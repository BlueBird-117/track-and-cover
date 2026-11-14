$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $AppRoot

py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean --onefile --windowed `
    --name "TrackAndCover" --collect-all mutagen --collect-all PIL --collect-all certifi `
    --icon "assets\app.ico" --add-data "assets;assets" `
    --add-data "licenses;licenses" app.py

Write-Host "Built: $AppRoot\dist\TrackAndCover.exe"
