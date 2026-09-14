"""Write the API-format workflows to ../workflows/*.json.

These files can be loaded in the ComfyUI web UI (Workflow > Open, or drag & drop)
and are also what the MCP server sends to ComfyUI. Re-run after editing workflows.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflows import flux_schnell, ltx_video, wan21_14b, wan22_5b  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "workflows"

PROMPT_IMG = "a framed minimalist abstract wall art print, warm earth tones, soft studio lighting, product photo"
PROMPT_VID = "slow cinematic camera push-in on a framed abstract painting hanging in a bright modern living room, sunlight moving across the wall"

EXPORTS = {
    "image_flux_schnell_gguf.json": lambda: flux_schnell(PROMPT_IMG, seed=42),
    "image_flux_schnell_fp8_checkpoint.json": lambda: flux_schnell(PROMPT_IMG, seed=42, use_checkpoint=True),
    "video_wan22_5b_text_to_video.json": lambda: wan22_5b(PROMPT_VID, seed=42),
    "video_wan22_5b_image_to_video.json": lambda: wan22_5b(PROMPT_VID, seed=42, image_name="example.png"),
    "video_ltx_text_to_video.json": lambda: ltx_video(PROMPT_VID, seed=42),
    "video_ltx_image_to_video.json": lambda: ltx_video(PROMPT_VID, seed=42, image_name="example.png"),
    "video_wan21_14b_gguf_text_to_video.json": lambda: wan21_14b(PROMPT_VID, seed=42),
    "video_wan21_14b_gguf_image_to_video.json": lambda: wan21_14b(PROMPT_VID, seed=42, image_name="example.png"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in EXPORTS.items():
        with open(OUT / name, "w", encoding="utf-8") as fh:
            json.dump(fn(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
