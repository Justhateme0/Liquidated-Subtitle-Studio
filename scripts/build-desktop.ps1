$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$frontendDir = Join-Path $root "frontend"
$buildDir = Join-Path $root "build"
$desktopDistDir = Join-Path $root "dist\LiquidatedSubtitleStudio"
$desktopExe = Join-Path $desktopDistDir "LiquidatedSubtitleStudio.exe"
$legacyDesktopDistDir = Join-Path $root "dist\BratSubtitleStudio"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11+ was not found in PATH."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm was not found in PATH."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating .venv..."
    python -m venv (Join-Path $root ".venv")
}

Write-Host "Installing desktop dependencies..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $root "desktop-requirements.txt")

Write-Host "Building frontend bundle..."
Push-Location -LiteralPath $frontendDir
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    & cmd /c npm.cmd install
} else {
    & cmd /c npm.cmd install
}
& cmd /c npm.cmd run build
Pop-Location

Write-Host "Ensuring ffmpeg is bundled..."
& $venvPython (Join-Path $root "scripts\bootstrap_ffmpeg.py")

if (Test-Path -LiteralPath $buildDir) {
    Remove-Item -LiteralPath $buildDir -Recurse -Force
}
if (Test-Path -LiteralPath $desktopDistDir) {
    Remove-Item -LiteralPath $desktopDistDir -Recurse -Force
}
if (Test-Path -LiteralPath $legacyDesktopDistDir) {
    Remove-Item -LiteralPath $legacyDesktopDistDir -Recurse -Force
}

Write-Host "Packaging desktop EXE..."
& $venvPython -m PyInstaller --noconfirm --clean (Join-Path $root "LiquidatedSubtitleStudio.spec")

if (-not (Test-Path -LiteralPath $desktopExe)) {
    throw "Desktop EXE was not created."
}

Write-Host ""
Write-Host "Desktop build is ready:"
Write-Host $desktopExe
