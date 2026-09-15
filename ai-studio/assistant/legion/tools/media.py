"""Image / video generation through the ComfyUI bridge (../claude-comfy) and speech tools."""
from __future__ import annotations

import asyncio
import sys

from . import tool
from ..config import Settings, comfy_bridge_dir

_bridge_loaded = False


def _bridge():
    global _bridge_loaded
    d = comfy_bridge_dir()
    if d is None:
        raise RuntimeError("claude-comfy bridge not found. Install ai-studio (INSTALL.bat) first.")
    if not _bridge_loaded:
        sys.path.insert(0, str(d))
        _bridge_loaded = True
    import comfy_client, workflows, presets  # type: ignore
    return comfy_client, workflows, presets


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # called from inside an event loop (web UI): run in a helper thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


async def _ensure_comfy(cc):
    c = cc.ComfyClient(Settings().get("comfy_url"))
    if not await c.is_running():
        try:
            cc.ComfyClient.launch_comfyui()
        except Exception as e:
            await c.close()
            raise RuntimeError(f"ComfyUI is not running and could not be started: {e}")
        for _ in range(90):
            await asyncio.sleep(2)
            if await c.is_running():
                break
        else:
            await c.close()
            raise RuntimeError("ComfyUI did not start within 3 minutes. Check its console window.")
    return c


@tool(category="media")
def generate_image(prompt: str, width: int = 1024, height: int = 1024, seed: int = -1, count: int = 1) -> dict:
    """Generate an image locally with FLUX (free, offline, ~15 s). Returns the PNG path(s).
    prompt: detailed description of the image
    width: pixels (multiple of 16)
    height: pixels (multiple of 16)
    seed: -1 for random
    count: number of images
    """
    cc, wf, _ = _bridge()

    async def go():
        c = await _ensure_comfy(cc)
        try:
            job = await c.queue_prompt(wf.flux_schnell(prompt, width=width, height=height, seed=seed,
                                                       batch_size=max(1, min(count, 8)), filename_prefix="legion/image"))
            state = await c.wait(job, timeout=900, poll=1.0)
            return {"state": state["state"], "files": [f["path"] for f in state["files"]], "errors": state.get("messages", [])}
        finally:
            await c.close()
    return _run(go())


@tool(category="media")
def generate_video(prompt: str, model: str | None = None, frames: int | None = None, width: int | None = None,
                   height: int | None = None, image_path: str | None = None, seed: int = -1) -> dict:
    """Generate an MP4 video locally (free, offline, takes minutes). Text-to-video, or image-to-video
    when image_path is given. Returns the MP4 path.
    prompt: describe the motion and scene
    model: wan22-5b (default, best) | ltx (fastest) | wan21-14b (best quality, slow)
    frames: clip length; 49 frames = 2 s. Start small.
    width: pixels (model default if omitted)
    height: pixels (model default if omitted)
    image_path: an image to animate (optional)
    seed: -1 for random
    """
    cc, wf, presets = _bridge()
    model = model or Settings().get("video_model", "wan22-5b")
    if model not in presets.VIDEO_PRESETS:
        return {"error": f"unknown model {model}; use one of {list(presets.VIDEO_PRESETS)}"}
    d = presets.VIDEO_PRESETS[model]["defaults"]

    async def go():
        c = await _ensure_comfy(cc)
        try:
            kwargs = dict(prompt=prompt, width=width or d["width"], height=height or d["height"],
                          frames=frames or d["frames"], fps=d["fps"], steps=d["steps"], cfg=d["cfg"], seed=seed,
                          filename_prefix="legion/video")
            if image_path:
                kwargs["image_name"] = await c.upload_image(image_path)
            job = await c.queue_prompt(wf.build_video(model, **kwargs))
            state = await c.wait(job, timeout=3600, poll=3.0)
            return {"state": state["state"], "model": model,
                    "files": [f["path"] for f in state["files"]], "errors": state.get("messages", [])}
        finally:
            await c.close()
    return _run(go())


@tool(category="media")
def comfy_status() -> dict:
    """Check whether ComfyUI (image/video engine) is running and which models are installed."""
    cc, _, presets = _bridge()

    async def go():
        c = cc.ComfyClient(Settings().get("comfy_url"))
        try:
            if not await c.is_running():
                return {"running": False, "hint": "Say 'start comfy' or run Start-ComfyUI.bat"}
            stats = await c.system_stats()
            dev = (stats.get("devices") or [{}])[0]
            have = set()
            for folder in ("diffusion_models", "unet_gguf", "checkpoints", "text_encoders", "vae", "clip_vision"):
                have.update(f.replace("\\", "/").split("/")[-1] for f in await c.list_models(folder))
            ready = {k: all(f in have for f in v["files"]) for k, v in presets.VIDEO_PRESETS.items()}
            ready["flux-schnell"] = all(f in have for f in presets.IMAGE_PRESETS["flux-schnell"]["files"]) or \
                presets.FLUX_FP8_CKPT in have
            return {"running": True, "gpu": dev.get("name"), "vram_free_gb": round((dev.get("vram_free") or 0) / 2**30, 1),
                    "models_ready": ready}
        finally:
            await c.close()
    return _run(go())


@tool(category="media")
def speak(text: str, voice: str | None = None) -> str:
    """Say something out loud through the speakers using the selected voice.
    text: what to say
    voice: optional voice id (see list_voices)
    """
    from ..speech import TTS
    path = TTS(Settings()).synthesize(text, voice=voice, play=True)
    return f"spoke {len(text)} chars" + (f" (saved {path})" if path else "")


@tool(category="media")
def list_voices() -> dict:
    """List available text-to-speech voices (Kokoro, Windows voices and cloned voices)."""
    from ..speech import TTS
    return TTS(Settings()).available_voices()


@tool(category="media")
def clone_voice(name: str, sample_wav: str) -> str:
    """Create a new voice from a 6-20 second WAV sample of someone speaking (uses Chatterbox,
    runs locally). The voice becomes selectable as clone:<name>.
    name: short name for the voice
    sample_wav: path to the sample .wav file
    """
    from ..speech import TTS
    return TTS(Settings()).add_clone(name, sample_wav)


@tool(category="media")
def transcribe_audio(path: str, language: str | None = None) -> str:
    """Convert a speech recording (wav/mp3/m4a) to text with Whisper (offline).
    path: audio file
    language: ISO code like en or ar; omit to auto-detect
    """
    from ..speech import STT
    return STT(Settings()).transcribe_file(path, language=language)
