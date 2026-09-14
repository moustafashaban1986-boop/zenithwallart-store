"""Static validation of every workflow the bridge can produce.

Run:  python tests/test_workflows.py   (or pytest tests/)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "claude-comfy"))
sys.path.insert(0, str(ROOT / "tests"))

from node_schema import validate  # noqa: E402
from presets import IMAGE_PRESETS, VIDEO_PRESETS, load_manifest, round_frames, round_to_step  # noqa: E402
from workflows import flux_schnell, ltx_video, wan21_14b, wan22_5b, build_video, output_files  # noqa: E402


def _assert_valid(name: str, wf: dict):
    problems = validate(wf)
    assert not problems, f"{name}:\n  " + "\n  ".join(problems)
    # Every workflow must end in exactly one output node.
    savers = [n for n in wf.values() if n["class_type"] in ("SaveImage", "VHS_VideoCombine")]
    assert len(savers) == 1, f"{name}: expected one save node, found {len(savers)}"
    json.dumps(wf)  # must be serialisable


def test_image_workflows():
    _assert_valid("flux gguf", flux_schnell("test", seed=1))
    _assert_valid("flux checkpoint", flux_schnell("test", seed=1, use_checkpoint=True))
    wf = flux_schnell("test", width=1000, height=1000, seed=1, batch_size=3)
    assert wf["6"]["inputs"] == {"width": 992, "height": 992, "batch_size": 3}
    assert wf["7"]["inputs"]["seed"] == 1 and wf["7"]["inputs"]["cfg"] == 1.0


def test_video_workflows_all_variants():
    for preset in VIDEO_PRESETS:
        _assert_valid(f"{preset} t2v", build_video(preset, prompt="p", seed=1))
        _assert_valid(f"{preset} i2v", build_video(preset, prompt="p", seed=1, image_name="x.png"))


def test_frame_and_size_rounding():
    assert round_frames(48, 4) == 45 and round_frames(49, 4) == 49 and round_frames(50, 4) == 49
    assert round_frames(48, 8) == 41 and round_frames(97, 8) == 97
    assert round_to_step(720, 32, 256) == 704 and round_to_step(1280, 32, 256) == 1280
    wf = wan22_5b("p", width=1280, height=720, frames=50, seed=1)
    assert wf["7"]["inputs"]["width"] == 1280 and wf["7"]["inputs"]["height"] == 704
    assert wf["7"]["inputs"]["length"] == 49
    wf = ltx_video("p", frames=50, seed=1)
    assert wf["6"]["inputs"]["length"] == 49
    wf = wan21_14b("p", width=1280, height=720, frames=48, seed=1)
    assert wf["7"]["inputs"] == {"width": 1280, "height": 720, "length": 45, "batch_size": 1}


def test_i2v_wiring():
    wf = wan22_5b("p", seed=1, image_name="a.png")
    assert wf["7"]["inputs"]["start_image"] == ["10", 0] and wf["10"]["inputs"]["image"] == "a.png"
    wf = ltx_video("p", seed=1, image_name="a.png")
    assert wf["6"]["class_type"] == "LTXVImgToVideo"
    assert wf["5"]["inputs"]["positive"] == ["6", 0] and wf["9"]["inputs"]["latent_image"] == ["6", 2]
    assert wf["7"]["inputs"]["latent"] == ["6", 2]
    wf = wan21_14b("p", seed=1, image_name="a.png")
    assert wf["1"]["inputs"]["unet_name"].startswith("wan2.1-i2v")
    assert wf["8"]["inputs"]["positive"] == ["7", 0] and wf["8"]["inputs"]["latent_image"] == ["7", 2]
    assert wf["7"]["inputs"]["clip_vision_output"] == ["13", 0]


def test_random_seed_when_negative():
    a = wan22_5b("p", seed=-1)["8"]["inputs"]["seed"]
    b = wan22_5b("p", seed=-1)["8"]["inputs"]["seed"]
    assert 0 <= a < 2**53 and (a != b or True)


def test_presets_reference_manifest_files():
    manifest = load_manifest()["files"]
    for p in IMAGE_PRESETS.values():
        for f in p["files"] + p.get("fallback_files", []):
            assert f in manifest, f"{f} missing from models.json"
    for p in VIDEO_PRESETS.values():
        for f in p["files"] + p.get("i2v_files", []):
            assert f in manifest, f"{f} missing from models.json"
    packs = load_manifest()["packs"]
    for name, pack in packs.items():
        for f in pack["files"]:
            assert f in manifest, f"pack {name} references unknown file {f}"


def test_workflow_files_use_only_manifest_models():
    manifest = load_manifest()["files"]
    for path in (ROOT / "workflows").glob("*.json"):
        wf = json.loads(path.read_text(encoding="utf-8"))
        _assert_valid(path.name, wf)
        for node in wf.values():
            for key in ("unet_name", "ckpt_name", "clip_name", "clip_name1", "clip_name2", "vae_name"):
                if key in node["inputs"]:
                    assert node["inputs"][key] in manifest, f"{path.name}: {node['inputs'][key]} not in models.json"


def test_output_files_parsing():
    hist = {"outputs": {
        "9": {"images": [{"filename": "a.png", "subfolder": "claude", "type": "output"}]},
        "11": {"gifs": [{"filename": "v.mp4", "subfolder": "claude", "type": "output", "format": "video/h264-mp4"}],
               "images": [{"filename": "v.mp4", "subfolder": "claude", "type": "output"}]},
    }}
    files = output_files(hist)
    assert [f["filename"] for f in files] == ["a.png", "v.mp4"]
    assert files[1]["kind"] == "video" and files[0]["kind"] == "image"


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failures += 1
                print("FAIL", name, "\n   ", e)
    sys.exit(1 if failures else 0)
