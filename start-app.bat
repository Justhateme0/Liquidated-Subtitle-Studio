@echo off
setlocal

if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "PYTHON=python"
set "VENV_DIR=%ROOT%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "BACKEND_REQUIREMENTS=%ROOT%backend\requirements.txt"
set "BOOTSTRAP_FFMPEG=%ROOT%scripts\bootstrap_ffmpeg.py"
set "FRONTEND_DIR=%ROOT%frontend"
set "RUN_BACKEND=%ROOT%scripts\run-backend.bat"
set "RUN_FRONTEND=%ROOT%scripts\run-frontend.bat"

echo [1/5] Checking Python...
where %PYTHON% >nul 2>nul
if errorlevel 1 (
  echo Python was not found in PATH. Install Python 3.11+ and run again.
  exit /b 1
)

if not exist "%VENV_PYTHON%" (
  echo [2/5] Creating .venv...
  %PYTHON% -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo Failed to create virtual environment.
    exit /b 1
  )
)

echo [3/5] Installing backend dependencies...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PYTHON%" -m pip install -r "%BACKEND_REQUIREMENTS%"
if errorlevel 1 exit /b 1
"%VENV_PYTHON%" "%BOOTSTRAP_FFMPEG%"
if errorlevel 1 exit /b 1

echo [4/5] Checking frontend dependencies...
if not exist "%FRONTEND_DIR%\node_modules" (
  pushd "%FRONTEND_DIR%"
  cmd /c npm.cmd install
  if errorlevel 1 (
    popd
    echo Failed to install frontend dependencies.
    exit /b 1
  )
  popd
)

echo [5/5] Starting backend and frontend...
start "Liquidated Subtitle Studio Backend" cmd /k call "%RUN_BACKEND%"
start "Liquidated Subtitle Studio Frontend" cmd /k call "%RUN_FRONTEND%"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo.
echo First run may take a few minutes while heavy dependencies are installed.
exit /b 0

:help
echo Usage: start-app.bat
echo.
echo This script:
echo   1. Creates .venv if missing
echo   2. Installs backend dependencies
echo   3. Downloads ffmpeg into tools\ffmpeg
echo   4. Installs frontend dependencies on first run
echo   5. Opens backend and frontend in two windows
exit /b 0
