$ErrorActionPreference = "Stop"

$demoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $demoDir
$venvDir = Join-Path $demoDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$port = if ($env:PI_OT_DEMO_PORT) { $env:PI_OT_DEMO_PORT } else { "8088" }

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating Windows demo virtual environment..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvDir
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvDir
    } else {
        throw "Python 3 is required. Install it from https://www.python.org/downloads/windows/"
    }
}

$nmapCandidates = @(
    (Get-Command nmap -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    (Join-Path ${env:ProgramFiles} "Nmap\nmap.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Nmap\nmap.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $nmapCandidates) {
    throw "Nmap for Windows is required. Install it from https://nmap.org/download"
}

& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet --editable $projectRoot

Write-Host "Pi-OT Windows discovery app: http://127.0.0.1:$port"
Write-Host "Select only a network you are authorized to assess. Press Ctrl+C to stop."
& $venvPython -m uvicorn kali_demo.app:app `
    --app-dir $projectRoot `
    --host 127.0.0.1 `
    --port $port
