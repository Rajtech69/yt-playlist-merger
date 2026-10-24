@echo off
set "PATH=%PATH%;C:\ffmpeg\bin"
echo ========================================================
echo  Starting Visual Timeline Video Editor Studio...
echo ========================================================
echo.
py "%~dp0editor_backend.py"
if errorlevel 1 (
    echo.
    echo Server closed with an error.
    pause
)
