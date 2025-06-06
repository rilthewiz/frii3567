import sqlite3

DB = 'ecfr_full_data.db'

def get_db_connection():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def print_db_info():
    conn = get_db_connection()
    cursor = conn.cursor()

    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])

    # For each table, print columns and 3 sample rows
    for table in [t[0] for t in tables]:
        print(f"\nColumns in {table}:")
        cursor.execute(f"PRAGMA table_info({table});")
        cols = cursor.fetchall()
        for col in cols:
            print(f"  {col[1]} ({col[2]})")  # col name and type

        # Try fetching some rows
        try:
            cursor.execute(f"SELECT * FROM {table} LIMIT 3")
            rows = cursor.fetchall()
            print(f"Sample rows from {table}:")
            for row in rows:
                print(dict(row))
        except sqlite3.OperationalError as e:
            print(f"Could not fetch rows from {table}: {e}")

    conn.close()

if __name__ == "__main__":
    print_db_info()
