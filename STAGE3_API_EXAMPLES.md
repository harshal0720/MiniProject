# GreenScale AI — Stage 3 monitoring API

Run from `backend` after applying the patch:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload
```

Examples use PowerShell 5.1 `Invoke-RestMethod`. For POST requests with JSON, use `-ContentType 'application/json'`.

## GET `/api/monitor/health`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/monitor/health
```

Expected shape (counts depend on the database):

```json
{"region_count":2,"open_alerts_by_severity":{"warning":0,"critical":0},"workloads_by_status":{"pending":1,"scheduled":0,"running":0,"completed":0,"failed":0,"deferred":0},"carbon_freshness":{"fresh":2,"stale":0,"missing":0,"total":2}}
```

## GET `/api/monitor/regions`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/monitor/regions
```

Each region item contains `id`, `provider`, `region`, used/total/available CPU and memory, utilisation percentages, `level` (`ok`, `warning`, `critical`), `carbon_freshness` (`fresh`, `stale`, `missing`), and `carbon_updated_at`.

## GET `/api/monitor/workloads`

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/monitor/workloads?page=1&page_size=20&status=pending'
Invoke-RestMethod 'http://127.0.0.1:8000/api/monitor/workloads?region=green-region&created_from=2026-10-01T00:00:00Z&created_to=2026-10-31T23:59:59Z'
```

Expected shape: `{"items":[...],"page":1,"page_size":20,"total":1,"pages":1}`. Each item is a workload summary. `region` matches the region name or provider, case-insensitively.

## GET `/api/monitor/workloads/{id}`

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/monitor/workloads/1
```

Expected shape: workload fields plus `history`, an ordered array of `{id,from_status,to_status,changed_at,reason}` entries. Missing workload returns HTTP 404 with `{"detail":"Workload 999 not found.","code":"workload_not_found"}`.

## POST `/api/monitor/workloads/{id}/transition`

```powershell
$body = @{ to_status = 'deferred'; reason = 'Waiting for capacity' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/monitor/workloads/1/transition -ContentType 'application/json' -Body $body
```

Expected shape: `{"workload_id":1,"status":"deferred","history_id":1,"changed_at":"...","reason":"Waiting for capacity"}`. Illegal transition returns HTTP 409 with `code=illegal_transition`; an unknown status or invalid body returns HTTP 422.

## GET `/api/monitor/alerts`

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/monitor/alerts?page=1&page_size=20&severity=warning&resolved=false&region_id=1&type=stale_carbon_data'
Invoke-RestMethod 'http://127.0.0.1:8000/api/monitor/alerts?created_from=2026-10-01T00:00:00Z&created_to=2026-10-31T23:59:59Z'
```

Expected shape: `{"items":[...],"page":1,"page_size":20,"total":1,"pages":1}`. Alert items contain the alert model fields. All filters are optional.

## POST `/api/monitor/evaluate`

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/monitor/evaluate
```

Expected shape: `{"created_count":2,"skipped_count":0}`. Counts depend on current conditions; repeating evaluation while the same alerts remain open should return `created_count: 0` and count duplicate active conditions as skipped.

## POST `/api/monitor/alerts/{id}/resolve`

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/monitor/alerts/1/resolve
```

Expected shape: `{"id":1,"resolved":true}`. A missing alert returns HTTP 404 with `code=alert_not_found`.

## Common validation/error examples

```powershell
try { Invoke-RestMethod 'http://127.0.0.1:8000/api/monitor/workloads?page=0' } catch { $_.ErrorDetails.Message }
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/monitor/workloads/1/transition -ContentType 'application/json' -Body '{"to_status":"completed"}' } catch { $_.ErrorDetails.Message }
```

For monitor routes, application errors use `detail` and `code`; validation errors use `detail`, `code`, and an `errors` array. Timestamps and counts vary with the database state.
