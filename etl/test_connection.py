from psycopg import connect
from config import DB_CONFIG

try:
    conn = connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        dbname=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )

    print("SUCCESS: Connected to PostgreSQL!")

    conn.close()

except Exception as e:
    print("ERROR:")
    print(e)