# =============================================================================
# KMS System Export Script for Migration (Windows PowerShell)
# Export all components for migration to Redhat Linux 64-bit GPU environment
# =============================================================================
# Usage: .\export_system.ps1 [-OutputDir <path>]
# =============================================================================

param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

# Configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "migration_export_$Timestamp"
}
$ArchiveName = "kms_migration_$Timestamp.tar.gz"

# =============================================================================
# Logging Functions
# =============================================================================
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }
function Write-Step { param($Message) Write-Host "[STEP] $Message" -ForegroundColor Cyan }

# =============================================================================
# Load Environment
# =============================================================================
function Load-Environment {
    Write-Step "Loading environment variables..."

    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^([^#][^=]+)=(.*)$") {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
        Write-Info "Loaded environment from .env"
    } else {
        Write-Warn "No .env file found - using defaults"
    }
}

# =============================================================================
# Create Export Directory Structure
# =============================================================================
function Setup-ExportDir {
    Write-Step "Creating export directory structure..."

    $dirs = @("database", "source", "config", "docker", "neo4j", "logs")
    foreach ($dir in $dirs) {
        $path = Join-Path $OutputDir $dir
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }

    Write-Info "Export directory: $OutputDir"
}

# =============================================================================
# Export PostgreSQL Database
# =============================================================================
function Export-PostgreSQL {
    Write-Step "Exporting PostgreSQL database..."

    $pgHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }
    $pgPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { "5432" }
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "raguser" }
    $pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "ragdb" }
    $pgPassword = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "ragpassword" }

    $env:PGPASSWORD = $pgPassword

    try {
        # Export schema
        Write-Info "Exporting PostgreSQL schema..."
        $schemaFile = Join-Path $OutputDir "database\schema.sql"
        & pg_dump -h $pgHost -p $pgPort -U $pgUser -d $pgDb --schema-only --no-owner --no-privileges -f $schemaFile 2>$null

        # Export data
        Write-Info "Exporting PostgreSQL data..."
        $dataFile = Join-Path $OutputDir "database\data.sql"
        & pg_dump -h $pgHost -p $pgPort -U $pgUser -d $pgDb --data-only --no-owner --no-privileges -f $dataFile 2>$null

        # Full dump
        Write-Info "Creating complete database dump..."
        $dumpFile = Join-Path $OutputDir "database\full_dump.pgdump"
        & pg_dump -h $pgHost -p $pgPort -U $pgUser -d $pgDb --no-owner --no-privileges -Fc -f $dumpFile 2>$null
    }
    catch {
        Write-Warn "pg_dump failed - copying migration files instead"
    }

    # Always copy migration SQL files
    Write-Info "Copying migration SQL files..."
    $migrationsDir = Join-Path $ProjectRoot "migrations"
    if (Test-Path $migrationsDir) {
        Copy-Item -Path "$migrationsDir\*.sql" -Destination (Join-Path $OutputDir "database") -Force -ErrorAction SilentlyContinue
    }

    Write-Info "PostgreSQL export completed"
}

# =============================================================================
# Export Neo4j Data
# =============================================================================
function Export-Neo4j {
    Write-Step "Exporting Neo4j data..."

    $neo4jDataDir = Join-Path $ProjectRoot "neo4j\data"
    $neo4jExportDir = Join-Path $OutputDir "neo4j"

    if (Test-Path $neo4jDataDir) {
        Write-Info "Copying Neo4j data directory..."
        Copy-Item -Path $neo4jDataDir -Destination $neo4jExportDir -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warn "Neo4j data directory not found at $neo4jDataDir"
    }

    # Copy plugins if exist
    $pluginsDir = Join-Path $ProjectRoot "neo4j\plugins"
    if (Test-Path $pluginsDir) {
        Copy-Item -Path $pluginsDir -Destination $neo4jExportDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Info "Neo4j export completed"
}

# =============================================================================
# Export Source Code
# =============================================================================
function Export-Source {
    Write-Step "Exporting source code..."

    $sourceDir = Join-Path $OutputDir "source"

    # Export backend
    Write-Info "Exporting backend source..."
    $appSrc = Join-Path $ProjectRoot "app"
    $appDst = Join-Path $sourceDir "app"
    Copy-Item -Path $appSrc -Destination $appDst -Recurse -Force

    # Export frontend (excluding node_modules and dist)
    Write-Info "Exporting frontend source..."
    $frontendSrc = Join-Path $ProjectRoot "kms-portal-ui"
    $frontendDst = Join-Path $sourceDir "kms-portal-ui"

    # Create destination directory
    New-Item -ItemType Directory -Force -Path $frontendDst | Out-Null

    # Copy files excluding node_modules and dist
    Get-ChildItem -Path $frontendSrc -Exclude @("node_modules", "dist", ".git") | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $frontendDst -Recurse -Force
    }

    # Export scripts
    Write-Info "Exporting utility scripts..."
    $scriptsSrc = Join-Path $ProjectRoot "scripts"
    $scriptsDst = Join-Path $sourceDir "scripts"
    Copy-Item -Path $scriptsSrc -Destination $scriptsDst -Recurse -Force

    # Export tests
    Write-Info "Exporting test files..."
    $testsSrc = Join-Path $ProjectRoot "tests"
    if (Test-Path $testsSrc) {
        $testsDst = Join-Path $sourceDir "tests"
        Copy-Item -Path $testsSrc -Destination $testsDst -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Export migrations
    Write-Info "Exporting migrations..."
    $migrationsSrc = Join-Path $ProjectRoot "migrations"
    if (Test-Path $migrationsSrc) {
        $migrationsDst = Join-Path $sourceDir "migrations"
        Copy-Item -Path $migrationsSrc -Destination $migrationsDst -Recurse -Force
    }

    # Export docs
    $docsSrc = Join-Path $ProjectRoot "docs"
    if (Test-Path $docsSrc) {
        $docsDst = Join-Path $sourceDir "docs"
        Copy-Item -Path $docsSrc -Destination $docsDst -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Info "Source code export completed"
}

# =============================================================================
# Export Configuration Files
# =============================================================================
function Export-Config {
    Write-Step "Exporting configuration files..."

    $configDir = Join-Path $OutputDir "config"

    # Copy environment example
    $envExample = Join-Path $ProjectRoot ".env.example"
    if (Test-Path $envExample) {
        Copy-Item -Path $envExample -Destination $configDir -Force
    }

    # Copy requirements
    $reqApi = Join-Path $ProjectRoot "requirements-api.txt"
    if (Test-Path $reqApi) {
        Copy-Item -Path $reqApi -Destination $configDir -Force
    }

    $reqApp = Join-Path $ProjectRoot "app\requirements.txt"
    if (Test-Path $reqApp) {
        Copy-Item -Path $reqApp -Destination $configDir -Force
    }

    # Copy package.json for frontend
    $pkgJson = Join-Path $ProjectRoot "kms-portal-ui\package.json"
    if (Test-Path $pkgJson) {
        Copy-Item -Path $pkgJson -Destination (Join-Path $configDir "frontend-package.json") -Force
    }

    $pkgLock = Join-Path $ProjectRoot "kms-portal-ui\package-lock.json"
    if (Test-Path $pkgLock) {
        Copy-Item -Path $pkgLock -Destination (Join-Path $configDir "frontend-package-lock.json") -Force
    }

    # Copy Docker configuration
    $dockerDir = Join-Path $ProjectRoot "docker"
    if (Test-Path $dockerDir) {
        Copy-Item -Path $dockerDir -Destination (Join-Path $OutputDir "docker") -Recurse -Force
    }

    # Copy CLAUDE.md files
    $claudeMd = Join-Path $ProjectRoot "CLAUDE.md"
    if (Test-Path $claudeMd) {
        Copy-Item -Path $claudeMd -Destination $configDir -Force
    }

    # Generate pip freeze
    Write-Info "Generating Python dependency list..."
    try {
        $pipFreeze = & pip freeze 2>$null
        $pipFreeze | Out-File -FilePath (Join-Path $configDir "pip_freeze.txt") -Encoding UTF8
    }
    catch {
        Write-Warn "pip freeze failed - using requirements file"
    }

    Write-Info "Configuration export completed"
}

# =============================================================================
# Copy Installation Scripts
# =============================================================================
function Copy-InstallScripts {
    Write-Step "Copying installation scripts for target system..."

    $setupScript = Join-Path $ScriptDir "setup_target.sh"
    $deployScript = Join-Path $ScriptDir "deploy.sh"

    if (Test-Path $setupScript) {
        Copy-Item -Path $setupScript -Destination $OutputDir -Force
    }

    if (Test-Path $deployScript) {
        Copy-Item -Path $deployScript -Destination $OutputDir -Force
    }

    Write-Info "Installation scripts copied"
}

# =============================================================================
# Generate Migration Report
# =============================================================================
function Generate-Report {
    Write-Step "Generating migration report..."

    $reportFile = Join-Path $OutputDir "MIGRATION_REPORT.md"

    $report = @"
# KMS System Migration Report

**Generated:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
**Source System:** Windows $(Get-WmiObject -Class Win32_OperatingSystem | Select-Object -ExpandProperty Caption)

## Exported Components

### 1. Database
- PostgreSQL schema: ``database/schema.sql``
- PostgreSQL data: ``database/data.sql``
- Full dump: ``database/full_dump.pgdump``
- Migration scripts: ``database/*.sql``

### 2. Source Code
- Backend API: ``source/app/``
- Frontend UI: ``source/kms-portal-ui/``
- Scripts: ``source/scripts/``
- Tests: ``source/tests/``

### 3. Configuration
- Environment template: ``config/.env.example``
- Python requirements: ``config/requirements-api.txt``
- Frontend packages: ``config/frontend-package.json``
- Docker compose: ``docker/docker-compose.yml``

### 4. Neo4j Data
- Data directory: ``neo4j/data/``
- Plugins: ``neo4j/plugins/``

## Target System Requirements

### Hardware
- CPU: 8+ cores recommended
- RAM: 64GB+ recommended
- GPU: NVIDIA A100 or equivalent (8x for full deployment)
- Storage: 500GB+ SSD

### Software
- OS: Red Hat Enterprise Linux 8/9 (64-bit)
- Python: 3.10+
- Node.js: 18+ LTS
- Docker: 24.0+
- NVIDIA Driver: 535+
- CUDA: 12.0+

## Installation Instructions

1. Transfer archive to target system
2. Extract: ``tar -xzvf kms_migration_$Timestamp.tar.gz``
3. Run setup: ``sudo ./setup_target.sh``
4. Configure: Edit ``.env`` file
5. Deploy: ``sudo ./deploy.sh``

## Port Allocations

| Port  | Service              |
|-------|----------------------|
| 3000  | React Frontend       |
| 9000  | FastAPI Backend      |
| 5432  | PostgreSQL           |
| 7474  | Neo4j HTTP           |
| 7687  | Neo4j Bolt           |
| 12800 | Nemotron LLM         |
| 12801 | NeMo Embedding       |
| 12802 | Mistral Code LLM     |

## Post-Installation Checklist

- [ ] Generate new JWT_SECRET_KEY
- [ ] Generate new ENCRYPTION_MASTER_KEY
- [ ] Generate new ENCRYPTION_SALT
- [ ] Set NEO4J_PASSWORD
- [ ] Set POSTGRES_PASSWORD
- [ ] Configure NGC_API_KEY for NVIDIA NIMs
- [ ] Verify GPU availability with ``nvidia-smi``
- [ ] Run database migrations
- [ ] Test all services
"@

    $report | Out-File -FilePath $reportFile -Encoding UTF8

    Write-Info "Migration report generated: $reportFile"
}

# =============================================================================
# Create Archive
# =============================================================================
function Create-Archive {
    Write-Step "Creating migration archive..."

    $parentDir = Split-Path -Parent $OutputDir
    $archivePath = Join-Path $parentDir $ArchiveName
    $folderName = Split-Path -Leaf $OutputDir

    # Try tar if available (Git Bash or WSL)
    try {
        Push-Location $parentDir
        & tar -czvf $ArchiveName $folderName 2>$null
        Pop-Location
        Write-Info "Archive created: $archivePath"
    }
    catch {
        # Fallback to zip
        Write-Warn "tar not available - creating zip archive instead"
        $zipPath = Join-Path $parentDir "kms_migration_$Timestamp.zip"
        Compress-Archive -Path $OutputDir -DestinationPath $zipPath -Force
        Write-Info "Zip archive created: $zipPath"
    }
}

# =============================================================================
# Main Execution
# =============================================================================
function Main {
    Write-Host "=============================================="
    Write-Host " KMS System Export for Migration"
    Write-Host " Target: Redhat Linux 64-bit GPU Environment"
    Write-Host "=============================================="
    Write-Host ""

    Load-Environment
    Setup-ExportDir
    Export-PostgreSQL
    Export-Neo4j
    Export-Source
    Export-Config
    Copy-InstallScripts
    Generate-Report
    Create-Archive

    Write-Host ""
    Write-Host "=============================================="
    Write-Info "Export completed successfully!"
    Write-Host "=============================================="
    Write-Host ""
    Write-Host "Export directory: $OutputDir"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "1. Transfer the archive to the target RHEL system"
    Write-Host "2. Extract: tar -xzvf kms_migration_$Timestamp.tar.gz"
    Write-Host "3. Run: sudo ./setup_target.sh"
    Write-Host "4. Configure .env file"
    Write-Host "5. Run: sudo ./deploy.sh"
    Write-Host ""
}

Main
