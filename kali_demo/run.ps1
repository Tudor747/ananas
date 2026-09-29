# Compatibility launcher for the previous folder layout.
& (Join-Path (Split-Path -Parent $PSScriptRoot) "run.ps1") @args
