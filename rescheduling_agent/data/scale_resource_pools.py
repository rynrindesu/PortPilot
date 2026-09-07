"""Size the berth, pilot and tug pools to the port's actual peak demand.

Why this exists
---------------
Daily averages hide the binding constraint. Berth utilisation across a whole
day looked survivable at ~80 %, but arrivals cluster hard: at the 07:00-09:00
Singapore peak the live OCEANS-X feed wanted 83 berths, 64 pilots and 45 tugs
simultaneously, against pools of 46, 20 and 13.

Every pool was roughly 3x oversubscribed at peak, so the scheduling pipeline
correctly refused almost every vessel and the port-call day was unschedulable
by construction. That is a seeding problem, not an agent problem: the real
Port of Singapore runs on the order of 380 arrivals a day and does not staff
20 pilots to do it.

This script measures peak concurrent demand per resource type with a sweep
line (counting a resource occupied until its window plus turnaround buffer has
elapsed), then tops each pool up to that peak plus a headroom margin. Headroom
is deliberately small: enough that a well-formed day is solvable, not so much
that contention disappears and every allocation trivially succeeds.

    PYTHONPATH=src python data/scale_resource_pools.py --dry-run
    PYTHONPATH=src python data/scale_resource_pools.py --apply
"""

import argparse
import math
import sys
from datetime import timedelta

from PortPilot.database.postgres import get_active_resources, get_connection


# (allocation table, resource type, id prefix)
POOLS = (
    ("berth_allocations", "berth", "B"),
    ("pilot_assignments", "pilot", "P"),
    ("tug_assignments", "tug", "T"),
)

DEFAULT_HEADROOM = 0.15


def peak_concurrency(cursor, table):
    """Highest number of simultaneously-occupied resources, and when.

    A resource stays occupied for its window plus the turnaround buffer, so
    the buffer is part of demand — ignoring it understates the peak.
    """
    cursor.execute(f"SELECT start_time, end_time, buffer_minutes FROM {table}")
    events = []
    for start, end, buffer_minutes in cursor.fetchall():
        if start is None or end is None:
            continue
        events.append((start, 1))
        events.append((end + timedelta(minutes=buffer_minutes or 0), -1))

    # Releases sort before acquisitions at the same instant: a resource freed
    # at exactly T is available to a vessel starting at T.
    events.sort(key=lambda item: (item[0], item[1]))

    concurrent = peak = 0
    peak_at = None
    for at, delta in events:
        concurrent += delta
        if concurrent > peak:
            peak, peak_at = concurrent, at
    return peak, peak_at


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--headroom",
        type=float,
        default=DEFAULT_HEADROOM,
        help="fraction above peak demand to provision (default 0.15)",
    )
    args = parser.parse_args()

    pools = get_active_resources()
    plan = []

    with get_connection() as connection:
        with connection.cursor() as cursor:
            print(
                f"\n  {'resource':8} {'pool':>5} {'peak':>6} {'target':>7} "
                f"{'add':>5}   peak at"
            )
            for table, resource_type, prefix in POOLS:
                peak, peak_at = peak_concurrency(cursor, table)
                current = len(pools.get(resource_type, []))
                target = max(current, math.ceil(peak * (1 + args.headroom)))
                add = target - current
                plan.append((resource_type, prefix, current, target, add))
                stamp = peak_at.strftime("%H:%M") if peak_at else "-"
                print(
                    f"  {resource_type:8} {current:>5} {peak:>6} {target:>7} "
                    f"{add:>5}   {stamp} UTC"
                )

            if args.dry_run:
                print("\nDry run. Nothing written.\n")
                return 0

            print()
            for resource_type, prefix, current, target, add in plan:
                if add <= 0:
                    print(f"  {resource_type:8} already sufficient")
                    continue

                # Continue the existing numbering rather than renumbering, so
                # ids already referenced by allocations keep meaning.
                cursor.execute(
                    """
                    SELECT resource_id FROM resources
                    WHERE resource_type = %s
                    """,
                    (resource_type,),
                )
                existing = {row[0] for row in cursor.fetchall()}

                created = 0
                index = 1
                while created < add:
                    resource_id = f"{prefix}{index:02d}"
                    index += 1
                    if resource_id in existing:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO resources (resource_type, resource_id, status)
                        VALUES (%s, %s, 'active')
                        ON CONFLICT (resource_type, resource_id)
                        DO UPDATE SET status = 'active'
                        """,
                        (resource_type, resource_id),
                    )
                    existing.add(resource_id)
                    created += 1
                print(f"  {resource_type:8} +{created} -> {target}")

    after = get_active_resources()
    print("\nActive pools now:", {k: len(v) for k, v in after.items()})
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
