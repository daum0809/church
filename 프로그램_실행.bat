@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONUTF8=1
python -m pip install -q -r requirements.txt tkinterdnd2
start "" pythonw app.py %*
