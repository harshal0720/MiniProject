
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "greenscale.db"


def main() -> None:
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}")
        print("Start the backend once to create the database, then rerun.")
        sys.exit(1)

    with sqlite3.connect(DATABASE_PATH) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        if "cloud_regions" not in tables:
            print("Table cloud_regions does not exist; nothing was migrated.")
            sys.exit(1)

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(cloud_regions)")
        }

        if "available_cpu_cores" not in columns:
            connection.execute(
                "ALTER TABLE cloud_regions "
                "ADD COLUMN available_cpu_cores INTEGER NOT NULL DEFAULT 64"
            )
            print("Added available_cpu_cores.")

        if "available_memory_gb" not in columns:
            connection.execute(
                "ALTER TABLE cloud_regions "
                "ADD COLUMN available_memory_gb FLOAT NOT NULL DEFAULT 256.0"
            )
            print("Added available_memory_gb.")

        connection.commit()

    print("Region capacity migration completed.")


if __name__ == "__main__":
    main()
