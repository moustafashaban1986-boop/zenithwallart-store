"""Command-line front end for the same generation code the MCP server uses.

Examples (run with C:\\ComfyUI\\python_embeded\\python.exe):
    python cli.py status
    python cli.py image "a minimalist abstract wall art print, warm tones"
    python cli.py video "slow camera push-in on a framed canvas in a bright living room"
    python cli.py video "the painting comes alive, gentle motion" --image C:\\art\\poster.png --model ltx
    python cli.py models
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfy_client import ComfyClient, ComfyError  # noqa: E402
from presets import DEFAULT_VIDEO_PRESET, VIDEO_PRESETS, load_manifest, models_dir  # noqa: E402
from workflows import build_video, flux_schnell  # noqa: E402


async def cmd_status(args):
    c = ComfyClient()
    try:
        if not await c.is_running():
            print(f"ComfyUI is NOT running at {c.base_url}. Start it with Start-ComfyUI.bat.")
            return 1
        stats = await c.system_stats()
        dev = (stats.get("devices") or [{}])[0]
        print(f"ComfyUI {stats['system'].get('comfyui_version')} running at {c.base_url}")
        print(f"GPU: {dev.get('name')}  VRAM free {dev.get('vram_free', 0) / 2**30:.1f} / {dev.get('vram_total', 0) / 2**30:.1f} GB")
        print("Nodes: GGUF", "OK" if await c.has_node("UnetLoaderGGUF") else "MISSING",
              "| VideoHelperSuite", "OK" if await c.has_node("VHS_VideoCombine") else "MISSING")
        await cmd_models(args, client=c)
        return 0
    finally:
        await c.close()


async def cmd_models(args, client=None):
    manifest = load_manifest()
    own = client is None
    c = client or ComfyClient()
    try:
        have = set()
        if await c.is_running():
            for folder in ("diffusion_models", "unet_gguf", "checkpoints", "text_encoders", "clip_gguf", "vae", "clip_vision"):
                for f in await c.list_models(folder):
                    have.add(f.replace("\\", "/").split("/")[-1])
        else:
            for p in models_dir().rglob("*"):
                if p.is_file():
                    have.add(p.name)
        print(f"\nModel files ({models_dir()}):")
        for name, info in manifest["files"].items():
            print(f"  [{'x' if name in have else ' '}] {name}  ({info['gb']} GB, {info['folder']})")
        return 0
    finally:
        if own:
            await c.close()


async def _run(c: ComfyClient, wf: dict, timeout: float):
    try:
        job = await c.queue_prompt(wf)
    except ComfyError as e:
        print("ComfyUI rejected the job:\n" + str(e))
        return 1
    print(f"Queued job {job} ... waiting")
    state = await c.wait(job, timeout=timeout, poll=2.0)
    print(json.dumps({"state": state["state"], "files": [f["path"] for f in state["files"]],
                      "errors": state.get("messages", [])}, indent=2, ensure_ascii=False))
    return 0 if state["state"] == "done" else 1


async def cmd_image(args):
    c = ComfyClient()
    try:
        if not await c.is_running():
            print("ComfyUI is not running. Start it with Start-ComfyUI.bat first.")
            return 1
        wf = flux_schnell(args.prompt, width=args.width, height=args.height, steps=args.steps,
                          seed=args.seed, batch_size=args.count, filename_prefix=args.prefix,
                          use_checkpoint=args.checkpoint)
        return await _run(c, wf, timeout=600)
    finally:
        await c.close()


async def cmd_video(args):
    c = ComfyClient()
    try:
        if not await c.is_running():
            print("ComfyUI is not running. Start it with Start-ComfyUI.bat first.")
            return 1
        d = VIDEO_PRESETS[args.model]["defaults"]
        kwargs = dict(prompt=args.prompt, negative=args.negative,
                      width=args.width or d["width"], height=args.height or d["height"],
                      frames=args.frames or d["frames"], fps=args.fps or d["fps"],
                      steps=args.steps or d["steps"], cfg=d["cfg"] if args.cfg is None else args.cfg,
                      seed=args.seed, filename_prefix=args.prefix)
        if args.image:
            kwargs["image_name"] = await c.upload_image(args.image)
        wf = build_video(args.model, **kwargs)
        return await _run(c, wf, timeout=3600)
    finally:
        await c.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate images/videos with local ComfyUI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="check ComfyUI, GPU and installed models")
    sub.add_parser("models", help="list model files and whether they are installed")

    im = sub.add_parser("image", help="text-to-image with FLUX schnell")
    im.add_argument("prompt")
    im.add_argument("--width", type=int, default=1024)
    im.add_argument("--height", type=int, default=1024)
    im.add_argument("--steps", type=int, default=4)
    im.add_argument("--seed", type=int, default=-1)
    im.add_argument("--count", type=int, default=1)
    im.add_argument("--prefix", default="claude/image")
    im.add_argument("--checkpoint", action="store_true", help="use flux1-schnell-fp8 checkpoint instead of GGUF")

    vd = sub.add_parser("video", help="text/image-to-video")
    vd.add_argument("prompt")
    vd.add_argument("--model", choices=list(VIDEO_PRESETS), default=DEFAULT_VIDEO_PRESET)
    vd.add_argument("--image", help="path to an image to animate (image-to-video)")
    vd.add_argument("--negative")
    vd.add_argument("--width", type=int)
    vd.add_argument("--height", type=int)
    vd.add_argument("--frames", type=int)
    vd.add_argument("--fps", type=float)
    vd.add_argument("--steps", type=int)
    vd.add_argument("--cfg", type=float)
    vd.add_argument("--seed", type=int, default=-1)
    vd.add_argument("--prefix", default="claude/video")

    args = ap.parse_args(argv)
    fn = {"status": cmd_status, "models": cmd_models, "image": cmd_image, "video": cmd_video}[args.cmd]
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())
