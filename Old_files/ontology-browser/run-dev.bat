@echo off
REM Launch ASK-DB Ontology Browser (works even if npm is not on PATH)
set "NODE_DIR=C:\Program Files\nodejs"
if not exist "%NODE_DIR%\npm.cmd" (
  echo Node.js not found at "%NODE_DIR%".
  echo Install from https://nodejs.org then reopen this window.
  pause
  exit /b 1
)

cd /d "%~dp0"

echo Using: %NODE_DIR%\npm.cmd
echo.

"%NODE_DIR%\npm.cmd" install
if errorlevel 1 (
  echo npm install failed.
  pause
  exit /b 1
)

echo.
echo Starting Ontology Browser at http://localhost:5173
echo Press Ctrl+C to stop.
echo.

"%NODE_DIR%\npm.cmd" run dev
pause
