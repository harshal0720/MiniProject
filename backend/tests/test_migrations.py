
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic import command


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


def run_alembic(database_path: Path, revision: str) -> None:
    """Run Alembic against a disposable SQLite database."""
    database_url = f"sqlite:///{database_path.as_posix()}"

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(BACKEND_DIR)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)

    # Alembic env.py reads app.core.database.engine, which is created
    # when the process starts. Run it in a subprocess so DATABASE_URL
    # is applied before that engine is imported.
    script = (
        "import os; "
        "from alembic.config import Config; "
        "from alembic import command; "
        f"os.environ['DATABASE_URL'] = {database_url!r}; "
        f"config = Config({str(BACKEND_DIR / 'alembic.ini')!r}); "
        f"config.set_main_option('sqlalchemy.url', {database_url!r}); "
        f"command.upgrade(config, {revision!r})"
    )

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_chain_preserves_legacy_region_data(tmp_path: Path) -> None:
    database_path = tmp_path / "migration_test.db"

    # Create the known legacy schema with one existing region.
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE cloud_regions (
                id INTEGER PRIMARY KEY,
                provider VARCHAR(80) NOT NULL,
                region VARCHAR(120) NOT NULL,
                carbon_intensity FLOAT NOT NULL,
                renewable_energy_pct FLOAT NOT NULL,
                estimated_cost_usd_per_kwh FLOAT NOT NULL,
                latency_ms FLOAT NOT NULL,
                available_cpu_cores INTEGER NOT NULL,
                available_memory_gb FLOAT NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cloud_regions (
                id, provider, region, carbon_intensity,
                renewable_energy_pct, estimated_cost_usd_per_kwh,
                latency_ms, available_cpu_cores, available_memory_gb,
                updated_at
            )
            VALUES (
                1, 'AWS', 'test-region', 120.0,
                70.0, 0.12, 25.0, 8, 32.0,
                '2026-01-01 00:00:00'
            )
            """
        )

    run_alembic(database_path, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(cloud_regions)")
        }
        assert "carbon_updated_at" in columns
        assert "total_cpu_cores" in columns
        assert "total_memory_gb" in columns

        region = connection.execute(
            """
            SELECT provider, region, available_cpu_cores,
                   available_memory_gb, total_cpu_cores, total_memory_gb
            FROM cloud_regions
            WHERE id = 1
            """
        ).fetchone()

        assert region is not None
        assert region == ("AWS", "test-region", 8, 32.0, 8, 32.0)

        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert revision == ("0004_capacity_release_alert_guard",)
