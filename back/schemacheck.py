from app import get_db_connection


def print_db_info():
    conn = get_db_connection()
    cursor = conn.cursor()

    # List tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", [t[0] for t in tables])

    # Show columns for agencies table
    cursor.execute("PRAGMA table_info(agencies);")
    cols = cursor.fetchall()
    print("Columns in agencies:", cols)

    # Sample data from agencies
    cursor.execute("SELECT id, name FROM agencies LIMIT 3")
    rows = cursor.fetchall()
    print("Sample rows:", rows)

    conn.close()

if __name__ == "__main__":
    print_db_info()
