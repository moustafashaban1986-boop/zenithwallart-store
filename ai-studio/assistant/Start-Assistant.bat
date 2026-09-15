@echo off
REM Legion web UI (chat + microphone + voice replies) at http://127.0.0.1:7860
cd /d "%~dp0.."
title Legion
.\python_embeded\python.exe -s "%~dp0run_legion.py" serve
pause
