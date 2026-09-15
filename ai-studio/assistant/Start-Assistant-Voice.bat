@echo off
REM Legion hands-free voice mode in the terminal (say "stop" to exit). Add --ptt for push-to-talk.
cd /d "%~dp0.."
set COMFY_BRIDGE_DIR=%~dp0..\claude-comfy
title Legion voice
.\python_embeded\python.exe -s -m legion voice %*
pause
