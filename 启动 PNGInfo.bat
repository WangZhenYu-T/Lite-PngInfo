@echo off
cd /d "%TEMP%"
echo Starting PNGInfo at http://127.0.0.1:8765
wsl.exe -d Ubuntu-D --exec /usr/bin/python3 /home/user1/pnginfo/app.py
pause
