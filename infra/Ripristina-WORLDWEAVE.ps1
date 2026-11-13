param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$BackupFile,
    [Parameter(Mandatory = $false, Position = 1)]
    [string]$MediaFile
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

$backupSidecar = "$($resolvedBackup.Path).sha256"
if (Test-Path $backupSidecar) {
    $expected = ((Get-Content $backupSidecar -Raw).Trim() -split '\s+')[0]
    $actual = (Get-FileHash -Path $resolvedBackup.Path -Algorithm SHA256).Hash
    if ($expected -ne $actual) {
        throw "The selected dump does not match its SHA-256 sidecar. Refusing to restore."
    }
    Write-Host "Backup checksum verified."
} else {
    Write-Warning "No SHA-256 sidecar found for the dump; continuing without checksum verification."
}

$resolvedMedia = $null
if ($MediaFile) {
    $resolvedMedia = Resolve-Path $MediaFile -ErrorAction Stop
    $mediaSidecar = "$($resolvedMedia.Path).sha256"
    if (Test-Path $mediaSidecar) {
        $expectedMedia = ((Get-Content $mediaSidecar -Raw).Trim() -split '\s+')[0]
        $actualMedia = (Get-FileHash -Path $resolvedMedia.Path -Algorithm SHA256).Hash
        if ($expectedMedia -ne $actualMedia) {
            throw "The selected media archive does not match its SHA-256 sidecar. Refusing to restore."
        }
        Write-Host "Media checksum verified."
    } else {
        Write-Warning "No SHA-256 sidecar found for the media archive; continuing without checksum verification."
    }
} else {
    Write-Warning "No media archive supplied. User-uploaded assets will not be restored."
}

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

    if ($resolvedMedia) {
        $mediaRoot = if ($values["MEDIA_ROOT"]) { $values["MEDIA_ROOT"] } else { "/var/lib/worldweave/media" }
        $mediaRootRelative = $mediaRoot.TrimStart("/")
        $mediaCommand = "docker compose exec -T api sh -c `"rm -rf /$mediaRootRelative && mkdir -p /$mediaRootRelative && tar -C / -xf -`" < `"$($resolvedMedia.Path)`""
        & cmd.exe /d /c $mediaCommand
        if ($LASTEXITCODE -ne 0) {
            throw "The media asset restore failed. Review the API container before restarting it."
        }
        Write-Host "Media assets restored to $mediaRoot."
    }
} finally {
    docker compose start api
}

Write-Host "Database restore completed. Verify the application before continuing to use it."
