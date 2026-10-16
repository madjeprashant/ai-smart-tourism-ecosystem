@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo The project virtual environment was not found.
  echo Please run this file from the ai-smart-tourism-ecosystem project folder.
  pause
  exit /b 1
)

start "VoyageAI" /B "venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000/static/index.html"

echo VoyageAI is running. Keep this window open while using the project.
echo Press Ctrl+C to stop the server.
pause
