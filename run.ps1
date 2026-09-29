param([int]$Port = 0)
$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if ($Port -eq 0) {
    $Port = if ($env:PI_OT_DEMO_PORT) { [int]$env:PI_OT_DEMO_PORT } else { 8088 }
}
if ($Port -lt 1 -or $Port -gt 65535) { throw "Port must be between 1 and 65535." }

# Keep dependencies isolated from your system Python.
if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvDir
    } else {
        & python -m venv $venvDir
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment." }
}
Push-Location -LiteralPath $projectRoot
try {
    # Editable installation means source edits are used immediately.
    & $venvPython -m pip install --quiet --editable $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not install project dependencies." }
    Write-Host "Website: http://127.0.0.1:$Port (Ctrl+C to stop)"
    & $venvPython -m uvicorn pi_ot_probe.web.app:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw "The website could not start or stopped with an error." }
} finally {
    Pop-Location
}
