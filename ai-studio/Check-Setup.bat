@echo off
REM Checks that ComfyUI is running, the GPU is visible and which model files are installed.
cd /d "%~dp0"
.\python_embeded\python.exe -s claude-comfy\cli.py status
echo.
pause
