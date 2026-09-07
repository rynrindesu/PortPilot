"""Read-only endpoints for the operations console.

Additive: nothing here changes monitoring, scheduling or the agent. Every
route is a projection of what the service already stores, shaped the way the
console consumes it.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Query

from PortPilot.database.postgres import (
    RESOURCE_TABLES,
    get_active_resources,
    get_all_vessel_states,
    get_connection,
)
from PortPilot.monitoring.run_log import agent_run_log


router = APIRouter(tags=["Console"])


def _iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


@router.get("/vessels")
def list_vessels():
    """Every active vessel with its berth, pilot and tug allocation."""

    vessels = get_all_vessel_states()

    allocations: dict[tuple[str, str], dict] = {}
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for resource_type, (table, resource_column, _id) in RESOURCE_TABLES.items():
                cursor.execute(
                    f"""
                    SELECT vessel_name, imo_number, {resource_column},
                           start_time, end_time, buffer_minutes, status
                    FROM {table}
                    """
                )
                for row in cursor.fetchall():
                    key = (row[0], row[1])
                    allocations.setdefault(key, {})[resource_type] = {
                        "resource_type": resource_type,
                        "resource_id": row[2],
                        "start_time": _iso(row[3]),
                        "end_time": _iso(row[4]),
                        "buffer_minutes": row[5],
                        "status": row[6],
                    }

    payload = []
    for vessel in vessels:
        key = (vessel["vessel_name"], vessel["imo_number"])
        found = allocations.get(key, {})
        payload.append(
            {
                "vessel_name": vessel["vessel_name"],
                "imo_number": vessel["imo_number"],
                "call_sign": vessel.get("call_sign") or "",
                "flag": vessel.get("flag") or "",
                "location_from": vessel.get("location_from") or "",
                "location_to": vessel.get("location_to") or "",
                "vessel_type": "",
                "loa_m": 0,
                "original_eta": _iso(vessel.get("original_eta")),
                "previous_eta": _iso(vessel.get("previous_eta")),
                "current_eta": _iso(vessel.get("current_eta")),
                "eta_source": vessel.get("eta_source") or "oceans_x",
                "eta_confidence": float(vessel.get("eta_confidence") or 0.95),
                "status": (
                    "staged"
                    if vessel.get("lifecycle_status") == "staged"
                    else "active"
                ),
                "last_updated": _iso(
                    vessel.get("last_eta_received_at") or vessel.get("last_updated")
                ),
                "allocations": {
                    "berth": found.get("berth"),
                    "pilot": found.get("pilot"),
                    "tug": found.get("tug"),
                },
            }
        )

    payload.sort(key=lambda v: v["current_eta"] or "")
    return payload


@router.get("/eta-history")
def list_eta_history(limit: int = Query(400, ge=1, le=2000)):
    """The append-only ETA revision log, newest first."""

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT eta_event_id, vessel_name, imo_number, previous_eta,
                       reported_eta, source, confidence, received_at
                FROM eta_history
                ORDER BY received_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "eta_event_id": row[0],
                    "vessel_name": row[1],
                    "imo_number": row[2],
                    "previous_eta": _iso(row[3]),
                    "reported_eta": _iso(row[4]),
                    "source": row[5] or "oceans_x",
                    "confidence": float(row[6] or 0.95),
                    "received_at": _iso(row[7]),
                }
                for row in cursor.fetchall()
            ]


@router.get("/schedule-changes")
def list_schedule_changes(limit: int = Query(200, ge=1, le=1000)):
    """Every allocation the agent actually rewrote."""

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT change_id, vessel_name, imo_number, resource_type,
                       resource_id, old_start_time, old_end_time,
                       new_start_time, new_end_time, reason, decision_score,
                       execution_mode, changed_at
                FROM schedule_changes
                ORDER BY changed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "change_id": row[0],
                    "vessel_name": row[1],
                    "imo_number": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "old_start_time": _iso(row[5]),
                    "old_end_time": _iso(row[6]),
                    "new_start_time": _iso(row[7]),
                    "new_end_time": _iso(row[8]),
                    "reason": row[9] or "",
                    "decision_score": row[10] or 0,
                    "execution_mode": row[11] or "autonomous",
                    "changed_at": _iso(row[12]),
                }
                for row in cursor.fetchall()
            ]


@router.get("/agent/runs")
def list_agent_runs():
    """
    Decision traces captured while monitoring ran.

    The generated-and-rejected options are not persisted to Postgres - only
    the applied change is - so they are recorded in process as the agent
    produces them. Restarting the service clears this log.
    """

    return agent_run_log.runs()


@router.get("/resources")
def list_resources():
    """The active resource pool, grouped by type."""

    return get_active_resources()


@router.post("/monitor/cycle")
def run_cycle(
    arrival_date: date | None = None,
    process_unconfirmed: bool = Query(
        True,
        description=(
            "Retry every vessel holding an unconfirmed allocation. True is the "
            "real hourly behaviour; set false to run only the ETA-change agent, "
            "which is far quicker when the backlog is large."
        ),
    ),
):
    """
    Run a full monitoring pass: poll OCEANS-X, then send each detected change
    through the agent. This is what the hourly job calls; exposing it lets the
    console trigger a real pass on demand.
    """

    import datetime as _dt
    import zoneinfo

    from PortPilot.agent import agent as agent_module

    when = (
        arrival_date
        or _dt.datetime.now(zoneinfo.ZoneInfo("Asia/Singapore")).date()
    ).isoformat()

    if process_unconfirmed:
        return agent_module.run_monitoring_cycle(when)

    # ETA changes only. Mirrors run_monitoring_cycle's first phase exactly,
    # without the unconfirmed-retry sweep.
    from PortPilot.monitoring.monitor_service import monitor_vessels

    changes = agent_module._deduplicate_events(monitor_vessels(when))
    eta_changes = [c for c in changes if c["event"] == "ETA_CHANGED"]

    results, errors = [], []
    for event in eta_changes:
        try:
            results.append(agent_module._process_eta_change(event))
        except Exception as error:  # one vessel must not stop the pass
            errors.append(
                {
                    "vessel_name": event.get("vessel_name"),
                    "imo_number": event.get("imo_number"),
                    "phase": "eta_change",
                    "error": str(error),
                }
            )

    return {
        "eta_change_results": results,
        "unconfirmed_retry_results": [],
        "raw_changes": changes,
        "errors": errors,
    }
