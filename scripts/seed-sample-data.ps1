$ErrorActionPreference = "Stop"
$BaseUrl = "http://127.0.0.1:8000"

function Get-ApiErrorDetail($ErrorRecord) {
    try {
        $response = $ErrorRecord.Exception.Response
        if ($response -and $response.GetResponseStream()) {
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
            $body = $reader.ReadToEnd()
            $reader.Dispose()
            try {
                $json = $body | ConvertFrom-Json
                if ($json.detail -is [System.Array]) {
                    return (($json.detail | ForEach-Object {
                        "$($_.loc -join '.') $($_.msg)"
                    }) -join "; ")
                }
                if ($json.detail) { return [string]$json.detail }
                return $body
            } catch { return $body }
        }
    } catch {}
    return $ErrorRecord.Exception.Message
}

function Invoke-Api($Method, $Path, $Body = $null) {
    $uri = "$BaseUrl$Path"
    try {
        if ($null -ne $Body) {
            $json = $Body | ConvertTo-Json -Depth 10 -Compress
            $result = Invoke-RestMethod -Method $Method -Uri $uri `
                -ContentType "application/json" -Body $json -TimeoutSec 30
        } else {
            $result = Invoke-RestMethod -Method $Method -Uri $uri -TimeoutSec 30
        }
        Write-Host ("[OK] {0} {1}" -f $Method, $Path) -ForegroundColor Green
        return @{ Ok = $true; Data = $result; Error = $null }
    } catch {
        $detail = Get-ApiErrorDetail $_
        Write-Host ("[FAILED] {0} {1} :: {2}" -f $Method, $Path, $detail) `
            -ForegroundColor Yellow
        return @{ Ok = $false; Data = $null; Error = $detail }
    }
}

Write-Host "GreenScale sample-data seeder" -ForegroundColor Cyan
Write-Host "API: $BaseUrl"

$health = Invoke-Api "GET" "/api/health"
if (-not $health.Ok) {
    Write-Host "Backend is unreachable. Start it and run this script again." `
        -ForegroundColor Red
    exit 1
}

$existing = Invoke-Api "GET" "/api/workload/list"
if (-not $existing.Ok) {
    Write-Host "Could not inspect existing workloads; stopping to avoid duplicates." `
        -ForegroundColor Red
    exit 1
}

$existingItems = @()
if ($existing.Data -is [System.Array]) {
    $existingItems = @($existing.Data)
} elseif ($existing.Data.items) {
    $existingItems = @($existing.Data.items)
} else {
    Write-Host "Unexpected workload-list response; stopping safely." -ForegroundColor Red
    exit 1
}

$sampleExisting = @($existingItems | Where-Object {
    $_.name -like "sample-*"
})
if ($sampleExisting.Count -gt 0) {
    Write-Host ("Found {0} existing sample-* workloads. No new workloads created." `
        -f $sampleExisting.Count) -ForegroundColor Yellow
    exit 0
}

$types = @("batch", "web_service", "ml_training", "data_processing")
$priorities = @("low", "normal", "high", "critical")
$created = @()
$scheduled = @()
$createFailed = 0
$optimizeFailed = 0
$scheduleFailed = 0
$transitionSucceeded = 0

for ($i = 0; $i -lt 14; $i++) {
    $type = $types[$i % $types.Count]
    $priority = $priorities[($i + [math]::Floor($i / 4)) % $priorities.Count]
    $cpu = 1 + (($i * 7) % 64)
    $memory = 1 + (($i * 17) % 256)
    $latency = 50 + (($i * 379) % 4951)
    $carbonAware = (($i % 3) -ne 0)
    $name = "sample-$type-$($i + 1)"

    $body = @{
        name = $name
        workload_type = $type
        priority = $priority
        required_cpu_cores = $cpu
        required_memory_gb = $memory
        max_latency_ms = $latency
        carbon_aware = $carbonAware
    }

    $result = Invoke-Api "POST" "/api/workload/create" $body
    if (-not $result.Ok) {
        $createFailed++
        continue
    }

    $workload = $result.Data
    if ($null -eq $workload.id) {
        Write-Host "[WARN] Create response had no workload id; skipping follow-up calls." `
            -ForegroundColor Yellow
        $createFailed++
        continue
    }

    $created += $workload
    Write-Host ("  Created id={0}, name={1}, type={2}, priority={3}" -f `
        $workload.id, $name, $type, $priority)

    if ($created.Count -le 8) {
        $optimized = Invoke-Api "POST" "/api/optimize" @{
            workload_id = [int]$workload.id
        }
        if (-not $optimized.Ok) {
            $optimizeFailed++
            continue
        }

        $scheduleResult = Invoke-Api "POST" "/api/schedule" @{
            workload_id = [int]$workload.id
        }

        if ($scheduleResult.Ok) {
            $status = [string]$scheduleResult.Data.status
            Write-Host ("  Schedule result: id={0}, status={1}, region={2}" -f `
                $workload.id, $status, $scheduleResult.Data.region)
            if ($status -eq "scheduled") {
                $scheduled += [int]$workload.id
            } else {
                $scheduleFailed++
            }
        } else {
            $scheduleFailed++
        }
    }
}

# Try valid lifecycle transitions on workloads that actually scheduled.
if ($scheduled.Count -ge 1) {
    $id = $scheduled[0]
    $r = Invoke-Api "POST" "/api/monitor/workloads/$id/transition" @{
        to_status = "running"
        reason = "Sample-data lifecycle test"
    }
    if ($r.Ok) {
        $transitionSucceeded++
        $done = Invoke-Api "POST" "/api/monitor/workloads/$id/transition" @{
            to_status = "completed"
            reason = "Sample-data completion test"
        }
        if ($done.Ok) { $transitionSucceeded++ }
    }
}

if ($scheduled.Count -ge 2) {
    $id = $scheduled[1]
    $r = Invoke-Api "POST" "/api/monitor/workloads/$id/transition" @{
        to_status = "running"
        reason = "Sample-data lifecycle test"
    }
    if ($r.Ok) {
        $transitionSucceeded++
        $failed = Invoke-Api "POST" "/api/monitor/workloads/$id/transition" @{
            to_status = "failed"
            reason = "Intentional sample failure for UI testing"
        }
        if ($failed.Ok) { $transitionSucceeded++ }
    }
}

$evaluation = Invoke-Api "POST" "/api/monitor/evaluate"
if ($evaluation.Ok) {
    Write-Host ("Evaluation: created_count={0}, skipped_count={1}" -f `
        $evaluation.Data.created_count, $evaluation.Data.skipped_count)
}

$monitorHealth = Invoke-Api "GET" "/api/monitor/health"
if ($monitorHealth.Ok) {
    Write-Host "Monitor health response:"
    $monitorHealth.Data | ConvertTo-Json -Depth 8
}

Write-Host "`n========== SEED SUMMARY ==========" -ForegroundColor Cyan
Write-Host "Workloads created:       $($created.Count)"
Write-Host "Create failures:         $createFailed"
Write-Host "Optimize failures:       $optimizeFailed"
Write-Host "Schedule non-successes:  $scheduleFailed"
Write-Host "Successfully scheduled:  $($scheduled.Count)"
Write-Host "Successful transitions:  $transitionSucceeded"
Write-Host "=================================" -ForegroundColor Cyan