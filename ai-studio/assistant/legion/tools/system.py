"""Shell, processes, apps, clipboard, system info."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime

from . import tool

IS_WIN = sys.platform.startswith("win")


def _run(cmd: list[str] | str, timeout: int = 120, shell: bool = False, cwd: str | None = None) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=shell, cwd=cwd,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except FileNotFoundError as e:
        return f"Error: {e}"
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    out = out.strip()
    if len(out) > 12000:
        out = out[:6000] + "\n... [truncated] ...\n" + out[-4000:]
    return f"[exit {p.returncode}]\n{out}" if out else f"[exit {p.returncode}] (no output)"


@tool(dangerous=True, category="system")
def run_command(command: str, timeout_seconds: int = 120, working_dir: str | None = None) -> str:
    """Run a shell command (PowerShell on Windows, bash elsewhere) and return its output.
    command: the full command line to execute
    timeout_seconds: kill the command after this many seconds
    working_dir: directory to run in (optional)
    """
    if IS_WIN:
        return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                    timeout=timeout_seconds, cwd=working_dir)
    return _run(command, timeout=timeout_seconds, shell=True, cwd=working_dir)


@tool(dangerous=True, category="system")
def run_python(code: str, timeout_seconds: int = 120) -> str:
    """Execute a Python snippet in a fresh interpreter and return stdout/stderr.
    code: the Python source code to run
    """
    return _run([sys.executable, "-c", code], timeout=timeout_seconds)


@tool(category="system")
def open_app(name_or_path: str, args: str = "") -> str:
    """Open an application, file, folder or URL with the default handler (e.g. 'notepad', 'chrome',
    'C:\\\\Users\\\\me\\\\report.pdf', 'https://youtube.com').
    name_or_path: program name on PATH, a file/folder path, or a URL
    args: optional command-line arguments
    """
    target = os.path.expandvars(os.path.expanduser(name_or_path))
    if target.lower().startswith(("http://", "https://")):
        webbrowser.open(target)
        return f"Opened {target} in the browser"
    if os.path.exists(target) and not args:
        if IS_WIN:
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return f"Opened {target}"
    exe = shutil.which(target) or target
    try:
        if IS_WIN:
            subprocess.Popen(f'start "" "{exe}" {args}', shell=True)
        else:
            subprocess.Popen([exe] + args.split())
        return f"Launched {exe} {args}".strip()
    except Exception as e:
        return f"Error launching {target}: {e}"


@tool(category="system")
def system_info() -> dict:
    """Return OS, CPU, RAM, disk, GPU and current time information about this PC."""
    info = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)"),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "user": os.environ.get("USERNAME") or os.environ.get("USER"),
        "hostname": platform.node(),
        "cwd": os.getcwd(),
    }
    try:
        import psutil
        vm = psutil.virtual_memory()
        info["ram_gb"] = {"total": round(vm.total / 2**30, 1), "available": round(vm.available / 2**30, 1)}
        info["cpu_percent"] = psutil.cpu_percent(interval=0.2)
        info["cpu_cores"] = psutil.cpu_count()
        disks = {}
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                disks[part.mountpoint] = {"total_gb": round(u.total / 2**30), "free_gb": round(u.free / 2**30)}
            except Exception:
                pass
        info["disks"] = disks
        try:
            b = psutil.sensors_battery()
            if b:
                info["battery"] = {"percent": b.percent, "plugged_in": b.power_plugged}
        except Exception:
            pass
    except ImportError:
        info["note"] = "pip install psutil for RAM/CPU/disk details"
    gpu = _run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader"], timeout=10)
    if "[exit 0]" in gpu:
        info["gpu"] = gpu.split("\n", 1)[1].strip()
    return info


@tool(category="system")
def list_processes(filter_text: str = "", limit: int = 40) -> str:
    """List running processes (name, pid, memory), optionally filtered by name.
    filter_text: only show processes whose name contains this text
    limit: max rows
    """
    try:
        import psutil
    except ImportError:
        return _run("tasklist" if IS_WIN else "ps aux", shell=not IS_WIN)
    rows = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            n = p.info["name"] or ""
            if filter_text.lower() in n.lower():
                mem = (p.info["memory_info"].rss if p.info["memory_info"] else 0) / 2**20
                rows.append((mem, p.info["pid"], n))
        except Exception:
            continue
    rows.sort(reverse=True)
    return "\n".join(f"{pid:>7}  {mem:8.0f} MB  {n}" for mem, pid, n in rows[:limit]) or "no matching processes"


@tool(dangerous=True, category="system")
def kill_process(name_or_pid: str) -> str:
    """Terminate a process by name (e.g. 'notepad.exe') or PID.
    name_or_pid: process name or numeric PID
    """
    try:
        import psutil
    except ImportError:
        if IS_WIN:
            flag = "/PID" if name_or_pid.isdigit() else "/IM"
            return _run(["taskkill", flag, name_or_pid, "/F"])
        return _run(["pkill", "-f", name_or_pid])
    killed = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if str(p.info["pid"]) == name_or_pid or (p.info["name"] or "").lower() == name_or_pid.lower():
                p.terminate()
                killed.append(f"{p.info['name']}({p.info['pid']})")
        except Exception:
            continue
    return "Terminated: " + ", ".join(killed) if killed else f"No process matched '{name_or_pid}'"


@tool(category="system")
def get_clipboard() -> str:
    """Read the current text on the clipboard."""
    try:
        import pyperclip
        return pyperclip.paste() or "(clipboard is empty)"
    except Exception:
        if IS_WIN:
            return _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
        return "Error: pip install pyperclip"


@tool(category="system")
def set_clipboard(text: str) -> str:
    """Put text on the clipboard.
    text: the text to copy
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        return f"Copied {len(text)} characters to the clipboard"
    except Exception:
        if IS_WIN:
            p = subprocess.run(["clip"], input=text, text=True, capture_output=True)
            return "Copied to clipboard" if p.returncode == 0 else "Error copying"
        return "Error: pip install pyperclip"


@tool(dangerous=True, category="system")
def power(action: str) -> str:
    """Lock, sleep, restart or shut down the PC.
    action: one of lock | sleep | restart | shutdown | cancel_shutdown
    """
    action = action.lower().strip()
    if not IS_WIN:
        return "power actions are implemented for Windows only"
    cmds = {
        "lock": "rundll32.exe user32.dll,LockWorkStation",
        "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
        "restart": "shutdown /r /t 30 /c \"Legion restart in 30 s (run power cancel_shutdown to abort)\"",
        "shutdown": "shutdown /s /t 30 /c \"Legion shutdown in 30 s (run power cancel_shutdown to abort)\"",
        "cancel_shutdown": "shutdown /a",
    }
    if action not in cmds:
        return f"Unknown action. Use one of {list(cmds)}"
    subprocess.Popen(cmds[action], shell=True)
    return f"{action} requested"


@tool(category="system")
def set_volume(percent: int) -> str:
    """Set the master speaker volume (0-100).
    percent: volume level
    """
    percent = max(0, min(100, int(percent)))
    if not IS_WIN:
        return _run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"])
    try:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(percent / 100, None)
        return f"Volume set to {percent}%"
    except Exception:
        # fallback: nircmd-free approach via key presses (coarse)
        try:
            import pyautogui
            for _ in range(50):
                pyautogui.press("volumedown")
            for _ in range(percent // 2):
                pyautogui.press("volumeup")
            return f"Volume set to about {percent}% (key-press fallback)"
        except Exception as e:
            return f"Error: {e}. pip install pycaw comtypes"
