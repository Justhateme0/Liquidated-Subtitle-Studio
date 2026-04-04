@echo off
setlocal

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

set "VENV_PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "FFMPEG_BIN_DIR=%ROOT%\tools\ffmpeg\bin"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"

if /I "%~1"=="--help" goto :help
if /I "%~1"=="--dry-run" goto :dryrun

if exist "%FFMPEG_BIN_DIR%" set "PATH=%FFMPEG_BIN_DIR%;%PATH%"

powershell -NoProfile -Command ^
  "$conn = Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; " ^
  "if (-not $conn) { exit 0 }; " ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $conn.OwningProcess); " ^
  "if ($proc -and $proc.CommandLine -like '*uvicorn backend.app.main:app*') { " ^
  "  Write-Host ('Backend already running on http://%BACKEND_HOST%:%BACKEND_PORT% (PID ' + $conn.OwningProcess + ').'); exit 10 " ^
  "} " ^
  "Write-Host ('Port %BACKEND_PORT% is already in use by PID ' + $conn.OwningProcess + '. Stop that process or change the port.'); exit 11"
if errorlevel 11 exit /b 1
if errorlevel 10 exit /b 0

"%VENV_PYTHON%" -m uvicorn backend.app.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% --reload
exit /b %errorlevel%

:dryrun
echo ROOT=%ROOT%
echo VENV_PYTHON=%VENV_PYTHON%
echo FFMPEG_BIN_DIR=%FFMPEG_BIN_DIR%
echo BACKEND_HOST=%BACKEND_HOST%
echo BACKEND_PORT=%BACKEND_PORT%
exit /b 0

:help
echo Usage: run-backend.bat
echo Starts FastAPI backend with ffmpeg bin added to PATH.
exit /b 0
