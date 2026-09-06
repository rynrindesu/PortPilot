"""Find vessels in TODAY's live OCEANS-X feed that actually have something
for run_monitoring_cycle() to do right now, unlike find_test_vessel.py (which
only checks database freshness and says nothing about the live feed).

Two categories, matching run_monitoring_cycle()'s two phases:

  NEW      - present in the live feed, absent from vessel_state entirely.
             A real run treats this as a brand-new vessel: it gets seeded and
             assigned initial operations, which may land on "unconfirmed" -
             the only way phase 2 (unconfirmed retry) can trigger under
             run_monitoring_cycle_test.py's real, unfabricated design.

  ETA_DRIFT - present in both the live feed and vessel_state, with a live eta
              that differs from what's currently stored. A real run treats
              this as an ETA_CHANGED event and routes it through the real
              agent graph (phase 1) - exactly what run_monitoring_cycle_test.py
              needs to exercise the reschedule path for real.

For ETA_DRIFT candidates, each existing allocation's own start_time is also
checked against the freeze window, same as find_test_vessel.py - a candidate
whose berth/pilot/tug is already locked can't actually be rescheduled.

This is read-only: one live OCEANS-X fetch, plus reads from vessel_state and
the resource tables. No writes.

Usage from the repository root:
    PYTHONPATH=backend/src python \\
        backend/tests/graph_with_ai_simulation/find_live_test_vessels.py 2026-09-05
"""

import sys
from datetime import datetime, timedelta, timezone

from PortPilot.database.postgres import RESOURCE_TABLES, get_all_vessel_states, get_connection
from PortPilot.integration.oceans import get_vessels_due_to_arrive
from PortPilot.monitoring.monitor_service import normalize_eta

FREEZE_MARGIN = timedelta(hours=3)
MAX_RESULTS_PER_CATEGORY = 8


def _fetch_all_allocations():
    """{(vessel_name, imo_number): {resource_type: {start_time, status}}}."""
    by_vessel = {}
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for resource_type, (table, resource_column, _id_column) in RESOURCE_TABLES.items():
                cursor.execute(
                    f"SELECT vessel_name, imo_number, start_time, status FROM {table}"
                )
                for vessel_name, imo_number, start_time, status in cursor.fetchall():
                    key = (vessel_name, imo_number)
                    by_vessel.setdefault(key, {})[resource_type] = {
                        "start_time": start_time, "status": status,
                    }
    return by_vessel


def main() -> None:
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc)

    print(f"Fetching live OCEANS-X data for {date}...")
    live_vessels = get_vessels_due_to_arrive(date)
    print(f"Received {len(live_vessels)} vessel(s).\n")

    states_by_key = {(v["vessel_name"], v["imo_number"]): v for v in get_all_vessel_states()}
    allocations_by_vessel = _fetch_all_allocations()

    new_candidates = []
    drift_candidates = []

    for vessel in live_vessels:
        key = (vessel["vessel_name"], vessel["imo_number"])
        stored = states_by_key.get(key)

        if stored is None:
            new_candidates.append(vessel)
            continue

        live_eta = normalize_eta(vessel["eta"])
        stored_eta = normalize_eta(stored["current_eta"])
        if live_eta == stored_eta:
            continue

        allocations = allocations_by_vessel.get(key, {})
        locked = [
            resource_type for resource_type, info in allocations.items()
            if info["start_time"] <= now + FREEZE_MARGIN
        ]

        drift_candidates.append({
            "vessel_name": vessel["vessel_name"],
            "imo_number": vessel["imo_number"],
            "stored_eta": stored_eta,
            "live_eta": live_eta,
            "locked_resource_types": locked,
        })

    print(f"=== NEW (absent from vessel_state) - {len(new_candidates)} found ===")
    for vessel in new_candidates[:MAX_RESULTS_PER_CATEGORY]:
        print(f"  {vessel['vessel_name']!r} imo={vessel['imo_number']!r} eta={vessel['eta']}")
    if not new_candidates:
        print("  (none)")

    print(f"\n=== ETA_DRIFT (live eta != stored eta) - {len(drift_candidates)} found ===")
    for candidate in drift_candidates[:MAX_RESULTS_PER_CATEGORY]:
        lock_note = f"  LOCKED: {candidate['locked_resource_types']}" if candidate["locked_resource_types"] else "  all allocations outside freeze window"
        print(
            f"  {candidate['vessel_name']!r} imo={candidate['imo_number']!r} "
            f"stored={candidate['stored_eta'].isoformat()} live={candidate['live_eta'].isoformat()}"
        )
        print(f"   {lock_note}")
    if not drift_candidates:
        print("  (none)")


if __name__ == "__main__":
    main()
