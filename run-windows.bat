@echo off
cd /d "%TEMP%"
py -3 "%~dp0scripts\windows_launcher.py" %*
if errorlevel 1 pause
