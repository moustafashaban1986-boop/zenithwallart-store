"""End-to-end: start mock ComfyUI, launch the real MCP server over stdio, call tools.

Run:  python tests/test_mcp_end_to_end.py     (needs `pip install mcp httpx`)
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "claude-comfy" / "server.py"

try:  # mcp 2.x
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.session import ClientSession
except ImportError:
    from mcp import ClientSession, StdioServerParameters  # type: ignore
    from mcp.client.stdio import stdio_client  # type: ignore

ALL_MODELS = json.loads((ROOT / "models.json").read_text(encoding="utf-8"))["files"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _text(result) -> str:
    return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")


async def scenario(port: int, tmp: Path, models_env: dict):
    env = {**os.environ,
           "COMFY_URL": f"http://127.0.0.1:{port}",
           "COMFY_DIR": str(tmp / "ComfyUI_root"),
           "COMFY_OUTPUT_DIR": str(tmp / "output"),
           "PYTHONUNBUFFERED": "1"}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            expected = {"comfy_status", "start_comfyui", "list_presets", "generate_image", "generate_video",
                        "job_status", "wait_for_job", "cancel_current_job", "free_memory", "list_outputs", "view_image"}
            assert expected <= tools, f"missing tools: {expected - tools}"
            print("PASS tools registered:", sorted(tools))

            status = json.loads(_text(await session.call_tool("comfy_status", {})))
            assert status["running"] and status["vram_total_gb"] == 16.0
            assert status["presets"]["image"]["flux-schnell"]["ready"]
            assert status["presets"]["video"]["wan22-5b"]["ready"]
            assert status["presets"]["video"]["ltx"]["ready"]
            assert status["presets"]["video"]["wan21-14b"]["image_to_video_ready"]
            print("PASS comfy_status")

            res = await session.call_tool("generate_image", {"prompt": "a framed abstract print", "seed": 7})
            body = json.loads(_text(res))
            assert body["state"] == "done" and body["seed"] == 7, body
            assert len(body["files"]) == 1 and body["files"][0].endswith(".png")
            assert Path(body["files"][0]).is_file(), "output path must resolve to the mock's output dir"
            kinds = [c.type for c in res.content]
            assert "image" in kinds, "expected an image preview block"
            print("PASS generate_image ->", body["files"][0])

            res = await session.call_tool("generate_video", {"prompt": "camera push-in", "frames": 50, "height": 720})
            body = json.loads(_text(res))
            assert body["state"] == "done", body
            assert body["settings"]["frames"] == 50 and body["model"] == "wan22-5b"
            assert body["files"][0].endswith(".mp4") and Path(body["files"][0]).is_file()
            print("PASS generate_video wan22-5b ->", body["files"][0])

            # image-to-video uploads the image then runs the LTX i2v graph
            src = tmp / "poster.png"
            src.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGM8URHAAANMDEgANwcAT5wBmBS18PkAAAAASUVORK5CYII="))
            res = await session.call_tool("generate_video", {"prompt": "gentle motion", "model": "ltx",
                                                             "image_path": str(src), "frames": 41})
            body = json.loads(_text(res))
            assert body["state"] == "done", body
            assert (tmp / "input" / "claude" / "poster.png").is_file(), "image should have been uploaded"
            print("PASS generate_video ltx image-to-video")

            res = await session.call_tool("generate_video", {"prompt": "x", "model": "wan21-14b", "wait": False})
            body = json.loads(_text(res))
            assert "job_id" in body and body["state"] == "queued"
            body2 = json.loads(_text(await session.call_tool("job_status", {"job_id": body["job_id"]})))
            assert body2["state"] == "done" and body2["files"][0].endswith(".mp4")
            print("PASS wan21-14b queued + job_status")

            # simulate an out-of-memory failure
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/mock/fail_next_oom", data=b"{}"))
            body = json.loads(_text(await session.call_tool("generate_video", {"prompt": "x"})))
            assert body["state"] == "error" and "hint" in body and "memory" in body["errors"][0].lower(), body
            print("PASS out-of-memory reported with hint")

            body = json.loads(_text(await session.call_tool("list_outputs", {"limit": 5})))
            assert len(body["files"]) >= 2
            print("PASS list_outputs")

            assert "Interrupt" in _text(await session.call_tool("cancel_current_job", {}))
            assert "freed" in _text(await session.call_tool("free_memory", {}))
            print("PASS cancel/free")


async def scenario_missing_models(port: int, tmp: Path):
    env = {**os.environ, "COMFY_URL": f"http://127.0.0.1:{port}", "COMFY_DIR": str(tmp),
           "COMFY_OUTPUT_DIR": str(tmp / "output")}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            body = json.loads(_text(await session.call_tool("generate_video", {"prompt": "x", "model": "wan21-14b"})))
            assert "missing" in body and "wan2.1-t2v-14b-Q4_K_M.gguf" in body["missing"], body
            print("PASS missing-model guidance:", body["missing"])
            status = json.loads(_text(await session.call_tool("comfy_status", {})))
            assert status["presets"]["image"]["flux-schnell"]["using_fallback_checkpoint"]
            print("PASS fp8 checkpoint fallback detected")


def _start_mock(port: int, tmp: Path, models: dict) -> subprocess.Popen:
    env = {**os.environ, "MOCK_PORT": str(port), "MOCK_OUTPUT_DIR": str(tmp / "output"),
           "MOCK_INPUT_DIR": str(tmp / "input"), "MOCK_MODELS": json.dumps(models)}
    proc = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_comfy.py")], env=env)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/system_stats", timeout=1)
            return proc
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("mock did not start")


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        full = {}
        for name, info in ALL_MODELS.items():
            # Like real ComfyUI: .gguf files are only visible via ComfyUI-GGUF's "unet_gguf" key.
            key = "unet_gguf" if name.endswith(".gguf") else info["folder"]
            full.setdefault(key, []).append(name)
        port = _free_port()
        proc = _start_mock(port, tmp, full)
        try:
            asyncio.run(scenario(port, tmp, full))
        finally:
            proc.kill()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        partial = {"checkpoints": ["flux1-schnell-fp8.safetensors"], "diffusion_models": [], "text_encoders": [],
                   "vae": [], "clip_vision": []}
        port = _free_port()
        proc = _start_mock(port, tmp, partial)
        try:
            asyncio.run(scenario_missing_models(port, tmp))
        finally:
            proc.kill()
    print("ALL END-TO-END TESTS PASSED")


if __name__ == "__main__":
    main()
