# ============================================================================
# Run Model Management Audit Logs Migration
# ============================================================================
# This script runs the 13-model-management-audit-logs-migration.sql file 
# against the model_management_db database via Docker.
#
# Usage:
#   .\infrastructure\postgres\run-audit-logs-migration.ps1
#   OR
#   powershell -ExecutionPolicy Bypass -File .\infrastructure\postgres\run-audit-logs-migration.ps1
# ============================================================================

$ErrorActionPreference = "Stop"

# Get database connection parameters from environment or use defaults
$DB_USER = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "dhruva_user" }
$DB_PASSWORD = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "dhruva_secure_password_2024" }
$DB_NAME = "model_management_db"
$CONTAINER_NAME = "ai4v-postgres"

Write-Host "Running Model Management Audit Logs Migration..." -ForegroundColor Green

# Check if container is running
$containerRunning = docker ps --format '{{.Names}}' | Select-String -Pattern "^${CONTAINER_NAME}$"
if (-not $containerRunning) {
    Write-Host "Error: PostgreSQL container '${CONTAINER_NAME}' is not running" -ForegroundColor Red
    Write-Host "Please start it with: docker compose up -d postgres" -ForegroundColor Yellow
    exit 1
}

# Get the script directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$SQL_FILE = Join-Path $SCRIPT_DIR "13-model-management-audit-logs-migration.sql"

# Check if SQL file exists
if (-not (Test-Path $SQL_FILE)) {
    Write-Host "Error: SQL file not found: ${SQL_FILE}" -ForegroundColor Red
    exit 1
}

Write-Host "Executing SQL file: ${SQL_FILE}" -ForegroundColor Yellow
Write-Host "Target database: ${DB_NAME}" -ForegroundColor Yellow

# Copy SQL file to container
docker cp "$SQL_FILE" "${CONTAINER_NAME}:/tmp/13-model-management-audit-logs-migration.sql"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error copying SQL file to container" -ForegroundColor Red
    exit 1
}

# Execute the SQL file
# Using PGPASSWORD environment variable to avoid password prompt
$env:PGPASSWORD = $DB_PASSWORD
docker exec -i "${CONTAINER_NAME}" `
    psql -U "${DB_USER}" -d "${DB_NAME}" `
    -f /tmp/13-model-management-audit-logs-migration.sql

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Model Management Audit Logs Migration executed successfully!" -ForegroundColor Green
    Write-Host "✓ Columns added to database: ${DB_NAME}" -ForegroundColor Green
} else {
    Write-Host "✗ Error executing SQL file" -ForegroundColor Red
    exit 1
}

# Clean up temporary file
docker exec "${CONTAINER_NAME}" rm -f /tmp/13-model-management-audit-logs-migration.sql

Write-Host "Done!" -ForegroundColor Green

