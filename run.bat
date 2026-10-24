@echo off
set "PATH=%PATH%;C:\ffmpeg\bin"
echo Starting YT Playlist Merger...
py "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Application closed with an error.
    pause
)
