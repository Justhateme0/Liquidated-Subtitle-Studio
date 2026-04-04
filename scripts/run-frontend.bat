@echo off
setlocal

if /I "%~1"=="--help" goto :help

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "FRONTEND_DIR=%ROOT%\frontend"
cd /d "%FRONTEND_DIR%"

cmd /c npm.cmd run dev
exit /b %errorlevel%

:help
echo Usage: run-frontend.bat
echo Starts Vite frontend dev server.
exit /b 0
