$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $root ".venv\\Scripts\\python.exe"
$python = $(if (Test-Path $venvPython) { $venvPython } else { "python" })
$ffmpegBin = Join-Path $root "tools\\ffmpeg\\bin"
$backendCommand = "if (Test-Path '$ffmpegBin') { `$env:PATH = '$ffmpegBin;' + `$env:PATH }; & '$python' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand -WorkingDirectory $root
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cmd /c npm.cmd run dev" -WorkingDirectory $frontend

Write-Host "Started backend on http://127.0.0.1:8000 and frontend on http://127.0.0.1:5173"
