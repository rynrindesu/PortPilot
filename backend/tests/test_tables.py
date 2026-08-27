from portpilot.database.postgres import get_connection

with get_connection() as connection:
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM vessel_state")

        for row in cursor.fetchall():
            print(row)