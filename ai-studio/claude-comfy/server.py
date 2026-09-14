"""MCP server that lets Claude generate images and videos with a local ComfyUI.

Run with the ComfyUI portable Python (no extra install needed after install.ps1):

    C:\\ComfyUI\\python_embeded\\python.exe C:\\ComfyUI\\claude-comfy\\server.py

Environment variables (all optional):
    COMFY_URL         http://127.0.0.1:8188
    COMFY_DIR         C:\\ComfyUI            (portable root; auto-detected)
    COMFY_OUTPUT_DIR  <COMFY_DIR>\\ComfyUI\\output
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
logging.getLogger("httpx").setLevel(logging.WARNING)

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

from mcp.types import ImageContent, TextContent

from comfy_client import ComfyClient, ComfyError
from presets import (
    DEFAULT_IMAGE_PRESET, DEFAULT_VIDEO_PRESET, IMAGE_PRESETS, VIDEO_PRESETS,
    comfy_dir, load_manifest, models_dir, output_dir,
)
from workflows import build_video, flux_schnell

INSTRUCTIONS = """Local, free, unlimited image and video generation through ComfyUI on the user's
Lenovo Legion (RTX 3080 16GB). Typical flow:
1. comfy_status()  - make sure ComfyUI is running (call start_comfyui() if not).
2. generate_image(prompt=...)  - FLUX schnell, ~10-20 s per 1024x1024 image.
3. generate_video(prompt=...)  - Wan 2.2 5B by default, 1280x704, 49 frames (~2 s), several minutes.
   Pass image_path= to animate an existing image (image-to-video).
Outputs are saved under ComfyUI/output and the absolute paths are returned.
Keep first video tests small (49 frames); raise frames only after a successful run.
"""

mcp = _Server("comfyui", instructions=INSTRUCTIONS)

_client: Optional[ComfyClient] = None


def client() -> ComfyClient:
    global _client
    if _client is None:
        _client = ComfyClient()
    return _client


def _j(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _preview_image(path: str, max_side: int = 768) -> Optional[ImageContent]:
    """Return a downscaled JPEG preview of an image file as MCP ImageContent."""
    try:
        from PIL import Image  # bundled with ComfyUI's python
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
        return ImageContent(type="image", data=base64.b64encode(buf.getvalue()).decode("ascii"),
                            mimeType="image/jpeg")
    except Exception:
        return None


async def _installed_files() -> dict[str, list[str]]:
    c = client()
    # ComfyUI-GGUF lists .gguf files only under its own "unet_gguf" / "clip_gguf" keys.
    folders = ("diffusion_models", "unet_gguf", "checkpoints", "text_encoders", "clip_gguf", "vae", "clip_vision")
    result = {}
    for folder in folders:
        result[folder] = await c.list_models(folder)
    return result


def _flatten(installed: dict[str, list[str]]) -> set[str]:
    names = set()
    for files in installed.values():
        for f in files:
            names.add(f)
            names.add(f.replace("\\", "/").split("/")[-1])
    return names


def _preset_readiness(installed: dict[str, list[str]]) -> dict:
    have = _flatten(installed)
    out = {"image": {}, "video": {}}
    for name, p in IMAGE_PRESETS.items():
        missing = [f for f in p["files"] if f not in have]
        fallback_ok = all(f in have for f in p.get("fallback_files", []))
        out["image"][name] = {
            "ready": not missing or fallback_ok,
            "missing": missing if not fallback_ok else [],
            "using_fallback_checkpoint": bool(missing) and fallback_ok,
            "label": p["label"],
        }
    for name, p in VIDEO_PRESETS.items():
        missing = [f for f in p["files"] if f not in have]
        i2v_missing = [f for f in p.get("i2v_files", p["files"]) if f not in have]
        out["video"][name] = {
            "ready": not missing,
            "image_to_video_ready": not i2v_missing,
            "missing": sorted(set(missing + i2v_missing)),
            "label": p["label"],
        }
    return out


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def comfy_status() -> str:
    """Check whether ComfyUI is running, show GPU/VRAM, queue length and which
    image/video presets have all their model files installed."""
    c = client()
    if not await c.is_running():
        return _j({
            "running": False,
            "url": c.base_url,
            "hint": "ComfyUI is not running. Call start_comfyui() or double-click Start-ComfyUI.bat.",
            "comfy_dir": str(comfy_dir()),
        })
    stats = await c.system_stats()
    q = await c.queue()
    dev = (stats.get("devices") or [{}])[0]
    installed = await _installed_files()
    nodes = {
        "ComfyUI-GGUF": await c.has_node("UnetLoaderGGUF"),
        "VideoHelperSuite": await c.has_node("VHS_VideoCombine"),
    }
    return _j({
        "running": True,
        "url": c.base_url,
        "comfyui_version": stats.get("system", {}).get("comfyui_version"),
        "gpu": dev.get("name"),
        "vram_total_gb": round((dev.get("vram_total") or 0) / 2**30, 1),
        "vram_free_gb": round((dev.get("vram_free") or 0) / 2**30, 1),
        "queue_running": len(q.get("queue_running", [])),
        "queue_pending": len(q.get("queue_pending", [])),
        "custom_nodes": nodes,
        "presets": _preset_readiness(installed),
        "output_dir": str(output_dir()),
    })


@mcp.tool()
async def start_comfyui(wait_seconds: int = 180) -> str:
    """Launch ComfyUI (Start-ComfyUI.bat) if it is not already running and wait until
    its API answers. Returns the status."""
    c = client()
    if await c.is_running():
        return "ComfyUI is already running at " + c.base_url
    bat = ComfyClient.launch_comfyui()
    deadline = time.time() + max(10, int(wait_seconds))
    while time.time() < deadline:
        if await c.is_running():
            return f"ComfyUI started via {bat} and is now answering at {c.base_url}"
        await asyncio.sleep(2)
    return (f"Launched {bat} but the API did not answer within {wait_seconds}s. "
            "Look at the ComfyUI console window for errors, then call comfy_status() again.")


@mcp.tool()
async def list_presets() -> str:
    """List the available image and video presets with their default settings,
    limits for 16GB VRAM, and the model files each one needs."""
    manifest = load_manifest()
    return _j({
        "default_image_preset": DEFAULT_IMAGE_PRESET,
        "default_video_preset": DEFAULT_VIDEO_PRESET,
        "image": IMAGE_PRESETS,
        "video": {k: {kk: vv for kk, vv in v.items()} for k, v in VIDEO_PRESETS.items()},
        "model_packs": {k: v["description"] for k, v in manifest["packs"].items()},
        "models_dir": str(models_dir()),
    })


@mcp.tool()
async def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    seed: int = -1,
    count: int = 1,
    filename_prefix: str = "claude/image",
    wait: bool = True,
    timeout_seconds: int = 600,
) -> list:
    """Generate image(s) locally with FLUX.1 schnell. Free and unlimited.

    prompt: describe the image in natural language (English works best).
    width/height: multiples of 16, up to about 1536x1536 on 16GB VRAM. 1024x1024 ~15 s.
    steps: 4 is the sweet spot for schnell (1-8).
    seed: -1 = random. Reuse a seed to reproduce an image.
    count: how many images (batch).
    Returns the saved file paths and a preview of the first image.
    """
    c = client()
    if not await c.is_running():
        return [TextContent(type="text", text="ComfyUI is not running. Call start_comfyui() first.")]
    installed = await _installed_files()
    readiness = _preset_readiness(installed)["image"][DEFAULT_IMAGE_PRESET]
    if not readiness["ready"]:
        return [TextContent(type="text", text=_j({
            "error": "FLUX schnell model files are missing",
            "missing": readiness["missing"],
            "fix": "Run  download-models.ps1 -Pack starter  (or -Pack flux-fp8) and restart ComfyUI.",
        }))]
    wf = flux_schnell(prompt, width=width, height=height, steps=steps, seed=seed,
                      batch_size=max(1, min(int(count), 8)), filename_prefix=filename_prefix,
                      use_checkpoint=readiness["using_fallback_checkpoint"])
    try:
        job_id = await c.queue_prompt(wf)
    except ComfyError as e:
        return [TextContent(type="text", text=f"ComfyUI rejected the job:\n{e}")]
    if not wait:
        return [TextContent(type="text", text=_j({"job_id": job_id, "state": "queued",
                                                  "next": "call job_status(job_id) or wait_for_job(job_id)"}))]
    state = await c.wait(job_id, timeout=timeout_seconds, poll=1.0)
    result = {"job_id": job_id, "state": state["state"], "seed": wf["7"]["inputs"]["seed"],
              "files": [f["path"] for f in state["files"]], "errors": state.get("messages", [])}
    blocks: list = [TextContent(type="text", text=_j(result))]
    if state["files"]:
        preview = _preview_image(state["files"][0]["path"])
        if preview:
            blocks.append(preview)
    return blocks


@mcp.tool()
async def generate_video(
    prompt: str,
    model: str = DEFAULT_VIDEO_PRESET,
    negative_prompt: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    frames: Optional[int] = None,
    fps: Optional[float] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    seed: int = -1,
    image_path: Optional[str] = None,
    filename_prefix: str = "claude/video",
    wait: bool = True,
    timeout_seconds: int = 3600,
) -> list:
    """Generate an MP4 video locally. Free and unlimited.

    model: "wan22-5b" (default, best quality/speed on 16GB, 1280x704 @ 24 fps),
           "ltx" (fastest, 768x512 @ 25 fps), or "wan21-14b" (slowest, 832x480 @ 16 fps, GGUF).
    frames: clip length. 49 frames ~ 2 s at 24 fps. Start small; 121 frames max for wan22-5b.
            Values are rounded to what the model accepts (4n+1 or 8n+1).
    image_path: absolute path to a PNG/JPG to animate (image-to-video). Omit for text-to-video.
    negative_prompt: omit to use the model's recommended default.
    seed: -1 = random.
    Videos take minutes: keep wait=True (default) or poll with job_status(job_id).
    Returns the saved MP4 path(s).
    """
    c = client()
    if model not in VIDEO_PRESETS:
        return [TextContent(type="text", text=f"Unknown model '{model}'. Use one of: {', '.join(VIDEO_PRESETS)}")]
    if not await c.is_running():
        return [TextContent(type="text", text="ComfyUI is not running. Call start_comfyui() first.")]
    installed = await _installed_files()
    readiness = _preset_readiness(installed)["video"][model]
    needs_i2v = bool(image_path)
    if (needs_i2v and not readiness["image_to_video_ready"]) or (not needs_i2v and not readiness["ready"]):
        return [TextContent(type="text", text=_j({
            "error": f"Model files for '{model}' are missing",
            "missing": readiness["missing"],
            "fix": "Run download-models.ps1 with the matching pack (starter / ltx / wan21-14b) and restart ComfyUI.",
        }))]
    if not await c.has_node("VHS_VideoCombine"):
        return [TextContent(type="text", text="ComfyUI-VideoHelperSuite is not installed. Re-run install.ps1 or install it from the Manager.")]
    if model == "wan21-14b" and not await c.has_node("UnetLoaderGGUF"):
        return [TextContent(type="text", text="ComfyUI-GGUF is not installed. Re-run install.ps1 or install it from the Manager.")]

    d = VIDEO_PRESETS[model]["defaults"]
    kwargs = dict(
        prompt=prompt, negative=negative_prompt,
        width=width or d["width"], height=height or d["height"],
        frames=frames or d["frames"], fps=fps or d["fps"],
        steps=steps or d["steps"], cfg=d["cfg"] if cfg is None else cfg,
        seed=seed, filename_prefix=filename_prefix,
    )
    max_frames = VIDEO_PRESETS[model]["limits"]["max_frames"]
    if kwargs["frames"] > max_frames:
        kwargs["frames"] = max_frames
    if image_path:
        try:
            kwargs["image_name"] = await c.upload_image(image_path)
        except ComfyError as e:
            return [TextContent(type="text", text=str(e))]
    wf = build_video(model, **kwargs)
    try:
        job_id = await c.queue_prompt(wf)
    except ComfyError as e:
        return [TextContent(type="text", text=f"ComfyUI rejected the job:\n{e}")]
    settings = {k: v for k, v in kwargs.items() if k not in ("prompt", "negative")}
    if not wait:
        return [TextContent(type="text", text=_j({"job_id": job_id, "state": "queued", "model": model,
                                                  "settings": settings,
                                                  "next": "call job_status(job_id) or wait_for_job(job_id)"}))]
    state = await c.wait(job_id, timeout=timeout_seconds, poll=3.0)
    result = {
        "job_id": job_id, "state": state["state"], "model": model, "settings": settings,
        "files": [f["path"] for f in state["files"] if f.get("kind") == "video"] or [f["path"] for f in state["files"]],
        "errors": state.get("messages", []),
    }
    if state["state"] == "error" and any("memory" in m.lower() for m in state.get("messages", [])):
        result["hint"] = ("Out of VRAM. Retry with fewer frames (e.g. 33) or a smaller size, "
                          "or call free_memory() first.")
    return [TextContent(type="text", text=_j(result))]


@mcp.tool()
async def job_status(job_id: str) -> str:
    """Check a queued/running job. Returns state (pending/running/done/error) and output file paths."""
    state = await client().job_state(job_id)
    state["files"] = [f["path"] for f in state.get("files", [])]
    return _j({"job_id": job_id, **state})


@mcp.tool()
async def wait_for_job(job_id: str, timeout_seconds: int = 3600) -> str:
    """Block until a job finishes (or the timeout passes) and return its output file paths."""
    state = await client().wait(job_id, timeout=timeout_seconds, poll=3.0)
    state["files"] = [f["path"] for f in state.get("files", [])]
    return _j({"job_id": job_id, **state})


@mcp.tool()
async def cancel_current_job() -> str:
    """Interrupt whatever ComfyUI is currently generating."""
    await client().interrupt()
    return "Interrupt sent."


@mcp.tool()
async def free_memory() -> str:
    """Unload all models from VRAM. Use between image and video jobs if you hit out-of-memory errors."""
    await client().free(unload_models=True)
    return "Models unloaded, VRAM freed."


@mcp.tool()
async def list_outputs(limit: int = 20, kind: str = "all") -> str:
    """List the most recent generated files in ComfyUI/output. kind: all | image | video."""
    root = output_dir()
    if not root.exists():
        return _j({"output_dir": str(root), "files": []})
    exts = {"image": (".png", ".jpg", ".jpeg", ".webp"), "video": (".mp4", ".webm", ".mkv", ".gif")}
    wanted = exts.get(kind, exts["image"] + exts["video"])
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in wanted]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return _j({"output_dir": str(root), "files": [
        {"path": str(p), "size_mb": round(p.stat().st_size / 2**20, 2),
         "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))}
        for p in files[:max(1, int(limit))]
    ]})


@mcp.tool()
async def view_image(path: str) -> list:
    """Show an image file (e.g. a generated image or a video's source frame) to Claude."""
    p = Path(path)
    if not p.is_file():
        return [TextContent(type="text", text=f"File not found: {p}")]
    preview = _preview_image(str(p))
    if preview is None:
        return [TextContent(type="text", text="Could not read that image (Pillow missing or unsupported format).")]
    return [TextContent(type="text", text=str(p)), preview]


if __name__ == "__main__":
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))
