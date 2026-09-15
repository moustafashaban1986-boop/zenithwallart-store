"""Settings, provider catalog and voice catalog (the dropdown contents)."""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

PKG_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = PKG_DIR.parent
# claude-comfy (image/video generation) lives next to the assistant folder in the repo,
# and next to it again once installed under C:\ComfyUI.
COMFY_BRIDGE_CANDIDATES = [ASSISTANT_DIR.parent / "claude-comfy", ASSISTANT_DIR.parent.parent / "claude-comfy"]


def data_dir() -> Path:
    env = os.environ.get("LEGION_HOME")
    if env:
        p = Path(env)
    elif sys.platform.startswith("win"):
        p = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Legion"
    else:
        p = Path.home() / ".legion"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path() -> Path:
    return data_dir() / "settings.json"


# ---------------------------------------------------------------------------
# Provider catalog: everything the "Brain" dropdown can offer.
# kind: "openai" = OpenAI-compatible chat API, "anthropic" = Claude SDK.
# ---------------------------------------------------------------------------
PROVIDERS: dict[str, dict[str, Any]] = {
    "ollama": {
        "label": "Ollama (local, offline)",
        "kind": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "key_env": None,
        "offline": True,
        "models": ["qwen3:8b", "llama3.1:8b", "gemma3:12b", "deepseek-r1:8b", "qwen2.5-coder:7b", "phi4:14b", "mistral-nemo:12b"],
        "default_model": "qwen3:8b",
        "note": "Runs fully on your GPU. qwen3:8b / llama3.1:8b fit easily in 16 GB and support tool calling.",
    },
    "lmstudio": {
        "label": "LM Studio (local, offline)",
        "kind": "openai",
        "base_url": "http://127.0.0.1:1234/v1",
        "key_env": None,
        "offline": True,
        "models": [],
        "default_model": "",
        "note": "Any model loaded in LM Studio's local server.",
    },
    "anthropic": {
        "label": "Claude (Anthropic, online)",
        "kind": "anthropic",
        "base_url": None,
        "key_env": "ANTHROPIC_API_KEY",
        "offline": False,
        "models": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"],
        "default_model": "claude-opus-5",
        "note": "Best quality. Needs an API key from console.anthropic.com (paid).",
    },
    "moonshot": {
        "label": "Kimi K2 (Moonshot, online)",
        "kind": "openai",
        "base_url": "https://api.moonshot.ai/v1",
        "key_env": "MOONSHOT_API_KEY",
        "offline": False,
        "models": ["kimi-k2-0905-preview", "kimi-k2-turbo-preview", "kimi-latest"],
        "default_model": "kimi-k2-0905-preview",
        "note": "Kimi K2 is a 1-trillion-parameter model: it cannot run on a laptop, so it is used via API (platform.moonshot.ai).",
    },
    "groq": {
        "label": "Groq (free tier, online, very fast)",
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "offline": False,
        "models": ["llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b", "openai/gpt-oss-120b"],
        "default_model": "llama-3.3-70b-versatile",
        "note": "Free key at console.groq.com. Also hosts Kimi K2.",
    },
    "openrouter": {
        "label": "OpenRouter (free models, online)",
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "offline": False,
        "models": ["moonshotai/kimi-k2:free", "deepseek/deepseek-r1:free", "qwen/qwen3-235b-a22b:free", "meta-llama/llama-3.3-70b-instruct:free"],
        "default_model": "moonshotai/kimi-k2:free",
        "note": "Free key at openrouter.ai. The model list is refreshed live (models ending in :free).",
    },
    "gemini": {
        "label": "Google Gemini (free tier, online)",
        "kind": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "offline": False,
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "default_model": "gemini-2.5-flash",
        "note": "Free key at aistudio.google.com.",
    },
    "deepseek": {
        "label": "DeepSeek (online, cheap)",
        "kind": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "offline": False,
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
        "note": "Key at platform.deepseek.com.",
    },
}

# Voices for the "Voice" dropdown. Kokoro ids: <lang><gender>_<name> (a=American, b=British).
KOKORO_VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "am_fenrir", "am_puck",
    "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
]

IMAGE_MODELS = {"flux-schnell": "FLUX.1 schnell (local, ComfyUI)"}
VIDEO_MODELS = {
    "wan22-5b": "Wan 2.2 5B (local, best on 16GB)",
    "ltx": "LTX-Video 2B (local, fastest)",
    "wan21-14b": "Wan 2.1 14B GGUF (local, highest quality, slow)",
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "provider": "ollama",
    "model": "qwen3:8b",
    "api_keys": {},                # provider -> key (env vars override)
    "tts_engine": "auto",          # auto | kokoro | windows | none
    "voice": "af_heart",           # kokoro id, "windows:<name>" or "clone:<name>"
    "speech_rate": 1.0,
    "stt_model": "small",          # faster-whisper size: tiny | base | small | medium | large-v3
    "stt_language": None,          # None = auto-detect (Arabic, English, ... all work)
    "image_model": "flux-schnell",
    "video_model": "wan22-5b",
    "safe_mode": True,             # dangerous tools need explicit approval
    "workspace": str(Path.home()),
    "comfy_url": "http://127.0.0.1:8188",
    "web_port": 7860,
    "wake_word": "",               # optional word the voice loop waits for, e.g. "legion"
    "language": "auto",
    "system_prompt_extra": "",
}


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or settings_path()
        self.data: dict[str, Any] = deepcopy(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> "Settings":
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                for k, v in stored.items():
                    if k in DEFAULT_SETTINGS:
                        self.data[k] = v
            except Exception:
                pass
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def update(self, changes: dict[str, Any]) -> None:
        for k, v in changes.items():
            if k in DEFAULT_SETTINGS:
                self.data[k] = v
        self.save()

    def api_key(self, provider: str) -> str | None:
        info = PROVIDERS.get(provider, {})
        env = info.get("key_env")
        if env and os.environ.get(env):
            return os.environ[env]
        return (self.data.get("api_keys") or {}).get(provider) or None

    def public(self) -> dict[str, Any]:
        """Settings safe to show in the UI (keys masked)."""
        out = deepcopy(self.data)
        out["api_keys"] = {k: ("set" if v else "") for k, v in (self.data.get("api_keys") or {}).items()}
        out["env_keys"] = {p: bool(os.environ.get(i["key_env"])) for p, i in PROVIDERS.items() if i.get("key_env")}
        return out


def comfy_bridge_dir() -> Path | None:
    env = os.environ.get("COMFY_BRIDGE_DIR")
    if env and Path(env).exists():
        return Path(env)
    for c in COMFY_BRIDGE_CANDIDATES:
        if (c / "server.py").exists():
            return c
    return None
