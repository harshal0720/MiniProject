from pathlib import Path
import os
import subprocess
import sys
import sqlite3

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_0003_downgrade_refuses_zero_cpu_before_dropping_monitoring_tables(tmp_path):
    db_path = tmp_path / "zero_cpu_downgrade.db"
    url = f"sqlite:///{db_path.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["PYTHONPATH"] = str(BACKEND_DIR)
    setup = (
        "from alembic.config import Config; from alembic import command; "
        f"cfg=Config({str(BACKEND_DIR / 'alembic.ini')!r}); "
        f"cfg.set_main_option('sqlalchemy.url', {url!r}); "
        "command.upgrade(cfg, 'head')"
    )
    subprocess.run([sys.executable, "-c", setup], cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True)
    with sqlite3.connect(db_path) as con:
        con.execute(
            """INSERT INTO cloud_regions (
                provider, region, carbon_intensity, renewable_energy_pct,
                estimated_cost_usd_per_kwh, latency_ms, available_cpu_cores,
                available_memory_gb, total_cpu_cores, total_memory_gb,
                updated_at, carbon_updated_at
            ) VALUES ('Test', 'zero-cpu', 100.0, 50.0, 0.1, 20.0, 0,
                      16.0, 16, 16.0, '2026-10-20 00:00:00', NULL)"""
        )
        con.commit()
    downgrade = setup.replace("command.upgrade(cfg, 'head')", "command.downgrade(cfg, '0002_total_capacity')")
    result = subprocess.run([sys.executable, "-c", downgrade], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "available_cpu_cores = 0" in (result.stderr + result.stdout)
    with sqlite3.connect(db_path) as con:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "monitoring_alerts" in tables
        assert "workload_status_history" in tables
