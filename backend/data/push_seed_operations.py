import csv
from pathlib import Path

from PortPilot.database.postgres import get_connection

DATA_DIR = Path(__file__).resolve().parent / "seed_operations"

TABLES = {
    "pilot_assignments.csv": ("pilot_assignments", "pilot_id"),
    "tug_assignments.csv": ("tug_assignments", "tug_id"),
    "berth_allocations.csv": ("berth_allocations", "berth_id"),
}


def _read_csv(filename):
    with open(DATA_DIR / filename, newline="") as f:
        return list(csv.DictReader(f))

# Upsert every row in one CSV into its matching Supabase table. Safe to
# re-run - ON CONFLICT (vessel_name, imo_number) updates existing rows
# instead of duplicating them.
# limit: if set, only push the first N rows from this CSV - useful for
# testing against a small batch instead of the whole file.
def push_csv_to_table(filename, table, resource_column, limit=None):
    rows = _read_csv(filename)

    if limit is not None:
        rows = rows[:limit]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for row in rows:
                cursor.execute(
                    f"""
                    INSERT INTO {table} (vessel_name, imo_number, {resource_column}, start_time, end_time, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (vessel_name, imo_number)
                    DO UPDATE SET
                        {resource_column} = EXCLUDED.{resource_column},
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        status = EXCLUDED.status
                    """,
                    (
                        row["vessel_name"],
                        row["imo_number"],
                        row[resource_column],
                        row["start_time"],
                        row["end_time"],
                        row["status"],
                    ),
                )
        connection.commit()

    print(f"Pushed {len(rows)} rows into {table}.")

# Entry point: push all three seeded-operations CSVs to Supabase.
# limit: if set, only push the first N rows from each CSV.
def push_all(limit=None):
    for filename, (table, resource_column) in TABLES.items():
        push_csv_to_table(filename, table, resource_column, limit=limit)


if __name__ == "__main__":
    push_all(limit=5)
