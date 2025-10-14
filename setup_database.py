#!/usr/bin/env python3
"""
Database setup script for Reliable Imports framework.

This script creates the necessary database schema for the framework.
"""

import sys
import psycopg2


def setup_database(connection_string: str):
    """
    Set up the database schema for the Reliable Imports framework.

    Args:
        connection_string: PostgreSQL connection string
    """
    print("Setting up Reliable Imports database schema...")

    conn = psycopg2.connect(connection_string)
    conn.autocommit = True

    with conn.cursor() as cur:
        # Read and execute schema
        with open('reliable_imports/schema.sql', 'r') as f:
            schema_sql = f.read()

        print("Creating tables...")
        cur.execute(schema_sql)

    conn.close()

    print("Database setup complete!")
    print("\nCreated:")
    print("  - import_batches table")
    print("  - import_batch_items table")
    print("  - import_logs table")
    print("  - Indexes for performance")
    print("  - Views for monitoring")


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_database.py <connection_string>")
        print("\nExample:")
        print("  python setup_database.py 'postgresql://user:password@localhost:5432/mydb'")
        sys.exit(1)

    connection_string = sys.argv[1]

    try:
        setup_database(connection_string)
    except Exception as e:
        print(f"Error setting up database: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
