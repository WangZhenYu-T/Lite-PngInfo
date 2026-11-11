@echo off
cd /d "%TEMP%"
py -3 "%~dp0scripts\windows_launcher.py" --open-browser %*
if errorlevel 1 pause
