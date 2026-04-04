$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root ".venv"

if (-not (Test-Path $venv)) {
  python -m venv $venv
}

$venvPython = Join-Path $venv "Scripts\\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $root "backend\\requirements.txt")
& $venvPython (Join-Path $root "scripts\\bootstrap_ffmpeg.py")

Write-Host "Backend bootstrap completed."
