@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or newer, then try again.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8989/api/health',timeout=1)); sys.exit(0 if d.get('mode')=='structured-demo-only' else 1)" >nul 2>&1
if not errorlevel 1 (
    start "" "http://127.0.0.1:8989/"
    exit /b 0
)
python portfolio.py serve --open
echo.
echo If the page did not open, inspect the error message above.
pause
endlocal
