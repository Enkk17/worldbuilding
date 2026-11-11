param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "infra\Ripristina-WORLDWEAVE.ps1") -BackupFile $BackupFile
