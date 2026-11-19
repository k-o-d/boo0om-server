@echo off
rem Double-click this file to start the Boo0om home server on Windows.
cd /d "%~dp0"

set PY=py -3
where py >nul 2>nul
if errorlevel 1 set PY=python
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo Python is not installed yet.
  echo Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and double-click this file again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo First start: setting things up. This takes a minute and needs the internet.
  %PY% -m venv .venv
  if errorlevel 1 ( echo Could not set up Python. & pause & exit /b 1 )
)
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( echo Could not download what the server needs. Check your internet and try again. & pause & exit /b 1 )

echo Starting. Leave this window open while you listen; close it to stop the server.
echo If Windows asks about the firewall, choose "Allow" for private networks.
set OPEN_BROWSER=1
if "%DEMO%"=="" set DEMO=1
.venv\Scripts\python.exe server.py
echo The server stopped.
pause
