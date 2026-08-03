$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

# Locate a python interpreter (prefer PATH, then managed WorkBuddy python)
$py = 'python'
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    $py = Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions\3.13.12\python.exe'
}
if (-not (Test-Path $py)) {
    $py = 'C:\Users\dillon\.workbuddy\binaries\python\versions\3.13.12\python.exe'
}

Write-Host '[Console] Scanning WorkBuddy data into console.html ...'
& $py (Join-Path $root 'scripts\scan_console.py')

Write-Host '[Console] Starting backend at http://127.0.0.1:8080 ...'
Start-Process $py -ArgumentList (Join-Path $root 'scripts\server.py')

Start-Sleep -Seconds 2
Start-Process 'http://127.0.0.1:8080/console.html'
