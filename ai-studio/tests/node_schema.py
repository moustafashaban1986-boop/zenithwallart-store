"""Input/output signatures of every ComfyUI node used by the workflows.

Transcribed from ComfyUI v0.35 (nodes.py, comfy_extras/nodes_*.py),
ComfyUI-GGUF/nodes.py and ComfyUI-VideoHelperSuite/videohelpersuite/nodes.py.
required = must be present, optional = may be present, outputs = number of output slots.
"""

NODES = {
    # loaders
    "UnetLoaderGGUF": {"required": {"unet_name"}, "optional": set(), "outputs": 1},
    "UNETLoader": {"required": {"unet_name", "weight_dtype"}, "optional": set(), "outputs": 1},
    "CheckpointLoaderSimple": {"required": {"ckpt_name"}, "optional": set(), "outputs": 3},
    "DualCLIPLoader": {"required": {"clip_name1", "clip_name2", "type"}, "optional": {"device"}, "outputs": 1},
    "CLIPLoader": {"required": {"clip_name", "type"}, "optional": {"device"}, "outputs": 1},
    "VAELoader": {"required": {"vae_name"}, "optional": set(), "outputs": 1},
    "CLIPVisionLoader": {"required": {"clip_name"}, "optional": set(), "outputs": 1},
    "LoadImage": {"required": {"image"}, "optional": set(), "outputs": 2},
    # conditioning
    "CLIPTextEncode": {"required": {"text", "clip"}, "optional": set(), "outputs": 1},
    "ConditioningZeroOut": {"required": {"conditioning"}, "optional": set(), "outputs": 1},
    "CLIPVisionEncode": {"required": {"clip_vision", "image", "crop"}, "optional": set(), "outputs": 1},
    "LTXVConditioning": {"required": {"positive", "negative", "frame_rate"}, "optional": set(), "outputs": 2},
    "WanImageToVideo": {"required": {"positive", "negative", "vae", "width", "height", "length", "batch_size"},
                        "optional": {"clip_vision_output", "start_image"}, "outputs": 3},
    "LTXVImgToVideo": {"required": {"positive", "negative", "vae", "image", "width", "height", "length",
                                    "batch_size", "strength"}, "optional": set(), "outputs": 3},
    # latents
    "EmptySD3LatentImage": {"required": {"width", "height", "batch_size"}, "optional": set(), "outputs": 1},
    "EmptyHunyuanLatentVideo": {"required": {"width", "height", "length", "batch_size"}, "optional": set(), "outputs": 1},
    "EmptyLTXVLatentVideo": {"required": {"width", "height", "length", "batch_size"}, "optional": set(), "outputs": 1},
    "Wan22ImageToVideoLatent": {"required": {"vae", "width", "height", "length", "batch_size"},
                                "optional": {"start_image"}, "outputs": 1},
    # sampling
    "ModelSamplingSD3": {"required": {"model", "shift"}, "optional": set(), "outputs": 1},
    "KSampler": {"required": {"model", "seed", "steps", "cfg", "sampler_name", "scheduler", "positive",
                              "negative", "latent_image", "denoise"}, "optional": set(), "outputs": 1},
    "KSamplerSelect": {"required": {"sampler_name"}, "optional": set(), "outputs": 1},
    "LTXVScheduler": {"required": {"steps", "max_shift", "base_shift", "stretch", "terminal"},
                      "optional": {"latent"}, "outputs": 1},
    "SamplerCustom": {"required": {"model", "add_noise", "noise_seed", "cfg", "positive", "negative",
                                   "sampler", "sigmas", "latent_image"}, "optional": set(), "outputs": 2},
    # decode / save
    "VAEDecode": {"required": {"samples", "vae"}, "optional": set(), "outputs": 1},
    "SaveImage": {"required": {"images", "filename_prefix"}, "optional": set(), "outputs": 0},
    "VHS_VideoCombine": {"required": {"images", "frame_rate", "loop_count", "filename_prefix", "format",
                                      "pingpong", "save_output"},
                         # format-specific widgets for video/h264-mp4 (video_formats/h264-mp4.json)
                         "optional": {"audio", "meta_batch", "vae", "pix_fmt", "crf", "save_metadata", "trim_to_audio"},
                         "outputs": 1},
}

# Allowed combo values we rely on.
COMBOS = {
    ("CLIPLoader", "type"): {"wan", "ltxv"},
    ("DualCLIPLoader", "type"): {"flux"},
    ("CLIPVisionEncode", "crop"): {"center", "none"},
    ("KSampler", "sampler_name"): {"euler", "uni_pc"},
    ("KSampler", "scheduler"): {"simple"},
    ("KSamplerSelect", "sampler_name"): {"euler"},
    ("VHS_VideoCombine", "format"): {"video/h264-mp4"},
    ("UNETLoader", "weight_dtype"): {"default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"},
}


def validate(workflow: dict) -> list[str]:
    """Return a list of problems (empty when the workflow is well-formed)."""
    problems = []
    for nid, node in workflow.items():
        cls = node.get("class_type")
        if cls not in NODES:
            problems.append(f"{nid}: unknown node class {cls}")
            continue
        spec = NODES[cls]
        inputs = node.get("inputs", {})
        missing = spec["required"] - set(inputs)
        extra = set(inputs) - spec["required"] - spec["optional"]
        if missing:
            problems.append(f"{nid} ({cls}): missing inputs {sorted(missing)}")
        if extra:
            problems.append(f"{nid} ({cls}): unexpected inputs {sorted(extra)}")
        for name, val in inputs.items():
            if isinstance(val, list):
                if len(val) != 2 or not isinstance(val[0], str) or not isinstance(val[1], int):
                    problems.append(f"{nid}.{name}: malformed link {val}")
                    continue
                src, idx = val
                if src not in workflow:
                    problems.append(f"{nid}.{name}: links to missing node {src}")
                elif idx >= NODES.get(workflow[src]["class_type"], {}).get("outputs", 0):
                    problems.append(f"{nid}.{name}: output index {idx} out of range for {workflow[src]['class_type']}")
            allowed = COMBOS.get((cls, name))
            if allowed is not None and val not in allowed:
                problems.append(f"{nid}.{name}: value {val!r} not in {sorted(allowed)}")
    return problems
