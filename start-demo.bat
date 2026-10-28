@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
    echo Python 3.10 or newer is required.
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo FFmpeg was not found in PATH.
    echo Install FFmpeg and restart this window.
    pause
    exit /b 1
)
where ffprobe >nul 2>&1
if errorlevel 1 (
    echo FFprobe was not found in PATH.
    pause
    exit /b 1
)
python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:8990/api/real/health',timeout=1)); sys.exit(0 if d.get('mode')=='actual-local-video-processing' else 1)" >nul 2>&1
if not errorlevel 1 (
    start "" "http://127.0.0.1:8990/"
    exit /b 0
)
python media_server.py --open
echo.
echo If the page did not open, check the error above.
pause
endlocal
