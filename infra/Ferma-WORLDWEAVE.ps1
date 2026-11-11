$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

docker compose down
if ($LASTEXITCODE -ne 0) {
    throw "WORLDWEAVE could not be stopped cleanly."
}

Write-Host "WORLDWEAVE stopped. Database data was preserved."
