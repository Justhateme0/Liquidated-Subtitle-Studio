$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$installerScript = Join-Path $root "LiquidatedSubtitleStudio.iss"
$installerOutput = Join-Path $root "dist\installer\LiquidatedSubtitleStudioSetup.exe"
$legacyInstallerOutput = Join-Path $root "dist\installer\BratSubtitleStudioSetup.exe"
$assetScript = Join-Path $root "scripts\generate-installer-assets.ps1"

function Get-IsccPath {
    $command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $registryInstall = Get-ItemProperty `
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', `
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*', `
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -like 'Inno Setup*' } |
        Select-Object -First 1 -ExpandProperty InstallLocation

    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        $(if ($registryInstall) { Join-Path $registryInstall "ISCC.exe" })
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    return $null
}

$iscc = Get-IsccPath
if (-not $iscc) {
    Write-Host "Installing Inno Setup..."
    winget install --exact --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --silent
    $iscc = Get-IsccPath
}

if (-not $iscc) {
    throw "Inno Setup compiler was not found."
}

Write-Host "Building desktop bundle..."
powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\build-desktop.ps1")

$appVersion = (& $venvPython -c "from backend.app.config import APP_VERSION; print(APP_VERSION)").Trim()

Write-Host "Generating installer assets..."
powershell -ExecutionPolicy Bypass -File $assetScript -Version $appVersion

if (Test-Path -LiteralPath $legacyInstallerOutput) {
    Remove-Item -LiteralPath $legacyInstallerOutput -Force
}

Write-Host "Building installer..."
& $iscc "/DMyAppVersion=$appVersion" $installerScript

if (-not (Test-Path -LiteralPath $installerOutput)) {
    throw "Installer EXE was not created."
}

Write-Host ""
Write-Host "Installer build is ready:"
Write-Host $installerOutput
