import csv
import random
from datetime import timedelta
from pathlib import Path

from PortPilot.database.postgres import get_connection, get_all_vessel_states

OUTPUT_DIR = Path(__file__).resolve().parent / "seed_operations"

# Database table and resource ID column for each operation type.
RESOURCE_TABLES = {
    "pilot": ("pilot_assignments", "pilot_id"),
    "tug": ("tug_assignments", "tug_id"),
    "berth": ("berth_allocations", "berth_id"),
}

# Resource ID prefixes and minimum number of resources to generate.
POOL_PREFIX = {"pilot": "P", "tug": "T", "berth": "B"}
MIN_POOL_SIZE = {"pilot": 5, "tug": 4, "berth": 8}

# Pilotage starts before ETA and varies in duration.
PILOT_DURATION_RANGE_HOURS = (0.5, 2)

# Tug assistance starts at ETA and varies in duration.
TUG_DURATION_RANGE_MINUTES = (30, 60)

# Berth allocation starts at ETA and varies with vessel turnaround time.
BERTH_DURATION_RANGE_HOURS = (4, 12)


# Check whether a vessel already has an operation of this type.
def _vessel_has_schedule(cursor, table, vessel_name, imo_number):
    cursor.execute(
        f"SELECT 1 FROM {table} WHERE vessel_name = %s AND imo_number = %s",
        (vessel_name, imo_number),
    )
    return cursor.fetchone() is not None


# Calculate peak concurrent demand to determine how many resources
# are needed to support the generated schedules without conflicts.
def _peak_concurrency(windows):
    events = []
    
    # +1 when an operation starts, -1 when it ends.
    for start, end in windows:
        events.append((start, 1))
        events.append((end, -1))
        
    # If one booking ends when another starts, process the end first 
    # so they are not counted as overlapping.
    events.sort(key=lambda e: (e[0], e[1]))

    peak = current = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


# Generate resource IDs, e.g. pilot size 3 -> P01, P02, P03.
def _build_pool(kind, size):
    prefix = POOL_PREFIX[kind]
    return [f"{prefix}{i:02d}" for i in range(1, size + 1)]


# Check for conflicts with existing DB bookings and bookings created in this run.
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

    # Check bookings generated in this run but not yet stored in the DB.
    for booked_start, booked_end in in_run_bookings.get(resource_id, []):
        if booked_start < end and booked_end > start:
            return False

    return True


# Assign an available resource; flag for review if none are available.
def _assign_resource(cursor, table, resource_column, pool, start, end, in_run_bookings):
    candidates = pool[:]
    random.shuffle(candidates)

    for resource_id in candidates:
        if _is_available(cursor, table, resource_column, resource_id, start, end, in_run_bookings):
            in_run_bookings.setdefault(resource_id, []).append((start, end))
            return resource_id, "confirmed"

    return random.choice(pool), "pending_review"


# Generate seed operation schedules while avoiding resource conflicts where possible.
def generate_operations_csv(limit=None):
    vessels = get_all_vessel_states()
    print(f"Found {len(vessels)} vessels in vessel_state.")

    # Optionally process only a subset of vessels for testing.
    if limit is not None:
        vessels = vessels[:limit]
        print(f"Restricting to first {len(vessels)} vessels for this run.")

    rows = {kind: [] for kind in RESOURCE_TABLES}
    in_run_bookings = {kind: {} for kind in RESOURCE_TABLES}

    with get_connection() as connection:
        with connection.cursor() as cursor:
            # First pass: calculate operation windows before assigning resources.
            operations_to_assign = {kind: [] for kind in RESOURCE_TABLES}

            for vessel in vessels:
                vessel_name = vessel["vessel_name"]
                imo_number = vessel["imo_number"]
                eta = vessel["eta"]

                for kind, (table, _resource_column) in RESOURCE_TABLES.items():
                    if _vessel_has_schedule(cursor, table, vessel_name, imo_number):
                        continue
                    
                    if kind == "berth":
                        # Berth allocation starts at ETA with a variable occupancy duration.
                        start = eta
                        duration_hours = random.uniform(*BERTH_DURATION_RANGE_HOURS)
                        end = start + timedelta(hours=duration_hours)
                    elif kind == "pilot":
                        # Pilotage duration varies, with the assignment ending at ETA.
                        duration_hours = random.uniform(*PILOT_DURATION_RANGE_HOURS)
                        start = eta - timedelta(hours=duration_hours)
                        end = eta
                    else:
                        # Tug assistance starts at ETA with a variable duration.
                        start = eta
                        duration_minutes = random.uniform(*TUG_DURATION_RANGE_MINUTES)
                        end = start + timedelta(minutes=duration_minutes)

                    operations_to_assign[kind].append((vessel_name, imo_number, start, end))

            # Sort chronologically so resources can be reused efficiently.
            for kind in operations_to_assign:
                operations_to_assign[kind].sort(key=lambda p: p[2])

            # Size each resource pool based on peak concurrent demand.
            pools = {}
            for kind in RESOURCE_TABLES:
                windows = [(start, end) for _, _, start, end in operations_to_assign[kind]]
                peak = _peak_concurrency(windows)
                
                # Ensure enough resources for peak demand while keeping the minimum pool size.
                pool_size = max(MIN_POOL_SIZE[kind], peak)
                pools[kind] = _build_pool(kind, pool_size)
                print(
                    f"{kind}: {len(operations_to_assign[kind])} vessel(s) to seed, "
                    f"peak concurrent demand {peak}, pool size {pool_size}"
                )

            # Second pass: assign a resource to each operation window.
            for kind, (table, resource_column) in RESOURCE_TABLES.items():
                for vessel_name, imo_number, start, end in operations_to_assign[kind]:
                    resource_id, status = _assign_resource(
                        cursor, table, resource_column, pools[kind], start, end, in_run_bookings[kind]
                    )

                    rows[kind].append({
                        "vessel_name": vessel_name,
                        "imo_number": imo_number,
                        resource_column: resource_id,
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                        "status": status,
                    })

    # Write generated assignments to separate CSV files.
    OUTPUT_DIR.mkdir(exist_ok=True)

    for kind, (table, resource_column) in RESOURCE_TABLES.items():
        filename = OUTPUT_DIR / f"{table}.csv"
        fieldnames = ["vessel_name", "imo_number", resource_column, "start_time", "end_time", "status"]

        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows[kind])

        print(f"Wrote {len(rows[kind])} rows to {filename}")


if __name__ == "__main__":
    generate_operations_csv()
