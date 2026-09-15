"""Command line entry point.  python -m legion <command>

  serve            start the web UI (http://127.0.0.1:7860)
  chat             text chat in the terminal
  voice [--ptt]    hands-free voice loop in the terminal
  mcp              run as an MCP server for Claude Desktop / Claude Code
  doctor           check brain, ears, voice, hands and ComfyUI
  models           list models per provider
  set KEY VALUE    change a setting (e.g. set provider anthropic, set model claude-opus-5, set voice am_adam)
  key PROVIDER K   store an API key (e.g. key groq gsk_...)
"""
from __future__ import annotations

import json
import sys

from .config import PROVIDERS, Settings, settings_path


def cmd_doctor() -> int:
    from .providers import OpenAICompatProvider, ollama_installed_models
    from .speech import doctor as speech_doctor
    from .tools import load_all
    s = Settings()
    print(f"Settings file: {settings_path()}")
    print(f"Brain: {s.get('provider')} / {s.get('model')}")
    ok, why = OpenAICompatProvider("ollama", "x").is_available()
    print(f"  Ollama: {'running' if ok else 'NOT running'} ({why})")
    if ok:
        print(f"  Ollama models: {', '.join(ollama_installed_models()) or 'none pulled yet -> ollama pull qwen3:8b'}")
    for p, info in PROVIDERS.items():
        if info.get("key_env"):
            print(f"  {info['label']}: key {'set' if s.api_key(p) else 'missing'}")
    print("Speech:")
    for k, v in speech_doctor().items():
        print(f"  {k}: {v}")
    print(f"Tools: {len(load_all())} registered")
    try:
        from .tools.media import comfy_status
        print(f"ComfyUI: {json.dumps(comfy_status())}")
    except Exception as e:
        print(f"ComfyUI: {e}")
    return 0


def cmd_models() -> int:
    from .providers import make_provider, ollama_installed_models
    s = Settings()
    for pid, info in PROVIDERS.items():
        print(f"\n{pid}: {info['label']}")
        if pid == "ollama":
            live = ollama_installed_models()
            print("  installed:", ", ".join(live) or "(none)")
            print("  suggested:", ", ".join(info["models"]))
            continue
        key = s.api_key(pid)
        if info.get("key_env") and not key:
            print(f"  (add a key with: python -m legion key {pid} <KEY>)  suggested: {', '.join(info['models'])}")
            continue
        try:
            live = make_provider(pid, info["default_model"], key).list_models()
            print("  available:", ", ".join(live[:40]) or ", ".join(info["models"]))
        except Exception as e:
            print(f"  error: {e}")
    return 0


def cmd_chat() -> int:
    from .agent import Agent
    agent = Agent()
    print(f"Legion chat ({agent.settings.get('provider')}/{agent.settings.get('model')}). Type 'quit' to exit, 'yes'/'no' to answer approvals.")
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if not text:
            continue
        if text.lower() in ("quit", "exit"):
            return 0
        if agent.pending and text.lower() in ("yes", "y", "approve"):
            r = agent.approve(True)
        elif agent.pending and text.lower() in ("no", "n", "decline"):
            r = agent.approve(False)
        else:
            r = agent.ask(text)
        for ev in r.tool_events:
            print(f"  [tool] {ev['tool']}({json.dumps(ev['arguments'], ensure_ascii=False)[:100]}) -> {ev['result'][:150].replace(chr(10), ' ')}")
        print(f"Legion: {r.text}")
        if r.needs_approval:
            print("  -> type yes to approve, no to decline")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "serve":
        from .web_ui import serve
        port = int(rest[0]) if rest else None
        return serve(port)
    if cmd == "chat":
        return cmd_chat()
    if cmd == "voice":
        from .voice_loop import run
        return run(ptt="--ptt" in rest)
    if cmd == "mcp":
        from .mcp_server import main as mcp_main
        mcp_main()
        return 0
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "models":
        return cmd_models()
    if cmd == "set" and len(rest) >= 2:
        s = Settings()
        key, value = rest[0], " ".join(rest[1:])
        if value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        s.update({key: value})
        print(f"{key} = {value}")
        return 0
    if cmd == "key" and len(rest) == 2:
        s = Settings()
        keys = dict(s.get("api_keys") or {})
        keys[rest[0]] = rest[1]
        s.update({"api_keys": keys})
        print(f"stored key for {rest[0]} in {settings_path()}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
