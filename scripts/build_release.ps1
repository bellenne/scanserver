param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$assetName = "ScanServer-windows-x64.zip"
$releaseDir = Join-Path $root "build\release"
$packageDir = Join-Path $releaseDir "ScanServer"
$zipPath = Join-Path $root ("build\" + $assetName)

& $Python -m pip install --upgrade pip
& $Python -m pip install pyinstaller
& $Python -m PyInstaller ScanServer.spec --noconfirm

if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

New-Item -ItemType Directory -Path $packageDir | Out-Null
Copy-Item (Join-Path $root "dist\ScanServer\*") $packageDir -Recurse -Force
Copy-Item (Join-Path $root "config.json") $packageDir -Force
Copy-Item (Join-Path $root "README.md") $packageDir -Force

Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -Force
Write-Host "Release asset created: $zipPath"
