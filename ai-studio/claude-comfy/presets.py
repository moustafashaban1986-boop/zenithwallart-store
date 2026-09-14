"""Model presets for the Claude <-> ComfyUI bridge.

Every preset names the model files it needs (see ../models.json) and the
generation defaults that are known to fit in 16 GB of VRAM
(Lenovo Legion 7 16ITHg6, RTX 3080 Laptop 16 GB).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_manifest() -> dict:
    """Load models.json (looked up next to this package, then one level up)."""
    for candidate in (HERE / "models.json", HERE.parent / "models.json"):
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as fh:
                return json.load(fh)
    raise FileNotFoundError("models.json not found next to claude-comfy/")


# --- File names (keep in sync with models.json) -----------------------------
FLUX_GGUF = "flux1-schnell-Q4_K_S.gguf"
FLUX_FP8_CKPT = "flux1-schnell-fp8.safetensors"
T5_FP8 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
CLIP_L = "clip_l.safetensors"
FLUX_VAE = "ae.safetensors"

WAN22_5B = "wan2.2_ti2v_5B_fp16.safetensors"
WAN22_VAE = "wan2.2_vae.safetensors"
UMT5_FP8 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
WAN21_VAE = "wan_2.1_vae.safetensors"
CLIP_VISION_H = "clip_vision_h.safetensors"
WAN21_T2V_GGUF = "wan2.1-t2v-14b-Q4_K_M.gguf"
WAN21_I2V_GGUF = "wan2.1-i2v-14b-480p-Q4_K_M.gguf"

LTX_CKPT = "ltx-video-2b-v0.9.5.safetensors"

# Negative prompt recommended by the Wan team (works for LTX too).
WAN_NEGATIVE = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，"
    "畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)
LTX_NEGATIVE = (
    "low quality, worst quality, deformed, distorted, disfigured, motion smear, motion artifacts, "
    "fused fingers, bad anatomy, weird hand, ugly"
)

IMAGE_PRESETS = {
    "flux-schnell": {
        "label": "FLUX.1 schnell (GGUF Q4) - fast, high quality images, 4 steps",
        "files": [FLUX_GGUF, T5_FP8, CLIP_L, FLUX_VAE],
        "fallback_files": [FLUX_FP8_CKPT],
        "defaults": {"width": 1024, "height": 1024, "steps": 4, "cfg": 1.0},
        "limits": {"max_pixels": 1536 * 1536},
    },
}

VIDEO_PRESETS = {
    "wan22-5b": {
        "label": "Wan 2.2 5B - best all-round video on 16GB (text->video and image->video), 24 fps",
        "files": [WAN22_5B, WAN22_VAE, UMT5_FP8],
        "supports_image": True,
        "defaults": {
            "width": 1280, "height": 704, "frames": 49, "fps": 24,
            "steps": 20, "cfg": 5.0, "negative": WAN_NEGATIVE,
        },
        "frame_step": 4,   # length must be 4n+1
        "size_step": 32,
        "limits": {"max_frames": 121},
    },
    "ltx": {
        "label": "LTX-Video 2B - fastest clips (seconds, not minutes), 25 fps",
        "files": [LTX_CKPT, T5_FP8],
        "supports_image": True,
        "defaults": {
            "width": 768, "height": 512, "frames": 97, "fps": 25,
            "steps": 30, "cfg": 3.0, "negative": LTX_NEGATIVE,
        },
        "frame_step": 8,   # length must be 8n+1
        "size_step": 32,
        "limits": {"max_frames": 257},
    },
    "wan21-14b": {
        "label": "Wan 2.1 14B (GGUF Q4_K_M) - highest quality, slowest. 480p recommended, 16 fps",
        "files": [WAN21_T2V_GGUF, UMT5_FP8, WAN21_VAE],
        "i2v_files": [WAN21_I2V_GGUF, UMT5_FP8, WAN21_VAE, CLIP_VISION_H],
        "supports_image": True,
        "defaults": {
            "width": 832, "height": 480, "frames": 33, "fps": 16,
            "steps": 20, "cfg": 6.0, "negative": WAN_NEGATIVE,
        },
        "frame_step": 4,
        "size_step": 16,
        "limits": {"max_frames": 81},
    },
}

DEFAULT_IMAGE_PRESET = "flux-schnell"
DEFAULT_VIDEO_PRESET = "wan22-5b"


def round_to_step(value: int, step: int, minimum: int) -> int:
    """Round *value* down to the nearest multiple of *step*, never below *minimum*."""
    value = max(int(value), minimum)
    return max(minimum, (value // step) * step)


def round_frames(frames: int, step: int) -> int:
    """Video models need length = step*n + 1 (e.g. 49, 81, 121 for step 4)."""
    frames = max(int(frames), step + 1)
    return ((frames - 1) // step) * step + 1


def comfy_dir() -> Path:
    """Locate the ComfyUI portable root.

    Priority: COMFY_DIR env var -> parent folder of this package (when installed
    as C:\\ComfyUI\\claude-comfy) -> C:\\ComfyUI.
    """
    env = os.environ.get("COMFY_DIR")
    if env:
        return Path(env)
    parent = HERE.parent
    if (parent / "python_embeded").exists() or (parent / "ComfyUI" / "main.py").exists():
        return parent
    return Path(r"C:\ComfyUI")


def models_dir() -> Path:
    return comfy_dir() / "ComfyUI" / "models"


def output_dir() -> Path:
    env = os.environ.get("COMFY_OUTPUT_DIR")
    return Path(env) if env else comfy_dir() / "ComfyUI" / "output"


def input_dir() -> Path:
    return comfy_dir() / "ComfyUI" / "input"
