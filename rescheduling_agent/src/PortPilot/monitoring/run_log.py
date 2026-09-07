"""In-process record of what the rescheduling agent actually did.

Postgres keeps the applied change. It does not keep the options the agent
generated and rejected, and those are the interesting part of an autonomous
decision - they are the evidence that a refusal was reasoned rather than a
failure. This module captures each run as it happens so the console can show
the whole decision, not just its outcome.

Nothing here may raise into the monitoring path: every recorder is wrapped by
its caller and failures are swallowed. A missing trace must never cost a
vessel its schedule.
"""

from collections import deque
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any

MAX_RUNS = 200


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _minutes_between(a: Any, b: Any) -> int:
    try:
        start = a if isinstance(a, datetime) else datetime.fromisoformat(str(a))
        end = b if isinstance(b, datetime) else datetime.fromisoformat(str(b))
        return int(round((end - start).total_seconds() / 60))
    except Exception:
        return 0


def _subject_allocations(option: dict, vessel_name: str, imo_number: str) -> dict:
    """The option's new allocations for the vessel being rescheduled."""

    for change in option.get("changes") or []:
        if (
            change.get("vessel_name") == vessel_name
            and str(change.get("imo_number")) == str(imo_number)
        ):
            return change.get("allocations") or {}
    changes = option.get("changes") or []
    return (changes[0].get("allocations") or {}) if changes else {}


def _displaced(option: dict, vessel_name: str) -> list[str]:
    names: list[str] = []
    for booking in option.get("resource_conflicts") or []:
        name = booking.get("vessel_name")
        if name and name != vessel_name and name not in names:
            names.append(name)
    for affected in option.get("affected_vessels") or []:
        name = affected.get("vessel_name")
        if name and name != vessel_name and name not in names:
            names.append(name)
    return names


def _shape_option(
    option: dict,
    *,
    vessel_name: str,
    imo_number: str,
    current: dict,
) -> dict:
    """Project one generated option into the shape the console renders."""

    allocations = _subject_allocations(option, vessel_name, imo_number)
    moves = []
    total_shift = 0

    for resource_type in ("berth", "pilot", "tug"):
        new = allocations.get(resource_type)
        if not new:
            continue
        old = (current or {}).get(resource_type) or {}
        shift = _minutes_between(old.get("start_time"), new.get("start_time"))
        total_shift = max(total_shift, abs(shift))
        moves.append(
            {
                "resource_type": resource_type,
                "from_resource": old.get("resource_id") or new.get("resource_id") or "",
                "to_resource": new.get("resource_id") or "",
                "from_start": _iso(old.get("start_time")) or _iso(new.get("start_time")),
                "to_start": _iso(new.get("start_time")),
                "to_end": _iso(new.get("end_time")),
            }
        )

    invalid_reason = option.get("invalid_reason")
    scores = option.get("scores") or {}

    return {
        "option_id": option.get("option_id") or "OPT-?",
        "rank": option.get("rank"),
        "valid": invalid_reason is None,
        "invalid_reason": invalid_reason,
        "score": round(float(next(iter(scores.values()), 0) or 0), 2) if scores else 0,
        "strategy": option.get("strategy"),
        "moves": moves,
        "displaced_vessels": _displaced(option, vessel_name),
        "total_shift_minutes": total_shift,
    }


def _steps(
    *,
    generated: int,
    valid: int,
    outcome: str,
    duration_ms: int,
    vessel_name: str,
    delta_minutes: int,
    current: dict,
    flagged: list,
) -> list[dict]:
    blocked = outcome in ("pending_review", "unable_to_resolve", "failed")
    resources = ", ".join(
        f"{kind} {(current.get(kind) or {}).get('resource_id', '?')}"
        for kind in ("berth", "pilot", "tug")
        if current.get(kind)
    ) or "its current allocations"

    return [
        {
            "key": "detect",
            "title": "ETA change detected",
            "detail": (
                f"OCEANS-X reported {'a delay of' if delta_minutes >= 0 else 'an advance of'} "
                f"{abs(delta_minutes)} minutes against the stored ETA."
            ),
            "actor": "monitor",
            "status": "done",
            "ms": 0,
        },
        {
            "key": "inspect",
            "title": "Agent inspected the current schedule",
            "detail": f"Read {resources} plus every booking overlapping the conflict window.",
            "actor": "agent",
            "status": "done",
            "ms": 0,
        },
        {
            "key": "generate",
            "title": "Deterministic options generated",
            "detail": f"{generated} candidate reschedules produced from the active resource pool.",
            "actor": "rules",
            "status": "done",
            "ms": 0,
        },
        {
            "key": "validate",
            "title": "Hard constraints applied",
            "detail": (
                f"{valid} of {generated} survived buffer, ETA-ordering and "
                "pool-availability checks."
            ),
            "actor": "rules",
            "status": "blocked" if valid == 0 else "done",
            "ms": 0,
        },
        {
            "key": "rank",
            "title": "Options ranked",
            "detail": (
                "No option cleared the constraints — the allocation is escalated "
                "instead of guessed."
                if valid == 0
                else f"{valid} valid option(s) ranked by disruption; rank 1 selected."
            ),
            "actor": "rules",
            "status": "blocked" if valid == 0 else "done",
            "ms": 0,
        },
        {
            "key": "apply",
            "title": (
                "Escalated to pending review"
                if blocked
                else "Change applied and verified"
            ),
            "detail": (
                f"Flagged {', '.join(flagged) if flagged else 'the allocation'} for a "
                "human controller. No write to the allocation tables."
                if blocked
                else "Wrote the new window under a row-level lock and re-read it to "
                "confirm; logged to schedule_changes."
            ),
            "actor": "agent" if blocked else "database",
            "status": "blocked" if blocked else "done",
            "ms": duration_ms,
        },
    ]


def _persist(record: dict) -> None:
    """Copy a trace into Postgres so it outlives this process.

    Best effort and off the caller's thread: the monitoring path must never
    slow down, fail, or hold its lock because the audit copy could not be
    written.
    """

    def write() -> None:
        try:
            import json

            from PortPilot.database.postgres import get_connection

            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO agent_runs (
                            run_id, vessel_name, imo_number, trigger,
                            outcome, started_at, duration_ms, payload
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.get("run_id"),
                            record.get("vessel_name"),
                            record.get("imo_number"),
                            record.get("trigger"),
                            record.get("outcome"),
                            record.get("started_at"),
                            record.get("duration_ms") or 0,
                            json.dumps(record, default=str),
                        ),
                    )
        except Exception:
            pass

    Thread(target=write, name="portpilot-run-log", daemon=True).start()


def _load(limit: int) -> list[dict] | None:
    """Recent traces from Postgres, or None if the store is unavailable."""
    try:
        from PortPilot.database.postgres import get_connection

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT payload FROM agent_runs
                    ORDER BY started_at DESC, id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [row[0] for row in cursor.fetchall()]
    except Exception:
        return None


class AgentRunLog:
    """Bounded, thread-safe log of recent agent runs, newest first."""

    def __init__(self, maxlen: int = MAX_RUNS):
        self._runs: deque[dict] = deque(maxlen=maxlen)
        self._lock = Lock()
        self._seq = 0

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()
            self._seq = 0

    def runs(self, limit: int = MAX_RUNS) -> list[dict]:
        """Newest first.

        Reads the durable copy so traces survive a restart, and falls back to
        the in-process ring if Postgres is unreachable.
        """
        stored = _load(limit)
        if stored is not None:
            return stored
        with self._lock:
            return list(reversed(self._runs))[:limit]

    def _store(self, record: dict) -> None:
        """Append to the ring and mirror to Postgres. Caller holds the lock."""
        self._runs.append(record)
        _persist(record)

    def record_eta_change(
        self,
        event: dict,
        result_state: dict,
        duration_ms: int,
    ) -> None:
        """Capture one pass of the agent graph over an ETA change."""

        vessel_name = event.get("vessel_name") or ""
        imo_number = str(event.get("imo_number") or "")

        final = result_state.get("final_result") or {}
        schedule_result = result_state.get("schedule_result") or {}
        ranked_result = result_state.get("ranked_result") or {}

        # get_ranked_options returns the vessel's existing allocations as
        # previous_allocation; get_vessel_schedule returns them as allocations.
        current = (
            ranked_result.get("previous_allocation")
            or schedule_result.get("allocations")
            or (schedule_result.get("schedule") or {}).get("allocations")
            or {}
        )

        options = [
            _shape_option(
                o, vessel_name=vessel_name, imo_number=imo_number, current=current
            )
            for o in ranked_result.get("options") or []
        ]

        # When nothing survived validation the tool returns the deduplicated
        # rejection reasons rather than the rejected candidates themselves.
        # Surface each reason as its own row: it is the evidence behind the
        # escalation, and it is the only record of it that exists.
        for i, reason in enumerate(ranked_result.get("invalid_reasons") or [], start=1):
            options.append(
                {
                    "option_id": f"REJECTED-{i}",
                    "rank": None,
                    "valid": False,
                    "invalid_reason": reason,
                    "score": 0,
                    "strategy": None,
                    "moves": [],
                    "displaced_vessels": [],
                    "total_shift_minutes": 0,
                }
            )

        generated_count = int(
            ranked_result.get("generated_option_count") or len(options) or 0
        )
        valid_count = int(
            ranked_result.get("valid_option_count")
            if ranked_result.get("valid_option_count") is not None
            else sum(1 for o in options if o["valid"])
        )

        outcome_map = {
            "rescheduled": "resources_allocated",
            "no_action": "no_action",
            "pending_review": "pending_review",
        }
        outcome = outcome_map.get(final.get("outcome"), "pending_review")

        previous_eta = _iso(event.get("previous_eta")) or _iso(final.get("previous_eta"))
        new_eta = _iso(event.get("new_eta")) or _iso(final.get("new_eta"))
        delta = _minutes_between(previous_eta, new_eta) if previous_eta and new_eta else 0

        with self._lock:
            self._seq += 1
            self._store(
                {
                    "run_id": f"RUN-{self._seq:04d}",
                    "vessel_name": vessel_name,
                    "imo_number": imo_number,
                    "trigger": "ETA_CHANGED",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "previous_eta": previous_eta,
                    "new_eta": new_eta,
                    "options_generated": generated_count,
                    "options_valid": valid_count,
                    "outcome": outcome,
                    "selected_option": final.get("selected_option_id"),
                    "rationale": final.get("agent_response") or "",
                    "steps": _steps(
                        generated=generated_count,
                        valid=valid_count,
                        outcome=final.get("outcome") or "",
                        duration_ms=duration_ms,
                        vessel_name=vessel_name,
                        delta_minutes=delta,
                        current=current,
                        flagged=final.get("flagged_resources") or [],
                    ),
                    "options": options,
                }
            )

    def record_retry(self, event: dict, result: dict, duration_ms: int) -> None:
        """Capture a deterministic retry of an incomplete assignment."""

        vessel_name = event.get("vessel_name") or ""
        outcome = result.get("outcome") or "no_action"
        if outcome == "no_action":
            return

        with self._lock:
            self._seq += 1
            self._store(
                {
                    "run_id": f"RUN-{self._seq:04d}",
                    "vessel_name": vessel_name,
                    "imo_number": str(event.get("imo_number") or ""),
                    "trigger": "INCOMPLETE_ASSIGNMENT",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                    "previous_eta": None,
                    "new_eta": None,
                    "options_generated": 0,
                    "options_valid": 0,
                    "outcome": (
                        "resources_allocated"
                        if outcome == "resources_allocated"
                        else "pending_review"
                    ),
                    "selected_option": None,
                    "rationale": (
                        f"Unconfirmed {', '.join(result.get('unconfirmed_resource_types') or [])} "
                        f"assignment(s) resolved by the deterministic pipeline."
                        if outcome == "resources_allocated"
                        else "No valid option existed for the unconfirmed allocation; "
                        "escalated for human review."
                    ),
                    "steps": [],
                    "options": [],
                }
            )


agent_run_log = AgentRunLog()
