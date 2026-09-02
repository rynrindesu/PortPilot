import atexit
import os
from datetime import datetime

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")


# Reuse database connections instead of opening a new connection for every query.
# The pool is created lazily so importing this module does not connect to the database.
_pool = None


def get_connection():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            kwargs={"password": DATABASE_PASSWORD},
            open=False,
        )
        _pool.open()
        # Close the connection pool cleanly when the application exits.
        atexit.register(_pool.close)
    return _pool.connection()


# Previous implementation kept for rollback if connection pooling causes issues.
# Opens a new database connection on every call.

# def get_connection():
#     return psycopg.connect(
#         DATABASE_URL,
#         password=DATABASE_PASSWORD
#     )

def get_vessel_state(vessel_name, imo_number):
    """Return the ETA state used by the monitoring service for one vessel."""
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    vessel_name,
                    original_eta,
                    previous_eta,
                    current_eta,
                    call_sign,
                    imo_number,
                    flag,
                    location_from,
                    location_to,
                    status,
                    last_eta_received_at,
                    last_updated
                FROM vessel_state
                WHERE vessel_name = %s AND imo_number = %s
                """,
                (vessel_name, imo_number)
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "vessel_name": row[0],
                "original_eta": row[1],
                "previous_eta": row[2],
                "current_eta": row[3],
                "call_sign": row[4],
                "imo_number": row[5],
                "flag": row[6],
                "location_from": row[7],
                "location_to": row[8],
                "status": row[9],
                "last_eta_received_at": row[10],
                "last_updated": row[11],
            }


def get_all_vessel_states():
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    vessel_name,
                    original_eta,
                    previous_eta,
                    current_eta,
                    call_sign,
                    imo_number,
                    flag,
                    location_from,
                    location_to,
                    last_updated
                FROM vessel_state
                """
            )

            rows = cursor.fetchall()

            return [
                {
                    "vessel_name": row[0],
                    "original_eta": row[1],
                    "previous_eta": row[2],
                    "current_eta": row[3],
                    "call_sign": row[4],
                    "imo_number": row[5],
                    "flag": row[6],
                    "location_from": row[7],
                    "location_to": row[8],
                    "last_updated": row[9],
                }
                for row in rows
            ]


def _metadata_values(vessel):
    """Return the API fields that may be refreshed without changing ETA state."""
    return (
        vessel.get("call_sign"),
        vessel.get("flag"),
        vessel.get("location_from"),
        vessel.get("location_to"),
        vessel["vessel_name"],
        vessel["imo_number"],
    )


def save_new_vessel_observation(vessel, incoming_eta, source="oceans_x"):
    """Create a vessel state without changing an existing vessel's ETA fields.

    The monitoring service calls this only when its initial read finds no state.
    ``ON CONFLICT DO NOTHING`` protects against a concurrent poll creating the
    same vessel between that read and this write.
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO vessel_state (
                    vessel_name,
                    imo_number,
                    original_eta,
                    current_eta,
                    call_sign,
                    flag,
                    location_from,
                    location_to,
                    eta_source,
                    last_eta_received_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (vessel_name, imo_number)
                DO NOTHING
                """,
                (
                    vessel["vessel_name"],
                    vessel["imo_number"],
                    incoming_eta,
                    incoming_eta,
                    vessel["call_sign"],
                    vessel["flag"],
                    vessel["location_from"],
                    vessel["location_to"],
                    source,
                )
            )


def record_eta_change(vessel, incoming_eta, source="oceans_x"):
    """Shift current ETA to previous ETA and persist the new observation.

    This is intentionally the only write that changes ETA history in
    ``vessel_state``. The ``IS DISTINCT FROM`` predicate also makes repeated
    API observations idempotent.
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE vessel_state
                SET
                    previous_eta = current_eta,
                    current_eta = %s,
                    call_sign = COALESCE(%s, call_sign),
                    flag = COALESCE(%s, flag),
                    location_from = COALESCE(%s, location_from),
                    location_to = COALESCE(%s, location_to),
                    eta_source = %s,
                    last_eta_received_at = NOW(),
                    last_updated = NOW()
                WHERE vessel_name = %s
                  AND imo_number = %s
                  AND current_eta IS DISTINCT FROM %s
                RETURNING previous_eta, current_eta
                """,
                (
                    incoming_eta,
                    *_metadata_values(vessel)[:4],
                    source,
                    vessel["vessel_name"],
                    vessel["imo_number"],
                    incoming_eta,
                )
            )
            row = cursor.fetchone()

            if row is None:
                return None

            cursor.execute(
                """
                INSERT INTO eta_history (
                    vessel_name,
                    imo_number,
                    previous_eta,
                    reported_eta,
                    source
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    vessel["vessel_name"],
                    vessel["imo_number"],
                    row[0],
                    row[1],
                    source,
                )
            )
            return {"previous_eta": row[0], "current_eta": row[1]}


def refresh_vessel_observation(vessel, source="oceans_x"):
    """Refresh optional API metadata without altering any ETA field."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE vessel_state
                SET
                    call_sign = COALESCE(%s, call_sign),
                    flag = COALESCE(%s, flag),
                    location_from = COALESCE(%s, location_from),
                    location_to = COALESCE(%s, location_to),
                    eta_source = %s,
                    last_eta_received_at = NOW(),
                    last_updated = NOW()
                WHERE vessel_name = %s AND imo_number = %s
                """,
                (*_metadata_values(vessel)[:4], source, vessel["vessel_name"], vessel["imo_number"]),
            )


RESOURCE_TABLES = {
    "berth": ("berth_allocations", "berth_id", "allocation_id"),
    "pilot": ("pilot_assignments", "pilot_id", "assignment_id"),
    "tug": ("tug_assignments", "tug_id", "assignment_id"),
}


def get_active_resources():
    """Return every active seeded resource, grouped by resource type."""
    resources = {resource_type: [] for resource_type in RESOURCE_TABLES}
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT resource_type, resource_id
                FROM resources
                WHERE status = 'active'
                ORDER BY resource_type, resource_id
                """
            )
            for resource_type, resource_id in cursor.fetchall():
                if resource_type in resources:
                    resources[resource_type].append(resource_id)
    return resources


def get_allocations_in_window(window_start, window_end):
    """Return active allocation windows that overlap a planning window."""
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    allocations = []
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for resource_type, (table, resource_column, id_column) in RESOURCE_TABLES.items():
                cursor.execute(
                    f"""
                    SELECT {id_column}, vessel_name, imo_number, {resource_column},
                           start_time, end_time, buffer_minutes, status
                    FROM {table}
                    WHERE status <> 'cancelled'
                      AND start_time < %s
                      AND end_time + (buffer_minutes * INTERVAL '1 minute') > %s
                    ORDER BY start_time
                    """,
                    (window_end, window_start),
                )
                allocations.extend(
                    {
                        "resource_type": resource_type,
                        "assignment_id": row[0],
                        "vessel_name": row[1],
                        "imo_number": row[2],
                        "resource_id": row[3],
                        "start_time": row[4],
                        "end_time": row[5],
                        "buffer_minutes": row[6],
                        "status": row[7],
                    }
                    for row in cursor.fetchall()
                )
    return allocations


def get_vessel_schedule(vessel_name, imo_number):
    """Return a vessel's ETA state and its current resource assignments."""
    vessel = get_vessel_state(vessel_name, imo_number)
    if vessel is None:
        return None

    schedule = {
        "vessel": vessel,
        "allocations": {"berth": None, "pilot": None, "tug": None},
    }
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for resource_type, (table, resource_column, id_column) in RESOURCE_TABLES.items():
                cursor.execute(
                    f"""
                    SELECT {id_column}, {resource_column}, start_time, end_time,
                           buffer_minutes, status
                    FROM {table}
                    WHERE vessel_name = %s AND imo_number = %s
                    ORDER BY start_time
                    """,
                    (vessel_name, imo_number),
                )
                assignments = [
                    {
                        "assignment_id": row[0],
                        "resource_id": row[1],
                        "start_time": row[2],
                        "end_time": row[3],
                        "buffer_minutes": row[4],
                        "status": row[5],
                    }
                    for row in cursor.fetchall()
                ]
                if len(assignments) > 1:
                    raise ValueError(
                        f"Expected one {resource_type} allocation for "
                        f"{vessel_name}/{imo_number}, found {len(assignments)}."
                    )
                if assignments:
                    schedule["allocations"][resource_type] = assignments[0]
    return schedule


def find_resource_conflicts(
    resource_type,
    resource_id,
    candidate_start,
    candidate_end,
    candidate_buffer_minutes=15,
    exclude_vessel_name=None,
    exclude_imo_number=None,
):
    """Return assignments whose occupied time overlaps a candidate window."""
    if resource_type not in RESOURCE_TABLES:
        raise ValueError(f"Unsupported resource type: {resource_type}")
    if candidate_end <= candidate_start:
        raise ValueError("candidate_end must be after candidate_start")

    table, resource_column, id_column = RESOURCE_TABLES[resource_type]
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {id_column}, vessel_name, imo_number, {resource_column},
                       start_time, end_time, buffer_minutes, status
                FROM {table}
                WHERE {resource_column} = %s
                  AND status <> 'cancelled'
                  AND start_time < %s + (%s * INTERVAL '1 minute')
                  AND %s < end_time + (buffer_minutes * INTERVAL '1 minute')
                ORDER BY start_time
                """,
                (resource_id, candidate_end, candidate_buffer_minutes, candidate_start),
            )
            rows = cursor.fetchall()

    conflicts = []
    for row in rows:
        if row[1] == exclude_vessel_name and row[2] == exclude_imo_number:
            continue
        conflicts.append(
            {
                "assignment_id": row[0],
                "vessel_name": row[1],
                "imo_number": row[2],
                "resource_id": row[3],
                "start_time": row[4],
                "end_time": row[5],
                "buffer_minutes": row[6],
                "status": row[7],
            }
        )
    return conflicts
