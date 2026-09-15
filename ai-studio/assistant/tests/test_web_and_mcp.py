"""Web UI endpoints (FastAPI TestClient) and the MCP server over stdio.

Run:  python tests/test_web_and_mcp.py   (needs fastapi, httpx, mcp)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LEGION_HOME"] = tempfile.mkdtemp(prefix="legion-web-")

from fastapi.testclient import TestClient  # noqa: E402

from legion import web_ui  # noqa: E402
from legion.providers import Provider  # noqa: E402


class EchoProvider(Provider):
    name = "echo"

    def chat(self, system, history, tools):
        last = history[-1]
        if last["role"] == "user" and last["content"].startswith("dir "):
            return {"content": "", "tool_calls": [{"id": "t1", "name": "list_dir", "arguments": {"path": last["content"][4:]}}]}
        if last["role"] == "user" and last["content"].startswith("del "):
            return {"content": "", "tool_calls": [{"id": "t2", "name": "delete_path", "arguments": {"path": last["content"][4:]}}]}
        if last["role"] == "tool":
            return {"content": "tool said: " + last["content"][:40], "tool_calls": []}
        return {"content": "echo: " + last["content"], "tool_calls": []}

    def is_available(self):
        return True, "fake"


def test_web_ui():
    web_ui._agent.provider = EchoProvider()
    web_ui._settings.update({"safe_mode": True})
    c = TestClient(web_ui.app)
    assert "<title>Legion</title>" in c.get("/").text
    cfg = c.get("/api/config").json()
    assert {p["id"] for p in cfg["providers"]} >= {"ollama", "anthropic", "moonshot", "groq", "openrouter", "gemini"}
    assert "wan22-5b" in cfg["video_models"] and "flux-schnell" in cfg["image_models"]
    print("PASS /api/config")

    r = c.post("/api/chat", json={"text": "hello"}).json()
    assert r["text"] == "echo: hello" and r["needs_approval"] is None
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "x.txt").write_text("1")
        r = c.post("/api/chat", json={"text": f"dir {td}"}).json()
        assert r["tool_events"][0]["tool"] == "list_dir" and "x.txt" in r["tool_events"][0]["result"]
        assert r["text"].startswith("tool said:")
        r = c.post("/api/chat", json={"text": f"del {td}/x.txt"}).json()
        assert r["needs_approval"][0]["name"] == "delete_path" and (Path(td) / "x.txt").exists()
        r = c.post("/api/chat", json={"action": "decline"}).json()
        assert (Path(td) / "x.txt").exists() and "declined" in r["tool_events"][0]["result"].lower()
    print("PASS /api/chat with tools + approval")

    r = c.post("/api/config", json={"voice": "am_adam", "api_keys": {"groq": "gsk_test"}}).json()
    assert r["settings"]["voice"] == "am_adam" and r["settings"]["api_keys"]["groq"] == "set"
    assert web_ui._settings.api_key("groq") == "gsk_test"
    r = c.get("/api/models?provider=anthropic").json()
    assert r["suggested"] == ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
    assert c.get("/api/models?provider=nope").status_code == 404
    h = c.get("/api/health").json()
    assert h["tools"] > 20 and "brain" in h and "speech" in h
    assert c.get("/api/file?path=/etc/passwd").status_code == 403
    print("PASS config/models/health/file guard")


async def _mcp_scenario():
    try:
        from mcp.client.stdio import StdioServerParameters, stdio_client
        from mcp.client.session import ClientSession
    except ImportError:
        from mcp import ClientSession, StdioServerParameters  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore
    env = {**os.environ, "LEGION_HOME": tempfile.mkdtemp(prefix="legion-mcp-")}
    # run_legion.py is what the installed launchers and the Claude config use (embedded Python ignores -m legion)
    params = StdioServerParameters(command=sys.executable, args=["-s", str(ROOT / "run_legion.py"), "mcp"], env=env, cwd="/")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            for n in ("run_command", "list_dir", "screenshot", "generate_image", "generate_video", "speak", "legion_status"):
                assert n in names, n
            res = await s.call_tool("system_info", {})
            body = json.loads("".join(c.text for c in res.content if c.type == "text"))
            assert "os" in body
            res = await s.call_tool("run_command", {"command": "echo hi"})
            txt = "".join(c.text for c in res.content if c.type == "text")
            assert txt.startswith("BLOCKED"), txt  # safe mode default
            with tempfile.TemporaryDirectory() as td:
                res = await s.call_tool("list_dir", {"path": td})
                assert "(empty)" in "".join(c.text for c in res.content if c.type == "text")
            print("PASS mcp: tools listed, safe tool ran, dangerous tool blocked by safe mode")


def test_mcp():
    asyncio.run(_mcp_scenario())


if __name__ == "__main__":
    test_web_ui()
    test_mcp()
    print("ALL WEB + MCP TESTS PASSED")
