$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required. Install and start Docker Desktop, then run this script again."
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is unavailable. Update Docker Desktop and retry."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is installed but is not running. Start it and retry."
}

if (-not (Test-Path ".env") -or (Get-Content ".env" -Raw) -match "GENERATE_ON_FIRST_START") {
    $randomBytes = New-Object byte[] 32
    $randomGenerator = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $randomGenerator.GetBytes($randomBytes)
    $randomGenerator.Dispose()
    $generatedPassword = [System.BitConverter]::ToString($randomBytes).Replace("-", "").ToLowerInvariant()
    $contents = (Get-Content ".env.example" -Raw).Replace("GENERATE_ON_FIRST_START", $generatedPassword)
    Set-Content -Path ".env" -Value $contents -Encoding ASCII
    Write-Host "Created a private .env file with a random database password."
}

docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "The Docker Compose configuration is invalid. Review .env and docker-compose.yml."
}

docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "WORLDWEAVE failed to start. Run 'docker compose logs' to inspect the service output."
}

$ready = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/readyz" -TimeoutSec 3
        if ($status.status -eq "ready") {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    docker compose logs --tail 80
    throw "WORLDWEAVE did not become ready within three minutes."
}

Write-Host "WORLDWEAVE is ready at http://localhost:8080"
Start-Process "http://localhost:8080"
