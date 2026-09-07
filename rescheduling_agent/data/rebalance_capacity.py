"""Re-fit berth windows to the berth pool, then re-run the scheduling pipeline.

Why this exists
---------------
The seeded berth windows were 4-12 h. Against the real OCEANS-X arrival volume
(≈190-310 vessels a day) and a 46-berth pool that is a demand of roughly
2,400 berth-hours against 1,104 available - a 220 % load. No allocator can
solve that, so every vessel ended up escalated to pending_review and the
`schedule_changes` table filled with nothing but `human_review` rows.

Shorter windows (1.5-4 h) put the day at roughly 75-80 % load: still genuinely
contended, so real conflicts and real escalations occur, but solvable often
enough that the agent can actually allocate.

This script:
  1. re-fits every berth window to the new range, keeping start times,
  2. returns previously-escalated allocations to 'unconfirmed' so the pipeline
     will reconsider them now that the day is feasible,
  3. re-runs the retry pipeline for each affected vessel, recording a full
     decision trace for every run.

Run from rescheduling_agent/ with the virtualenv active:

    PYTHONPATH=src python data/rebalance_capacity.py --dry-run
    PYTHONPATH=src python data/rebalance_capacity.py --apply
"""

import argparse
import random
import sys

from PortPilot.database.postgres import get_connection, get_active_resources
from PortPilot.monitoring.monitor_service import (
    BERTH_DURATION_RANGE_HOURS,
    retry_unconfirmed_operations,
)


def capacity_report(cursor):
    """Print demand against capacity for each resource pool."""
    pools = get_active_resources()
    rows = []
    for table, resource_type in (
        ("berth_allocations", "berth"),
        ("pilot_assignments", "pilot"),
        ("tug_assignments", "tug"),
    ):
        cursor.execute(
            f"""
            SELECT count(*),
                   coalesce(sum(extract(epoch from (end_time - start_time)) / 3600), 0)
            FROM {table}
            """
        )
        bookings, demand_hours = cursor.fetchone()
        pool = max(1, len(pools.get(resource_type, [])))
        capacity = pool * 24
        rows.append(
            (
                resource_type,
                bookings,
                float(demand_hours),
                pool,
                capacity,
                round(float(demand_hours) / capacity * 100),
            )
        )

    print(f"  {'resource':10} {'bookings':>9} {'demand':>10} {'pool':>6} {'capacity':>10} {'load':>7}")
    for resource_type, bookings, demand, pool, capacity, load in rows:
        print(
            f"  {resource_type:10} {bookings:>9} {demand:>9.0f}h "
            f"{pool:>6} {capacity:>9}h {load:>6}%"
        )
    return rows


def status_report(cursor):
    for table in ("berth_allocations", "pilot_assignments", "tug_assignments"):
        cursor.execute(f"SELECT status, count(*) FROM {table} GROUP BY 1 ORDER BY 1")
        counts = ", ".join(f"{s}={n}" for s, n in cursor.fetchall())
        print(f"  {table:20} {counts}")


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report only")
    group.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument(
        "--seed", type=int, default=20260907, help="deterministic window seed"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="cap how many vessels are re-run through the pipeline (0 = all)",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    low, high = BERTH_DURATION_RANGE_HOURS

    with get_connection() as connection:
        with connection.cursor() as cursor:
            print("\nBEFORE")
            capacity_report(cursor)
            print()
            status_report(cursor)

            if args.dry_run:
                print(
                    f"\nDry run. Would re-fit berth windows to "
                    f"{low}-{high} h and reset escalated allocations.\n"
                )
                return 0

            # 1. Re-fit berth windows. Start times are the vessel's ETA and
            #    must not move; only the duration was wrong.
            cursor.execute(
                "SELECT allocation_id FROM berth_allocations ORDER BY allocation_id"
            )
            allocation_ids = [row[0] for row in cursor.fetchall()]
            for allocation_id in allocation_ids:
                hours = random.uniform(low, high)
                cursor.execute(
                    """
                    UPDATE berth_allocations
                    SET end_time = start_time + make_interval(secs => %s),
                        updated_at = now()
                    WHERE allocation_id = %s
                    """,
                    (hours * 3600, allocation_id),
                )
            print(f"\nRe-fitted {len(allocation_ids)} berth windows to {low}-{high} h.")

            # 2. Return escalated allocations to the queue. They were escalated
            #    because the day was infeasible, not because of anything about
            #    the vessel.
            reset_total = 0
            for table in (
                "berth_allocations",
                "pilot_assignments",
                "tug_assignments",
            ):
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET status = 'unconfirmed', updated_at = now()
                    WHERE status = 'pending_review'
                    """
                )
                reset_total += cursor.rowcount
            print(f"Returned {reset_total} escalated allocations to 'unconfirmed'.")

    # 3. Re-run the pipeline. Done outside the transaction above so each
    #    vessel commits independently and records its own decision trace.
    from PortPilot.database.postgres import get_unconfirmed_vessel_keys

    keys = get_unconfirmed_vessel_keys()
    if args.max_retries:
        keys = keys[: args.max_retries]
    print(f"\nRe-running the scheduling pipeline for {len(keys)} vessels...")

    outcomes: dict[str, int] = {}
    for index, key in enumerate(keys, start=1):
        try:
            result = retry_unconfirmed_operations(
                key["vessel_name"], key["imo_number"]
            )
            outcome = result["outcome"]
        except Exception as error:  # keep going; one vessel must not stop the pass
            outcome = f"error: {type(error).__name__}"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if index % 25 == 0:
            print(f"  {index}/{len(keys)}  {outcomes}")

    print(f"\nOutcomes: {outcomes}")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            print("\nAFTER")
            capacity_report(cursor)
            print()
            status_report(cursor)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
