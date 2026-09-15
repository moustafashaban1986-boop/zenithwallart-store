"""Expose every Legion tool to Claude Desktop / Claude Code over MCP (stdio).

    python -m legion mcp

Claude then gets run_command, files, apps, screenshots, mouse/keyboard, speak/listen,
generate_image/generate_video ... on this PC. Dangerous tools are blocked while
safe_mode is on unless LEGION_MCP_ALLOW_DANGEROUS=1 is set in the server env.
"""
from __future__ import annotations

import inspect
import os
import sys
import typing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

from legion.config import Settings
from legion.tools import REGISTRY, load_all, run_tool

INSTRUCTIONS = """Legion gives you hands on the user's own Windows PC: shell, files, apps, screenshots,
mouse/keyboard, clipboard, speech (speak / transcribe_audio / clone_voice) and local image & video generation
(generate_image / generate_video via ComfyUI). Prefer specific tools over run_command. Tools marked DANGEROUS
change the system; use them only when the user clearly asked for that action."""

mcp = _Server("legion", instructions=INSTRUCTIONS)
_settings = Settings()
_allow_dangerous = os.environ.get("LEGION_MCP_ALLOW_DANGEROUS", "").lower() in ("1", "true", "yes")


def _make_wrapper(name: str):
    t = REGISTRY[name]
    orig = inspect.signature(t.fn)
    try:
        hints = typing.get_type_hints(t.fn)
    except Exception:
        hints = {}
    # Real (non-string) parameter annotations, and a str return: run_tool always returns text.
    params = [p.replace(annotation=hints.get(p.name, str if p.annotation is inspect._empty else p.annotation))
              for p in orig.parameters.values() if not p.name.startswith("_")]
    sig = orig.replace(parameters=params, return_annotation=str)

    def wrapper(**kwargs):
        if t.dangerous and _settings.get("safe_mode", True) and not _allow_dangerous:
            return ("BLOCKED: Legion safe mode is on. Turn it off in the Legion web UI (Safe mode switch) or set "
                    "LEGION_MCP_ALLOW_DANGEROUS=1 in the MCP server env to allow this action.")
        return run_tool(name, kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = t.description + ("  [DANGEROUS]" if t.dangerous else "")
    wrapper.__signature__ = sig  # type: ignore[attr-defined]
    return wrapper


def register_all():
    load_all()
    for name in sorted(REGISTRY):
        mcp.tool(name=name, description=REGISTRY[name].description)(_make_wrapper(name))


register_all()


@mcp.tool()
def legion_status() -> str:
    """Show Legion's current brain (provider/model), voice, safe-mode state and tool count."""
    import json
    from legion.agent import describe_provider
    return json.dumps({**describe_provider(_settings), "voice": _settings.get("voice"),
                       "safe_mode": _settings.get("safe_mode"), "tools": len(REGISTRY)}, indent=2)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
