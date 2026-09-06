import sqlite3
from pathlib import Path


DB_PATH = Path("portpilot.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def initialize_database():
    connection = get_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS vessel_state (
            vessel_name TEXT PRIMARY KEY,
            eta TEXT,
            last_updated TEXT
        )
    """)

    connection.commit()
    connection.close()


def get_vessel_state(vessel_name):
    connection = get_connection()

    cursor = connection.execute(
        """
        SELECT vessel_name, eta, last_updated
        FROM vessel_state
        WHERE vessel_name = ?
        """,
        (vessel_name,)
    )

    row = cursor.fetchone()
    connection.close()

    if row is None:
        return None

    return {
        "vessel_name": row[0],
        "eta": row[1],
        "last_updated": row[2]
    }


def save_vessel_state(vessel_name, eta, last_updated):
    connection = get_connection()

    connection.execute(
        """
        INSERT OR REPLACE INTO vessel_state
        (vessel_name, eta, last_updated)
        VALUES (?, ?, ?)
        """,
        (vessel_name, eta, last_updated)
    )

    connection.commit()
    connection.close()