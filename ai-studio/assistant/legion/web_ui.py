"""Local web UI: chat, microphone, spoken replies, and dropdowns for brain / model / voice / image / video.

    python -m legion serve        ->  http://127.0.0.1:7860
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .agent import Agent, describe_provider
from .config import IMAGE_MODELS, KOKORO_VOICES, PROVIDERS, VIDEO_MODELS, Settings
from .providers import make_provider, ollama_installed_models
from .speech import STT, TTS

app = FastAPI(title="Legion")
_settings = Settings()
_agent = Agent(_settings)
_lock = threading.Lock()
HTML_PATH = Path(__file__).with_name("ui.html")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_PATH.read_text(encoding="utf-8")


@app.get("/api/config")
def get_config():
    providers = []
    for pid, info in PROVIDERS.items():
        providers.append({"id": pid, "label": info["label"], "offline": info["offline"],
                          "needs_key": bool(info.get("key_env")), "has_key": bool(_settings.api_key(pid)),
                          "key_env": info.get("key_env"), "note": info["note"], "models": info["models"],
                          "default_model": info["default_model"]})
    tts = TTS(_settings)
    voices = tts.available_voices()
    return {
        "settings": _settings.public(),
        "providers": providers,
        "voices": voices,
        "kokoro_voices": KOKORO_VOICES,
        "image_models": IMAGE_MODELS,
        "video_models": VIDEO_MODELS,
        "current": describe_provider(_settings),
    }


@app.post("/api/config")
async def set_config(payload: dict):
    changes = {k: v for k, v in payload.items() if k != "api_keys"}
    if "api_keys" in payload and isinstance(payload["api_keys"], dict):
        keys = dict(_settings.get("api_keys") or {})
        for k, v in payload["api_keys"].items():
            if v == "":
                keys.pop(k, None)
            elif v and v != "set":
                keys[k] = v
        changes["api_keys"] = keys
    if "provider" in changes or "model" in changes or "api_keys" in changes:
        _agent.provider = None
    _settings.update(changes)
    return {"ok": True, "settings": _settings.public()}


@app.get("/api/models")
def list_models(provider: str):
    info = PROVIDERS.get(provider)
    if not info:
        raise HTTPException(404, "unknown provider")
    if provider == "ollama":
        live = ollama_installed_models()
        return {"installed": live, "suggested": info["models"], "available": live or []}
    key = _settings.api_key(provider)
    if info.get("key_env") and not key:
        return {"installed": [], "suggested": info["models"], "available": [], "error": f"Add a {info['key_env']} first"}
    try:
        live = make_provider(provider, info["default_model"], key).list_models()
    except Exception as e:
        return {"installed": [], "suggested": info["models"], "available": [], "error": str(e)}
    return {"installed": live, "suggested": info["models"], "available": live}


@app.post("/api/ollama/pull")
def ollama_pull(payload: dict):
    """Download a model into Ollama (streams progress to Ollama's own console)."""
    import httpx
    name = payload.get("model", "")
    if not name:
        raise HTTPException(400, "model required")
    try:
        with httpx.stream("POST", "http://127.0.0.1:11434/api/pull", json={"name": name, "stream": True}, timeout=None) as r:
            last = ""
            for line in r.iter_lines():
                if line:
                    last = line
        return {"ok": True, "last": last}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/chat")
def chat(payload: dict):
    text = (payload.get("text") or "").strip()
    action = payload.get("action")
    with _lock:
        if action == "approve":
            result = _agent.approve(True)
        elif action == "decline":
            result = _agent.approve(False)
        elif action == "reset":
            _agent.reset()
            return {"text": "New conversation.", "tool_events": []}
        elif text:
            result = _agent.ask(text, approve_all=not _settings.get("safe_mode", True))
        else:
            raise HTTPException(400, "text required")
    return {"text": result.text, "tool_events": result.tool_events,
            "needs_approval": result.needs_approval, "error": result.error,
            "brain": describe_provider(_settings)}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form("")):
    data = await audio.read()
    suffix = Path(audio.filename or "a.webm").suffix or ".webm"
    try:
        text = STT(_settings).transcribe_bytes(data, suffix=suffix, language=language or None)
    except Exception as e:
        return JSONResponse({"error": f"transcription failed: {e}"}, status_code=500)
    return {"text": text}


@app.post("/api/tts")
def tts(payload: dict):
    text = (payload.get("text") or "")[:3000]
    try:
        path = TTS(_settings).synthesize(text, voice=payload.get("voice"), play=False)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    if not path:
        return JSONResponse({"error": "no TTS engine available (install kokoro or use a Windows voice)"}, status_code=503)
    return FileResponse(str(path), media_type="audio/wav")


@app.get("/api/file")
def get_file(path: str):
    p = Path(path)
    if not p.is_file():
        raise HTTPException(404)
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".wav", ".mp3"):
        raise HTTPException(403, "only media files can be served")
    return FileResponse(str(p))


@app.get("/api/health")
def health():
    from .speech import doctor
    from .tools import REGISTRY
    prov = describe_provider(_settings)
    try:
        ok, why = _agent.get_provider().is_available()
    except Exception as e:
        ok, why = False, str(e)
    return {"brain": {**prov, "available": ok, "detail": why}, "speech": doctor(), "tools": len(REGISTRY)}


def serve(port: int | None = None) -> int:
    import uvicorn
    import webbrowser
    port = port or int(_settings.get("web_port", 7860))
    url = f"http://127.0.0.1:{port}"
    print(f"Legion web UI -> {url}")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0
