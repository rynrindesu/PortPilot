import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")


def get_connection():
    return psycopg.connect(
        DATABASE_URL,
        password=DATABASE_PASSWORD
    )

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
                "last_eta_received_at": row[9],
                "last_updated": row[10],
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
