param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

$resolvedBackup = Resolve-Path $BackupFile -ErrorAction Stop
if (-not (Test-Path ".env")) {
    throw "No .env file exists. Start WORLDWEAVE before restoring a database."
}

$values = @{}
foreach ($line in Get-Content ".env") {
    if ($line -match '^\s*([^#=]+)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}
$database = if ($values["POSTGRES_DB"]) { $values["POSTGRES_DB"] } else { "worldweave" }
$user = if ($values["POSTGRES_USER"]) { $values["POSTGRES_USER"] } else { "worldweave" }

Write-Warning "This replaces the current WORLDWEAVE database with the selected backup."
$confirmation = Read-Host "Type RESTORE WORLDWEAVE to continue"
if ($confirmation -cne "RESTORE WORLDWEAVE") {
    Write-Host "Restore cancelled."
    exit 0
}

docker compose stop api
if ($LASTEXITCODE -ne 0) {
    throw "The API could not be stopped; the database was not restored."
}

try {
    $command = "docker compose exec -T db pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error -U $user -d $database - < `"$($resolvedBackup.Path)`""
    & cmd.exe /d /c $command
    if ($LASTEXITCODE -ne 0) {
        throw "The restore failed. Review the database logs before restarting the API."
    }
} finally {
    docker compose start api
}

Write-Host "Database restore completed. Verify the application before continuing to use it."
