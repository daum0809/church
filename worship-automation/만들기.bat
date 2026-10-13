@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1
python -m pip install -q -r requirements.txt
python make_worship.py
if errorlevel 1 (pause) else (start "" output)
pause
