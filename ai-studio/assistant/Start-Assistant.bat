@echo off
REM Legion web UI (chat + microphone + voice replies) at http://127.0.0.1:7860
cd /d "%~dp0.."
set COMFY_BRIDGE_DIR=%~dp0..\claude-comfy
title Legion
.\python_embeded\python.exe -s -m legion serve
pause
