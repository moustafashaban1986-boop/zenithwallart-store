"""Screen, mouse, keyboard and window control (pyautogui / pygetwindow)."""
from __future__ import annotations

import base64
import io
import sys
import time
from pathlib import Path

from . import tool
from ..config import data_dir


def _pag():
    import pyautogui
    pyautogui.FAILSAFE = True  # slam the mouse into the top-left corner to abort
    pyautogui.PAUSE = 0.05
    return pyautogui


@tool(category="desktop")
def screenshot(save_to: str | None = None, region: str | None = None) -> dict:
    """Take a screenshot of the whole screen (or a region) and save it as PNG.
    Returns the file path so the assistant can look at it with view_image.
    save_to: optional output path (default: Legion data folder)
    region: optional 'x,y,width,height'
    """
    pag = _pag()
    kwargs = {}
    if region:
        x, y, w, h = [int(v) for v in region.split(",")]
        kwargs["region"] = (x, y, w, h)
    img = pag.screenshot(**kwargs)
    path = Path(save_to) if save_to else data_dir() / "screenshots" / f"shot_{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return {"path": str(path), "size": img.size}


@tool(category="desktop")
def screen_size() -> dict:
    """Return the screen resolution and the current mouse position."""
    pag = _pag()
    w, h = pag.size()
    x, y = pag.position()
    return {"width": w, "height": h, "mouse_x": x, "mouse_y": y}


@tool(dangerous=True, category="desktop")
def mouse(action: str, x: int | None = None, y: int | None = None, button: str = "left", clicks: int = 1,
          amount: int = 0) -> str:
    """Move or click the mouse.
    action: move | click | double_click | right_click | scroll | drag_to
    x: screen x coordinate (optional for scroll)
    y: screen y coordinate
    button: left | right | middle
    clicks: number of clicks
    amount: scroll amount (positive = up, negative = down)
    """
    pag = _pag()
    a = action.lower()
    if a == "move" and x is not None:
        pag.moveTo(x, y, duration=0.2)
    elif a == "click":
        pag.click(x=x, y=y, clicks=clicks, button=button)
    elif a == "double_click":
        pag.doubleClick(x=x, y=y)
    elif a == "right_click":
        pag.rightClick(x=x, y=y)
    elif a == "scroll":
        pag.scroll(amount, x=x, y=y)
    elif a == "drag_to" and x is not None:
        pag.dragTo(x, y, duration=0.4, button=button)
    else:
        return f"Unknown mouse action '{action}'"
    return f"mouse {a} done at {pag.position()}"


@tool(dangerous=True, category="desktop")
def keyboard(action: str, text: str = "", keys: str = "") -> str:
    """Type text or press keys.
    action: type | press | hotkey
    text: text to type when action=type
    keys: key name for press (enter, tab, esc, f5 ...) or combination for hotkey like 'ctrl+s' or 'win+d'
    """
    pag = _pag()
    a = action.lower()
    if a == "type":
        pag.write(text, interval=0.01)
        return f"typed {len(text)} chars"
    if a == "press":
        pag.press(keys)
        return f"pressed {keys}"
    if a == "hotkey":
        pag.hotkey(*[k.strip() for k in keys.split("+")])
        return f"hotkey {keys}"
    return f"Unknown keyboard action '{action}'"


@tool(category="desktop")
def list_windows() -> str:
    """List the titles of open windows."""
    try:
        import pygetwindow as gw
        titles = [t for t in gw.getAllTitles() if t.strip()]
        return "\n".join(titles) if titles else "no windows"
    except Exception as e:
        return f"Error: {e} (pip install pygetwindow; Windows only)"


@tool(category="desktop")
def focus_window(title_contains: str, action: str = "activate") -> str:
    """Bring a window to the front, or minimize / maximize / close it.
    title_contains: part of the window title
    action: activate | minimize | maximize | close
    """
    try:
        import pygetwindow as gw
    except Exception as e:
        return f"Error: {e}"
    wins = [w for w in gw.getWindowsWithTitle(title_contains) if w.title.strip()]
    if not wins:
        return f"No window with '{title_contains}' in its title"
    w = wins[0]
    try:
        if action == "activate":
            if w.isMinimized:
                w.restore()
            w.activate()
        elif action == "minimize":
            w.minimize()
        elif action == "maximize":
            w.maximize()
        elif action == "close":
            w.close()
        return f"{action}: {w.title}"
    except Exception as e:
        return f"Error: {e}"


def image_to_base64_jpeg(path: str, max_side: int = 1280) -> tuple[str, str] | None:
    """Helper for vision: return (base64, mime) of a downscaled JPEG."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return None


if not sys.platform.startswith("win"):
    # pygetwindow is Windows/macOS only; tools stay registered but report the limitation.
    pass
