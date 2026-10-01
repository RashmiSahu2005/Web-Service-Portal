#!/usr/bin/env python3
import os
import sqlite3
import psycopg2
from psycopg2 import sql
import argparse

def migrate(sqlite_path="deployiq.db", pg_url=None):
    if not pg_url:
        pg_url = os.getenv("DATABASE_URL")
    
    if not pg_url:
        print("ERROR: DATABASE_URL not set in environment or passed as argument.")
        print("Example: postgresql+psycopg2://user:password@localhost:5432/deployiq")
        return

    # Extract the raw connection string if it has the sqlalchemy prefix
    if pg_url.startswith("postgresql+psycopg2://"):
        pg_url = pg_url.replace("postgresql+psycopg2://", "postgresql://")

    print(f"Connecting to SQLite database at {sqlite_path}...")
    if not os.path.exists(sqlite_path):
        print(f"ERROR: SQLite database not found at {sqlite_path}")
        return

    try:
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_cursor = sqlite_conn.cursor()
    except Exception as e:
        print(f"ERROR: Failed to connect to SQLite: {e}")
        return

    print(f"Connecting to PostgreSQL database...")
    try:
        pg_conn = psycopg2.connect(pg_url)
        pg_cursor = pg_conn.cursor()
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        return

    tables_to_migrate = ["applications", "script_registry"]
    
    for table in tables_to_migrate:
        print(f"\nMigrating table '{table}'...")
        
        # Check if table exists in SQLite
        sqlite_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
        if not sqlite_cursor.fetchone():
            print(f"WARNING: Table '{table}' does not exist in SQLite. Skipping.")
            continue
            
        # Get column names
        sqlite_cursor.execute(f"PRAGMA table_info({table});")
        columns = [row[1] for row in sqlite_cursor.fetchall()]
        
        if not columns:
            print(f"WARNING: Could not determine columns for '{table}'. Skipping.")
            continue

        # Get data
        sqlite_cursor.execute(f"SELECT * FROM {table};")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            print(f"Table '{table}' is empty in SQLite. Skipping.")
            continue
            
        print(f"Found {len(rows)} rows to migrate.")
        
        # Insert into PG
        placeholders = ', '.join(['%s'] * len(columns))
        col_names = ', '.join(columns)
        
        insert_query = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"
        
        success_count = 0
        for row in rows:
            try:
                pg_cursor.execute(insert_query, row)
                success_count += 1
            except Exception as e:
                print(f"Error inserting row into '{table}': {e}")
                pg_conn.rollback()
                continue
                
        pg_conn.commit()
        print(f"Successfully migrated {success_count} rows for table '{table}'.")

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete. SQLite database was left untouched.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate configuration data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite", default="deployiq.db", help="Path to SQLite database file")
    parser.add_argument("--pg", help="PostgreSQL connection URL")
    args = parser.parse_args()
    
    migrate(args.sqlite, args.pg)
