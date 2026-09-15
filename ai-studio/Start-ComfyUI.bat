@echo off
REM Starts ComfyUI portable with settings for a 16 GB laptop GPU and the Claude bridge.
REM Extra ComfyUI flags can be appended, e.g.  Start-ComfyUI.bat --lowvram
cd /d "%~dp0"
title ComfyUI
echo Starting ComfyUI ... the browser opens at http://127.0.0.1:8188 when ready. Keep this window open.
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --enable-manager --preview-method auto --listen 127.0.0.1 --port 8188 %*
echo.
echo ComfyUI stopped. If it crashed, read the error above (out of memory: try Start-ComfyUI.bat --lowvram).
pause
