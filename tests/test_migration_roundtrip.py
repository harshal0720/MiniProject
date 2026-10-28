import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_alembic(db_path: Path, revision: str) -> None:
    url = f"sqlite:///{db_path.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["PYTHONPATH"] = str(BACKEND_DIR)
    script = (
        "import os; from alembic.config import Config; from alembic import command; "
        f"os.environ['DATABASE_URL']={url!r}; "
        f"cfg=Config({str(BACKEND_DIR / 'alembic.ini')!r}); "
        f"cfg.set_main_option('sqlalchemy.url', {url!r}); "
        + (f"command.downgrade(cfg, {revision!r})" if revision == '-1' else f"command.upgrade(cfg, {revision!r})")
    )
    subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True)


def version_and_tables(db_path: Path):
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return version, tables


def test_empty_database_upgrade_downgrade_one_step_upgrade(tmp_path: Path):
    db_path = tmp_path / "empty_roundtrip.db"
    run_alembic(db_path, "head")
    version, tables = version_and_tables(db_path)
    assert version == "0004_capacity_release_alert_guard"
    assert {"workload_status_history", "monitoring_alerts"} <= tables

    run_alembic(db_path, "-1")
    version, tables = version_and_tables(db_path)
    assert version == "0003_monitoring"
    assert {"workload_status_history", "monitoring_alerts"} <= tables

    run_alembic(db_path, "head")
    version, tables = version_and_tables(db_path)
    assert version == "0004_capacity_release_alert_guard"
    assert {"workload_status_history", "monitoring_alerts"} <= tables
