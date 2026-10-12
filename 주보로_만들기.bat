@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1
python -m pip install -q -r requirements.txt
if "%~1"=="" (python make_worship.py --bulletin) else (python make_worship.py "%~1")
if errorlevel 1 (pause) else (start "" output)
pause
