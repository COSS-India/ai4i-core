# PowerShell script to quickly check alert status on Windows
# Run: .\scripts\quick-alert-check.ps1

Write-Host "=== Quick Alert Status Check ===" -ForegroundColor Cyan
Write-Host ""

# 1. Check Prometheus
Write-Host "1. Checking Prometheus..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9090/-/healthy" -UseBasicParsing -TimeoutSec 5
    Write-Host "   ✅ Prometheus is running" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Prometheus is not accessible" -ForegroundColor Red
    exit
}

# 2. Check if alerts are firing
Write-Host ""
Write-Host "2. Checking for FIRING alerts..." -ForegroundColor Yellow
try {
    $alerts = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/alerts"
    $firing = $alerts.data.alerts | Where-Object { $_.state -eq "firing" }
    if ($firing) {
        Write-Host "   ✅ Found $($firing.Count) firing alert(s):" -ForegroundColor Green
        $firing | ForEach-Object {
            Write-Host "      - $($_.labels.alertname): $($_.state)" -ForegroundColor White
        }
    } else {
        Write-Host "   ❌ No alerts are currently FIRING" -ForegroundColor Red
        Write-Host "   Checking all alert states:" -ForegroundColor Yellow
        $alerts.data.alerts | ForEach-Object {
            Write-Host "      - $($_.labels.alertname): $($_.state)" -ForegroundColor White
        }
    }
} catch {
    Write-Host "   ❌ Could not fetch alerts: $_" -ForegroundColor Red
}

# 3. Check if metrics exist
Write-Host ""
Write-Host "3. Checking if metrics exist..." -ForegroundColor Yellow
try {
    $query = [System.Web.HttpUtility]::UrlEncode('telemetry_obsv_request_duration_seconds_bucket')
    $result = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=$query"
    $count = $result.data.result.Count
    Write-Host "   Found $count metric series" -ForegroundColor $(if ($count -gt 0) { "Green" } else { "Red" })
    
    if ($count -eq 0) {
        Write-Host "   ⚠️  No metrics found! This is likely the problem." -ForegroundColor Red
        Write-Host "   Check if services are emitting metrics with organization label" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Could not query metrics: $_" -ForegroundColor Red
}

# 4. Check metrics with organization label
Write-Host ""
Write-Host "4. Checking metrics with organization label..." -ForegroundColor Yellow
$orgs = @("kisanmitra", "bashadaan", "irctc", "beml")
foreach ($org in $orgs) {
    try {
        $query = [System.Web.HttpUtility]::UrlEncode("telemetry_obsv_request_duration_seconds_bucket{organization=`"$org`"}")
        $result = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=$query"
        $count = $result.data.result.Count
        Write-Host "   $org : $count series" -ForegroundColor $(if ($count -gt 0) { "Green" } else { "Red" })
    } catch {
        Write-Host "   $org : Error checking" -ForegroundColor Red
    }
}

# 5. Test alert query manually
Write-Host ""
Write-Host "5. Testing alert query for kisanmitra..." -ForegroundColor Yellow
try {
    $query = [System.Web.HttpUtility]::UrlEncode('histogram_quantile(0.5, sum by (le, endpoint) (rate(telemetry_obsv_request_duration_seconds_bucket{endpoint=~"/.*inference.*", organization="kisanmitra"}[5m]))) > 0.1')
    $result = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=$query"
    if ($result.data.result.Count -gt 0) {
        Write-Host "   ✅ Query returns results (alert should fire if threshold exceeded):" -ForegroundColor Green
        $result.data.result | ForEach-Object {
            $endpoint = $_.metric.endpoint
            $value = $_.value[1]
            Write-Host "      Endpoint: $endpoint, Value: ${value}s" -ForegroundColor White
        }
    } else {
        Write-Host "   ❌ Query returns no results" -ForegroundColor Red
        Write-Host "   Possible reasons:" -ForegroundColor Yellow
        Write-Host "      - No metrics with organization='kisanmitra'" -ForegroundColor White
        Write-Host "      - No metrics matching endpoint pattern '/.*inference.*'" -ForegroundColor White
        Write-Host "      - Latency is below threshold (0.1s)" -ForegroundColor White
    }
} catch {
    Write-Host "   ❌ Could not test query: $_" -ForegroundColor Red
}

# 6. Check Alertmanager
Write-Host ""
Write-Host "6. Checking Alertmanager..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:9095/-/healthy" -UseBasicParsing -TimeoutSec 5
    Write-Host "   ✅ Alertmanager is running" -ForegroundColor Green
    
    $amAlerts = Invoke-RestMethod -Uri "http://localhost:9095/api/v2/alerts"
    if ($amAlerts.data.Count -gt 0) {
        Write-Host "   ✅ Found $($amAlerts.data.Count) alert(s) in Alertmanager" -ForegroundColor Green
    } else {
        Write-Host "   ❌ No alerts in Alertmanager" -ForegroundColor Red
        Write-Host "   This means Prometheus is not sending alerts to Alertmanager" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   ❌ Alertmanager is not accessible: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Next Steps ===" -ForegroundColor Cyan
Write-Host "1. If no metrics: Check if services are running and emitting metrics" -ForegroundColor White
Write-Host "2. If metrics exist but no alerts: Check if latency exceeds thresholds" -ForegroundColor White
Write-Host "3. If alerts firing but no emails: Check Alertmanager logs and route matching" -ForegroundColor White
Write-Host ""
Write-Host "For detailed diagnostics, see: docs/ALERT-TROUBLESHOOTING.md" -ForegroundColor Cyan
