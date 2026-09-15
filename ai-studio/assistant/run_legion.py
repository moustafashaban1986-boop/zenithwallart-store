"""Launcher for Legion that works with ComfyUI's embedded Python.

The portable Python ships a python3xx._pth file, which makes the interpreter ignore
PYTHONPATH and the current directory, so ``python -m legion`` cannot find the package.
Running this file by path always works:

    C:\\ComfyUI\\python_embeded\\python.exe -s C:\\ComfyUI\\legion\\run_legion.py serve
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
os.environ.setdefault("COMFY_BRIDGE_DIR", os.path.join(os.path.dirname(HERE), "claude-comfy"))

from legion.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
