@echo off
cd /d "%TEMP%"
start "BunnyInfo" wsl.exe -d Ubuntu-D --exec /usr/bin/python3 /home/user1/pnginfo/app.py
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8765"
