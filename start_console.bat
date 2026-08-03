@echo off
setlocal
cd /d "%~dp0"
REM Locate a python interpreter (prefer PATH, then managed WorkBuddy python)
set "PY=python"
where python >nul 2>nul || set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=C:\Users\dillon\.workbuddy\binaries\python\versions\3.13.12\python.exe"

echo [Console] Scanning WorkBuddy data into console.html ...
"%PY%" scripts\scan_console.py

echo [Console] Starting backend at http://127.0.0.1:8080 ...
start "" "%PY%" scripts\server.py

timeout /t 2 >nul
start "" http://127.0.0.1:8080/console.html
endlocal
