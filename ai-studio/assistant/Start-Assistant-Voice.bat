@echo off
REM Legion hands-free voice mode in the terminal (say "stop" to exit). Add --ptt for push-to-talk.
cd /d "%~dp0.."
title Legion voice
.\python_embeded\python.exe -s "%~dp0run_legion.py" voice %*
pause
