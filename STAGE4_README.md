# GreenScale Stage 4 patch (UNTESTED until run in your backend)

## Files in this patch
Overwrites:
- app/models/scheduled_allocation.py
- app/models/monitoring.py
- app/services/monitoring.py
- app/services/scheduling.py
- app/api/routes/scheduling.py
- app/services/cloud_regions.py
- migrations/versions/0003_monitoring.py
- tests/test_monitoring.py
- tests/test_monitor.py

Adds:
- migrations/versions/0004_capacity_release_alert_guard.py
- tests/test_stage4_migration_safety.py

## Behavior decisions
- Capacity is released once on `completed` or `failed`; `released_at` is the guard.
- Allocation rows are retained, so completed/failed workloads cannot be rescheduled through the existing duplicate-allocation check.
- Scheduling writes its status-history row before the same commit as allocation and capacity reservation.
- Active alert fingerprints are unique; resolved alerts can be recreated.
- Migration 0003 downgrade refuses to start if any region has zero available CPU.
- Region seeding inserts missing demo provider/region pairs and preserves existing rows.

## Commands (PowerShell 5.1)
From `D:\GreenScale - MiniProject\backend`:
```powershell
& "..\.venv\Scripts\python.exe" -m compileall -q app migrations tests
& "..\.venv\Scripts\python.exe" -m pytest -q --basetemp=".pytest-tmp"
```
Expected test count: baseline 62 + 9 new cases = 71. This is an expectation, not a verified result. Paste actual output before treating Stage 4 as done.

## Real DB upgrade (only after the test suite passes)
```powershell
Set-Location "D:\GreenScale - MiniProject\backend"
if (-not (Test-Path ..\data\greenscale.db)) { throw "Real database not found; aborting." }
Copy-Item ..\data\greenscale.db ..\data\greenscale.pre_0004.db
if (-not (Test-Path ..\data\greenscale.pre_0004.db)) { throw "Backup verification failed; aborting." }
& "..\.venv\Scripts\python.exe" -m alembic upgrade head
```

Read-only verification:
```powershell
@'
import sqlite3
from pathlib import Path
p = Path(r"..\data\greenscale.db")
con = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)
try:
    print("revision:", con.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    print("released_at column:", [r[1] for r in con.execute("PRAGMA table_info(scheduled_allocations)") if r[1] == "released_at"])
    print("active-alert unique index:", [r[1] for r in con.execute("PRAGMA index_list(monitoring_alerts)") if "active_fingerprint" in r[1]])
finally:
    con.close()
'@ | & "..\.venv\Scripts\python.exe" -
```

Dependency comparison (no versions guessed):
```powershell
& "..\.venv\Scripts\python.exe" -m pip freeze | Select-String -Pattern '^(fastapi|uvicorn|SQLAlchemy|psycopg|alembic|pydantic-settings|pandas|numpy|pytest|httpx)=='
```
Compare output with requirements.txt manually before changing pins.

Git: `git rev-parse --show-toplevel` failed in the reported backend directory, so do not commit yet. Suggested commit after locating the real repo root and reviewing the diff:
`Stage 4: release workload capacity and harden monitoring`
