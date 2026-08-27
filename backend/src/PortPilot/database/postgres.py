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

def get_vessel_state(vessel_name):
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    vessel_name,
                    eta,
                    call_sign,
                    imo_number,
                    flag,
                    location_from,
                    location_to,
                    last_updated
                FROM vessel_state
                WHERE vessel_name = %s
                """,
                (vessel_name,)
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "vessel_name": row[0],
                "eta": row[1],
                "call_sign": row[2],
                "imo_number": row[3],
                "flag": row[4],
                "location_from": row[5],
                "location_to": row[6],
                "last_updated": row[7],
            }


def save_vessel_state(vessel):
    with get_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO vessel_state (
                    vessel_name,
                    eta,
                    call_sign,
                    imo_number,
                    flag,
                    location_from,
                    location_to
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (vessel_name)
                DO UPDATE SET
                    eta = EXCLUDED.eta,
                    call_sign = EXCLUDED.call_sign,
                    imo_number = EXCLUDED.imo_number,
                    flag = EXCLUDED.flag,
                    location_from = EXCLUDED.location_from,
                    location_to = EXCLUDED.location_to,
                    last_updated = NOW()
                """,
                (
                    vessel["vessel_name"],
                    vessel["eta"],
                    vessel["call_sign"],
                    vessel["imo_number"],
                    vessel["flag"],
                    vessel["location_from"],
                    vessel["location_to"],
                )
            )