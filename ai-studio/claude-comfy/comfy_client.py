"""Small async client for the ComfyUI HTTP API (queue, history, upload, stats)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from presets import comfy_dir, output_dir
from workflows import output_files

DEFAULT_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 30.0):
        self.base_url = base_url
        self.client_id = str(uuid.uuid4())
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self):
        await self._http.aclose()

    # -- basic queries -------------------------------------------------------
    async def is_running(self) -> bool:
        try:
            r = await self._http.get("/system_stats", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def system_stats(self) -> dict:
        r = await self._http.get("/system_stats")
        r.raise_for_status()
        return r.json()

    async def queue(self) -> dict:
        r = await self._http.get("/queue")
        r.raise_for_status()
        return r.json()

    async def list_models(self, folder: str) -> list[str]:
        r = await self._http.get(f"/models/{folder}")
        if r.status_code != 200:
            return []
        return r.json()

    async def object_info(self, node_class: str) -> Optional[dict]:
        r = await self._http.get(f"/object_info/{node_class}")
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get(node_class)

    async def has_node(self, node_class: str) -> bool:
        return await self.object_info(node_class) is not None

    # -- jobs ----------------------------------------------------------------
    async def queue_prompt(self, workflow: dict) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        r = await self._http.post("/prompt", json=payload)
        if r.status_code != 200:
            try:
                err = r.json()
            except Exception:
                raise ComfyError(f"ComfyUI rejected the workflow (HTTP {r.status_code}): {r.text[:500]}")
            raise ComfyError(format_prompt_error(err))
        data = r.json()
        return data["prompt_id"]

    async def history(self, prompt_id: str) -> Optional[dict]:
        r = await self._http.get(f"/history/{prompt_id}")
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get(prompt_id)

    async def job_state(self, prompt_id: str) -> dict:
        """Return {'state': pending|running|done|error|unknown, ...}."""
        hist = await self.history(prompt_id)
        if hist:
            status = hist.get("status") or {}
            state = "error" if status.get("status_str") == "error" else "done"
            files = output_files(hist)
            return {
                "state": state,
                "files": [self.to_local_path(f) for f in files],
                "messages": _error_messages(status) if state == "error" else [],
            }
        q = await self.queue()
        for item in q.get("queue_running", []):
            if len(item) > 1 and item[1] == prompt_id:
                return {"state": "running", "files": [], "messages": []}
        position = 0
        for idx, item in enumerate(q.get("queue_pending", [])):
            if len(item) > 1 and item[1] == prompt_id:
                position = idx + 1
                return {"state": "pending", "position": position, "files": [], "messages": []}
        return {"state": "unknown", "files": [], "messages": []}

    async def wait(self, prompt_id: str, timeout: float = 3600.0, poll: float = 2.0) -> dict:
        start = time.time()
        while True:
            state = await self.job_state(prompt_id)
            if state["state"] in ("done", "error"):
                return state
            if time.time() - start > timeout:
                state["state"] = "timeout"
                return state
            await asyncio.sleep(poll)

    async def interrupt(self) -> None:
        await self._http.post("/interrupt")

    async def free(self, unload_models: bool = True) -> None:
        await self._http.post("/free", json={"unload_models": unload_models, "free_memory": True})

    # -- files ---------------------------------------------------------------
    async def upload_image(self, path: str, subfolder: str = "claude") -> str:
        """Upload a local image into ComfyUI/input and return the name LoadImage expects."""
        p = Path(path).expanduser()
        if not p.is_file():
            raise ComfyError(f"Image not found: {p}")
        with open(p, "rb") as fh:
            files = {"image": (p.name, fh, "application/octet-stream")}
            data = {"subfolder": subfolder, "overwrite": "true", "type": "input"}
            r = await self._http.post("/upload/image", files=files, data=data, timeout=120.0)
        if r.status_code != 200:
            raise ComfyError(f"Upload failed (HTTP {r.status_code}): {r.text[:300]}")
        info = r.json()
        name = info.get("name", p.name)
        sub = info.get("subfolder", "")
        return f"{sub}/{name}" if sub else name

    def to_local_path(self, f: dict) -> dict:
        base = output_dir() if f.get("type", "output") == "output" else comfy_dir() / "ComfyUI" / f["type"]
        local = base / f.get("subfolder", "") / f["filename"]
        view = (f"{self.base_url}/view?filename={f['filename']}"
                f"&subfolder={f.get('subfolder', '')}&type={f.get('type', 'output')}")
        return {**f, "path": str(local), "url": view}

    # -- process management --------------------------------------------------
    @staticmethod
    def launch_comfyui() -> str:
        """Start ComfyUI portable in a new console window (Windows) or background process."""
        root = comfy_dir()
        bat = None
        for name in ("Start-ComfyUI.bat", "run_nvidia_gpu.bat"):
            if (root / name).exists():
                bat = root / name
                break
        if bat is None:
            raise ComfyError(f"Could not find Start-ComfyUI.bat or run_nvidia_gpu.bat in {root}")
        if sys.platform.startswith("win"):
            # 'start' opens a separate console so the server keeps running after we exit.
            subprocess.Popen(
                ["cmd", "/c", "start", "ComfyUI", "/D", str(root), str(bat)],
                cwd=str(root),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        else:
            subprocess.Popen([str(bat)], cwd=str(root), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(bat)


def _error_messages(status: dict) -> list[str]:
    out = []
    for msg in status.get("messages", []) or []:
        if isinstance(msg, list) and len(msg) > 1 and msg[0] == "execution_error":
            info = msg[1] or {}
            out.append(f"{info.get('node_type', '?')}: {info.get('exception_message', 'error')}")
    return out or ["Execution failed. Check the ComfyUI console window for the full traceback."]


def format_prompt_error(err: dict) -> str:
    """Turn ComfyUI's validation error JSON into a readable message."""
    lines = []
    top = err.get("error") or {}
    if top:
        lines.append(f"{top.get('message', 'Invalid workflow')}: {top.get('details', '')}".strip(": "))
    for node_id, info in (err.get("node_errors") or {}).items():
        cls = info.get("class_type", node_id)
        for e in info.get("errors", []):
            detail = e.get("details", "")
            msg = e.get("message", "")
            hint = ""
            if "not in list" in detail or "not in" in msg:
                hint = "  -> a model file is missing. Run download-models.ps1 or check ComfyUI\\models."
            lines.append(f"[{cls}] {msg}: {detail}{hint}")
    return "\n".join(lines) or json.dumps(err)[:800]
