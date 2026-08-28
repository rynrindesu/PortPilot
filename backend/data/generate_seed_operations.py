import csv
import random
from datetime import timedelta
from pathlib import Path

from PortPilot.database.postgres import get_connection, get_all_vessel_states

OUTPUT_DIR = Path(__file__).resolve().parent / "seed_operations"

PILOTS = [f"P{i:02d}" for i in range(1, 6)]   # P01-P05
TUGS = [f"T{i:02d}" for i in range(1, 5)]     # T01-T04
BERTHS = [f"B{i:02d}" for i in range(1, 9)]   # B01-B08

RESOURCE_TABLES = {
    "pilot": ("pilot_assignments", "pilot_id", PILOTS),
    "tug": ("tug_assignments", "tug_id", TUGS),
    "berth": ("berth_allocations", "berth_id", BERTHS),
}

# Windows are relative to ETA - pilot boards shortly before/after arrival,
# tug assists around the same time, berth ops start once alongside is
# complete and run for the day.
SCHEDULE_WINDOWS = {
    "pilot": (timedelta(minutes=-30), timedelta(minutes=30)),
    "tug": (timedelta(minutes=-15), timedelta(minutes=45)),
    "berth": (timedelta(minutes=30), timedelta(hours=8)),
}

# Check if this vessel already has a row in the given assignment table
# - used to enforce 'seed once, never regenerate' per resource type.
def _vessel_has_schedule(cursor, table, vessel_name, imo_number):
    cursor.execute(
        f"SELECT 1 FROM {table} WHERE vessel_name = %s AND imo_number = %s",
        (vessel_name, imo_number),
    )
    return cursor.fetchone() is not None

# Check whether one resource is free for [start, end) - against bookings
# already confirmed in the database, AND against bookings already generated
# earlier in this same run (since those haven't been pushed to the DB yet,
# a plain SELECT wouldn't see them).
def _is_available(cursor, table, resource_column, resource_id, start, end, in_run_bookings):
    cursor.execute(
        f"""
        SELECT 1 FROM {table}
        WHERE {resource_column} = %s
          AND status = 'confirmed'
          AND start_time < %s
          AND end_time > %s
        LIMIT 1
        """,
        (resource_id, end, start),
    )
    if cursor.fetchone() is not None:
        return False

    for booked_start, booked_end in in_run_bookings.get(resource_id, []):
        if booked_start < end and booked_end > start:
            return False

    return True

# Pick one resource from the pool that's free for [start, end). Falls
# back to a random pick flagged 'pending_review' if none are free.
def _assign_resource(cursor, table, resource_column, pool, start, end, in_run_bookings):
    candidates = pool[:]
    random.shuffle(candidates)

    for resource_id in candidates:
        if _is_available(cursor, table, resource_column, resource_id, start, end, in_run_bookings):
            in_run_bookings.setdefault(resource_id, []).append((start, end))
            return resource_id, "confirmed"

    return random.choice(pool), "pending_review"

# Entry point: read every vessel currently in vessel_state, generate
# pilot/tug/berth bookings for any that don't already have one, and write
# the results to CSV files under seed_operations/.
# Does NOT write to the database - run push_seed_operations.py separately to commit these.
# limit: if set, only process the first N vessels - useful for testing
# against a small batch instead of the full vessel_state table.
def generate_operations_csv(limit=None):
    vessels = get_all_vessel_states()
    print(f"Found {len(vessels)} vessels in vessel_state.")

    if limit is not None:
        vessels = vessels[:limit]
        print(f"Restricting to first {len(vessels)} vessels for this run.")

    rows = {kind: [] for kind in RESOURCE_TABLES}
    in_run_bookings = {kind: {} for kind in RESOURCE_TABLES}

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for vessel in vessels:
                vessel_name = vessel["vessel_name"]
                imo_number = vessel["imo_number"]
                eta = vessel["eta"]

                for kind, (table, resource_column, pool) in RESOURCE_TABLES.items():
                    if _vessel_has_schedule(cursor, table, vessel_name, imo_number):
                        continue

                    offset_start, offset_end = SCHEDULE_WINDOWS[kind]
                    start, end = eta + offset_start, eta + offset_end

                    resource_id, status = _assign_resource(
                        cursor, table, resource_column, pool, start, end, in_run_bookings[kind]
                    )

                    rows[kind].append({
                        "vessel_name": vessel_name,
                        "imo_number": imo_number,
                        resource_column: resource_id,
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                        "status": status,
                    })

    OUTPUT_DIR.mkdir(exist_ok=True)

    for kind, (table, resource_column, _) in RESOURCE_TABLES.items():
        filename = OUTPUT_DIR / f"{table}.csv"
        fieldnames = ["vessel_name", "imo_number", resource_column, "start_time", "end_time", "status"]

        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows[kind])

        print(f"Wrote {len(rows[kind])} rows to {filename}")


if __name__ == "__main__":
    generate_operations_csv(limit=5)
