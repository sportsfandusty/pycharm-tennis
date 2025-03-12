#!/usr/bin/env python3

import sqlite3
import os
import glob
import sys

def inspect_database(db_path, limit=10):
    """
    Inspects a SQLite3 database in the current directory, showing a sample of data.

    Args:
        db_path: Path to the SQLite3 database file.
        limit: Number of rows to display for each table.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found in the database.")
            conn.close()
            return

        for table in tables:
            table_name = table[0]
            print(f"\n--- Table: {table_name} ---")

            # Get schema (column names)
            cursor.execute(f"PRAGMA table_info({table_name});")
            schema = cursor.fetchall()
            column_names = [col[1] for col in schema]
            print(" | ".join(column_names))
            print("---" * len(column_names))

            # Get sample data
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT ?", (limit,))
                rows = cursor.fetchall()
                for row in rows:
                    print(" | ".join(str(value) for value in row))
            except sqlite3.OperationalError as e:
                print(f"Error fetching data from {table_name}: {e}")

        conn.close()

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

def main():
    # Find SQLite database files in the current directory
    db_files = glob.glob("*.db") + glob.glob("*.sqlite") + glob.glob("*.sqlite3")

    if not db_files:
        print("No SQLite database files found in the current directory.")
        return

    if len(db_files) > 1:
        print("Multiple database files found:")
        for i, db_file in enumerate(db_files):
            print(f"{i+1}. {db_file}")
        while True:
            try:
                choice = int(input("Enter the number of the database to inspect (or 0 to exit): "))
                if 0 <= choice <= len(db_files):
                    break
                else:
                    print("Invalid choice. Please enter a number between 1 and", len(db_files), "or 0 to exit.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        if choice == 0:
            return
        db_path = db_files[choice - 1]

    else:
        db_path = db_files[0]  # Only one database file, use it directly

    inspect_database(db_path)


if __name__ == "__main__":
    main()