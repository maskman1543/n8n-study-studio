@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 --version >nul 2>nul
    if not errorlevel 1 (
    start "Study Studio Server" cmd /k "cd /d ""%~dp0"" && set STUDY_STUDIO_PORT=8001 && py -3 server.py"
        goto open_app
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    start "Study Studio Server" cmd /k "cd /d ""%~dp0"" && set STUDY_STUDIO_PORT=8001 && python server.py"
    goto open_app
)

echo Python was not found. Install Python, then click this file again.
pause
exit /b 1

:open_app
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8001"
endlocal
