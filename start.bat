@echo off
title YouTube Video Yuklovchi
echo ====================================
echo   YouTube Video Yuklovchi ishga tushmoqda...
echo ====================================
cd /d "%~dp0"
start "" "http://127.0.0.1:5000"
python app.py
pause
