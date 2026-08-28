from PortPilot.database.postgres import get_connection

def test_postgres_connection():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            print("PostgreSQL connection successful!")
            print("Result:", result)


if __name__ == "__main__":
    test_postgres_connection()