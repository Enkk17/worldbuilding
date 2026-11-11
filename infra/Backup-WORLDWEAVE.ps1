$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

if (-not (Test-Path ".env")) {
    throw "No .env file exists. Start WORLDWEAVE once before creating a backup."
}

$values = @{}
foreach ($line in Get-Content ".env") {
    if ($line -match '^\s*([^#=]+)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$database = if ($values["POSTGRES_DB"]) { $values["POSTGRES_DB"] } else { "worldweave" }
$user = if ($values["POSTGRES_USER"]) { $values["POSTGRES_USER"] } else { "worldweave" }

New-Item -ItemType Directory -Path "backups" -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path (Get-Location) "backups\worldweave-$stamp.dump"
$command = "docker compose exec -T db pg_dump -U $user -d $database -Fc > `"$backupPath`""
& cmd.exe /d /c $command
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $backupPath) -or (Get-Item $backupPath).Length -eq 0) {
    throw "The database backup failed. Check that WORLDWEAVE is running and review docker compose logs."
}

$digest = (Get-FileHash -Path $backupPath -Algorithm SHA256).Hash
Set-Content -Path "$backupPath.sha256" -Value "$digest  $(Split-Path -Leaf $backupPath)" -Encoding ASCII
Write-Host "Database backup created: $backupPath"
Write-Host "SHA-256: $digest"
