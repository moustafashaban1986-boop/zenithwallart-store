"""ComfyUI API-format workflow builders.

Each function returns a ``{node_id: {"class_type": ..., "inputs": {...}}}``
dict that can be POSTed to ``/prompt``.  Node classes and input names were
checked against ComfyUI v0.35, ComfyUI-GGUF and ComfyUI-VideoHelperSuite.
"""
from __future__ import annotations

import random
from typing import Optional

from presets import (
    CLIP_L, CLIP_VISION_H, FLUX_FP8_CKPT, FLUX_GGUF, FLUX_VAE, LTX_CKPT, T5_FP8,
    UMT5_FP8, WAN21_I2V_GGUF, WAN21_T2V_GGUF, WAN21_VAE, WAN22_5B, WAN22_VAE,
    IMAGE_PRESETS, VIDEO_PRESETS, round_frames, round_to_step,
)

MAX_SEED = 2**53 - 1  # keeps the value exact in JSON / JavaScript


def pick_seed(seed: Optional[int]) -> int:
    if seed is None or int(seed) < 0:
        return random.randint(0, MAX_SEED)
    return int(seed)


def _video_combine(images_ref: list, fps: float, prefix: str) -> dict:
    """VHS_VideoCombine node writing an H.264 MP4 into ComfyUI/output."""
    return {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": images_ref,
            "frame_rate": fps,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
        },
    }


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
def flux_schnell(prompt: str, width: int = 1024, height: int = 1024, steps: int = 4,
                 seed: Optional[int] = None, batch_size: int = 1,
                 filename_prefix: str = "claude/image", use_checkpoint: bool = False) -> dict:
    """FLUX.1 schnell text-to-image (GGUF Q4 by default, fp8 checkpoint fallback)."""
    d = IMAGE_PRESETS["flux-schnell"]["defaults"]
    width = round_to_step(width, 16, 256)
    height = round_to_step(height, 16, 256)
    steps = max(1, int(steps or d["steps"]))
    wf: dict = {}
    if use_checkpoint:
        wf["1"] = {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": FLUX_FP8_CKPT}}
        model_ref, clip_ref, vae_ref = ["1", 0], ["1", 1], ["1", 2]
    else:
        wf["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": FLUX_GGUF}}
        wf["2"] = {"class_type": "DualCLIPLoader",
                   "inputs": {"clip_name1": T5_FP8, "clip_name2": CLIP_L, "type": "flux"}}
        wf["3"] = {"class_type": "VAELoader", "inputs": {"vae_name": FLUX_VAE}}
        model_ref, clip_ref, vae_ref = ["1", 0], ["2", 0], ["3", 0]
    wf["4"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}}
    wf["5"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}}
    wf["6"] = {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": width, "height": height, "batch_size": max(1, int(batch_size))}}
    wf["7"] = {"class_type": "KSampler", "inputs": {
        "model": model_ref, "seed": pick_seed(seed), "steps": steps, "cfg": d["cfg"],
        "sampler_name": "euler", "scheduler": "simple",
        "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0}}
    wf["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": vae_ref}}
    wf["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix}}
    return wf


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------
def wan22_5b(prompt: str, negative: Optional[str] = None, width: int = 1280, height: int = 704,
             frames: int = 49, fps: float = 24, steps: int = 20, cfg: float = 5.0,
             seed: Optional[int] = None, image_name: Optional[str] = None,
             filename_prefix: str = "claude/video") -> dict:
    """Wan 2.2 5B text-to-video, or image-to-video when *image_name* (a file in
    ComfyUI/input) is given."""
    p = VIDEO_PRESETS["wan22-5b"]
    d = p["defaults"]
    negative = d["negative"] if negative is None else negative
    width = round_to_step(width, p["size_step"], 256)
    height = round_to_step(height, p["size_step"], 256)
    frames = round_frames(frames, p["frame_step"])
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": WAN22_5B, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": UMT5_FP8, "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": WAN22_VAE}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
            "vae": ["3", 0], "width": width, "height": height, "length": frames, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": pick_seed(seed), "steps": int(steps or d["steps"]),
            "cfg": float(cfg if cfg is not None else d["cfg"]),
            "sampler_name": "uni_pc", "scheduler": "simple",
            "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "11": _video_combine(["9", 0], fps or d["fps"], filename_prefix),
    }
    if image_name:
        wf["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["7"]["inputs"]["start_image"] = ["10", 0]
    return wf


def ltx_video(prompt: str, negative: Optional[str] = None, width: int = 768, height: int = 512,
              frames: int = 97, fps: float = 25, steps: int = 30, cfg: float = 3.0,
              seed: Optional[int] = None, image_name: Optional[str] = None,
              image_strength: float = 0.15, filename_prefix: str = "claude/video") -> dict:
    """LTX-Video 2B text-to-video / image-to-video."""
    p = VIDEO_PRESETS["ltx"]
    d = p["defaults"]
    negative = d["negative"] if negative is None else negative
    width = round_to_step(width, p["size_step"], 256)
    height = round_to_step(height, p["size_step"], 256)
    frames = round_frames(frames, p["frame_step"])
    fps = fps or d["fps"]
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": LTX_CKPT}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": T5_FP8, "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        # 5/6 set below (text-to-video vs image-to-video)
        "7": {"class_type": "LTXVScheduler", "inputs": {
            "steps": int(steps or d["steps"]), "max_shift": 2.05, "base_shift": 0.95,
            "stretch": True, "terminal": 0.1}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": _video_combine(["10", 0], fps, filename_prefix),
    }
    if image_name:
        wf["12"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["6"] = {"class_type": "LTXVImgToVideo", "inputs": {
            "positive": ["3", 0], "negative": ["4", 0], "vae": ["1", 2], "image": ["12", 0],
            "width": width, "height": height, "length": frames, "batch_size": 1,
            "strength": float(image_strength)}}
        pos_ref, neg_ref, latent_ref = ["6", 0], ["6", 1], ["6", 2]
    else:
        wf["6"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {
            "width": width, "height": height, "length": frames, "batch_size": 1}}
        pos_ref, neg_ref, latent_ref = ["3", 0], ["4", 0], ["6", 0]
    wf["5"] = {"class_type": "LTXVConditioning", "inputs": {
        "positive": pos_ref, "negative": neg_ref, "frame_rate": float(fps)}}
    wf["7"]["inputs"]["latent"] = latent_ref
    wf["9"] = {"class_type": "SamplerCustom", "inputs": {
        "model": ["1", 0], "add_noise": True, "noise_seed": pick_seed(seed),
        "cfg": float(cfg if cfg is not None else d["cfg"]),
        "positive": ["5", 0], "negative": ["5", 1], "sampler": ["8", 0], "sigmas": ["7", 0],
        "latent_image": latent_ref}}
    return wf


def wan21_14b(prompt: str, negative: Optional[str] = None, width: int = 832, height: int = 480,
              frames: int = 33, fps: float = 16, steps: int = 20, cfg: float = 6.0,
              seed: Optional[int] = None, image_name: Optional[str] = None,
              filename_prefix: str = "claude/video") -> dict:
    """Wan 2.1 14B GGUF (Q4_K_M) text-to-video, or image-to-video with the 480p I2V model."""
    p = VIDEO_PRESETS["wan21-14b"]
    d = p["defaults"]
    negative = d["negative"] if negative is None else negative
    width = round_to_step(width, p["size_step"], 256)
    height = round_to_step(height, p["size_step"], 256)
    frames = round_frames(frames, p["frame_step"])
    wf = {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": WAN21_I2V_GGUF if image_name else WAN21_T2V_GGUF}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": UMT5_FP8, "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": WAN21_VAE}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["2", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "11": _video_combine(["9", 0], fps or d["fps"], filename_prefix),
    }
    if image_name:
        wf["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["12"] = {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CLIP_VISION_H}}
        wf["13"] = {"class_type": "CLIPVisionEncode",
                    "inputs": {"clip_vision": ["12", 0], "image": ["10", 0], "crop": "none"}}
        wf["7"] = {"class_type": "WanImageToVideo", "inputs": {
            "positive": ["5", 0], "negative": ["6", 0], "vae": ["3", 0],
            "width": width, "height": height, "length": frames, "batch_size": 1,
            "clip_vision_output": ["13", 0], "start_image": ["10", 0]}}
        pos_ref, neg_ref, latent_ref = ["7", 0], ["7", 1], ["7", 2]
    else:
        wf["7"] = {"class_type": "EmptyHunyuanLatentVideo", "inputs": {
            "width": width, "height": height, "length": frames, "batch_size": 1}}
        pos_ref, neg_ref, latent_ref = ["5", 0], ["6", 0], ["7", 0]
    wf["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["4", 0], "seed": pick_seed(seed), "steps": int(steps or d["steps"]),
        "cfg": float(cfg if cfg is not None else d["cfg"]),
        "sampler_name": "uni_pc", "scheduler": "simple",
        "positive": pos_ref, "negative": neg_ref, "latent_image": latent_ref, "denoise": 1.0}}
    return wf


VIDEO_BUILDERS = {
    "wan22-5b": wan22_5b,
    "ltx": ltx_video,
    "wan21-14b": wan21_14b,
}


def build_video(preset: str, **kwargs) -> dict:
    if preset not in VIDEO_BUILDERS:
        raise ValueError(f"Unknown video preset '{preset}'. Choose one of: {', '.join(VIDEO_BUILDERS)}")
    return VIDEO_BUILDERS[preset](**kwargs)


def output_files(history_entry: dict) -> list[dict]:
    """Collect every saved file from a /history entry, regardless of node type.

    Returns dicts with filename, subfolder, type and the node id that produced it.
    """
    files: list[dict] = []
    for node_id, out in (history_entry.get("outputs") or {}).items():
        for key in ("images", "gifs", "videos", "audio", "files"):
            for item in out.get(key, []) or []:
                if isinstance(item, dict) and item.get("filename"):
                    files.append({
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output"),
                        "node": node_id,
                        "kind": "video" if key == "gifs" or item["filename"].lower().endswith((".mp4", ".webm", ".mkv")) else key.rstrip("s"),
                    })
    # de-duplicate (VHS reports the same mp4 under previews sometimes)
    seen = set()
    unique = []
    for f in files:
        key = (f["subfolder"], f["filename"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
