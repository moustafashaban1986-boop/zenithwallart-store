"""Agent loop, tool registry, settings and provider message conversion - no network, no GPU.

Run:  python tests/test_agent.py   (or pytest tests/)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["LEGION_HOME"] = tempfile.mkdtemp(prefix="legion-test-")

from legion.agent import Agent, system_prompt  # noqa: E402
from legion.config import PROVIDERS, Settings  # noqa: E402
from legion.providers import AnthropicProvider, OpenAICompatProvider, Provider  # noqa: E402
from legion.tools import load_all, run_tool, tool_specs  # noqa: E402


class FakeProvider(Provider):
    """Replays scripted replies; records what it was sent."""
    name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, system, history, tools):
        self.calls.append({"system": system, "history": [dict(h) for h in history], "tools": tools})
        if not self.script:
            return {"content": "done", "tool_calls": []}
        return self.script.pop(0)


def _settings(**over) -> Settings:
    s = Settings(Path(os.environ["LEGION_HOME"]) / f"s_{len(os.listdir(os.environ['LEGION_HOME']))}.json")
    s.update(over)
    return s


def test_registry_and_schema():
    reg = load_all()
    for name in ("run_command", "list_dir", "read_file", "screenshot", "generate_image", "generate_video", "speak", "web_search", "open_app"):
        assert name in reg, name
    specs = {t["name"]: t for t in tool_specs()}
    ld = specs["list_dir"]["parameters"]
    assert ld["properties"]["path"]["type"] == "string" and ld["properties"]["show_hidden"]["type"] == "boolean"
    assert "required" in ld and ld["required"] == []
    rc = specs["run_command"]
    assert "DANGEROUS" in rc["description"] and rc["parameters"]["required"] == ["command"]
    assert specs["mouse"]["parameters"]["properties"]["x"]["type"] == "integer"
    assert "description" in ld["properties"]["pattern"]
    json.dumps(specs)


def test_run_tool_safe_ones():
    load_all()
    out = json.loads(run_tool("system_info", {}))
    assert "os" in out and "time" in out
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.txt"
        assert "Wrote" in run_tool("write_file", {"path": str(p), "content": "hello"})
        assert run_tool("read_file", {"path": str(p)}) == "hello"
        assert "a.txt" in run_tool("list_dir", {"path": td})
        assert str(p) in run_tool("search_files", {"query": "*.txt", "root": td})
        assert "hello" not in run_tool("search_files", {"query": "nothing-here", "root": td, "content": True})
        info = json.loads(run_tool("file_info", {"path": str(p)}))
        assert info["size_bytes"] == 5
    assert run_tool("nope", {}).startswith("Error: unknown tool")
    assert "missing required" in run_tool("read_file", {})
    # extra/unknown args are ignored, errors are strings not exceptions
    assert "not found" in run_tool("read_file", {"path": "/definitely/not/here", "bogus": 1})


def test_agent_plain_answer():
    agent = Agent(_settings(), provider=FakeProvider([{"content": "Hello!", "tool_calls": []}]))
    r = agent.ask("hi")
    assert r.text == "Hello!" and r.tool_events == [] and r.needs_approval is None
    assert agent.history[-1]["role"] == "assistant"
    assert "Legion" in agent.provider.calls[0]["system"]


def test_agent_runs_safe_tool_then_answers():
    fp = FakeProvider([
        {"content": "", "tool_calls": [{"id": "c1", "name": "system_info", "arguments": {}}]},
        {"content": "You are on {os}", "tool_calls": []},
    ])
    agent = Agent(_settings(), provider=fp)
    r = agent.ask("what os?")
    assert r.tool_events and r.tool_events[0]["tool"] == "system_info"
    # second call must include the tool result in history
    hist = fp.calls[1]["history"]
    assert hist[-1]["role"] == "tool" and hist[-1]["tool_call_id"] == "c1" and '"os"' in hist[-1]["content"]
    assert r.text.startswith("You are on")


def test_dangerous_tool_requires_approval_then_runs():
    with tempfile.TemporaryDirectory() as td:
        target = str(Path(td) / "note.txt")
        fp = FakeProvider([
            {"content": "", "tool_calls": [{"id": "w1", "name": "write_file", "arguments": {"path": target, "content": "x"}}]},
            {"content": "Saved.", "tool_calls": []},
        ])
        agent = Agent(_settings(safe_mode=True), provider=fp)
        r = agent.ask("write a note")
        assert r.needs_approval and r.needs_approval[0]["name"] == "write_file"
        assert not Path(target).exists(), "must not run before approval"
        assert len(fp.calls) == 1
        r2 = agent.approve(True)
        assert Path(target).read_text() == "x"
        assert r2.text == "Saved." and r2.tool_events[0]["approved"] is True
        assert fp.calls[1]["history"][-1]["role"] == "tool"


def test_decline_sends_refusal_to_model():
    fp = FakeProvider([
        {"content": "", "tool_calls": [{"id": "k1", "name": "run_command", "arguments": {"command": "echo hi"}}]},
        {"content": "Okay, not running it.", "tool_calls": []},
    ])
    agent = Agent(_settings(safe_mode=True), provider=fp)
    agent.ask("run echo")
    r = agent.approve(False)
    assert "declined" in fp.calls[1]["history"][-1]["content"].lower()
    assert r.text == "Okay, not running it."


def test_safe_mode_off_runs_dangerous_directly():
    fp = FakeProvider([
        {"content": "", "tool_calls": [{"id": "k1", "name": "run_python", "arguments": {"code": "print(6*7)"}}]},
        {"content": "42", "tool_calls": []},
    ])
    agent = Agent(_settings(safe_mode=False), provider=fp)
    r = agent.ask("compute")
    assert r.needs_approval is None and "42" in r.tool_events[0]["result"]


def test_mixed_safe_and_dangerous_in_one_turn():
    fp = FakeProvider([
        {"content": "", "tool_calls": [
            {"id": "a", "name": "system_info", "arguments": {}},
            {"id": "b", "name": "run_command", "arguments": {"command": "whoami"}},
        ]},
        {"content": "final", "tool_calls": []},
    ])
    agent = Agent(_settings(safe_mode=True), provider=fp)
    r = agent.ask("do both")
    assert [e["tool"] for e in r.tool_events] == ["system_info"]
    assert [a["name"] for a in r.needs_approval] == ["run_command"]
    r2 = agent.approve(True)
    tool_msgs = [h for h in fp.calls[1]["history"] if h["role"] == "tool"]
    assert {m["tool_call_id"] for m in tool_msgs} == {"a", "b"}
    assert r2.text == "final"


def test_unknown_tool_and_step_limit():
    fp = FakeProvider([{"content": "", "tool_calls": [{"id": "z", "name": "teleport", "arguments": {}}]},
                       {"content": "sorry", "tool_calls": []}])
    agent = Agent(_settings(), provider=fp)
    r = agent.ask("go")
    assert "unknown tool" in fp.calls[1]["history"][-1]["content"]
    loop = FakeProvider([{"content": "", "tool_calls": [{"id": f"i{i}", "name": "system_info", "arguments": {}}]} for i in range(40)])
    r = Agent(_settings(), provider=loop).ask("loop")
    assert "too many steps" in r.text


def test_openai_message_conversion():
    hist = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "list_dir", "arguments": {"path": "~"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "list_dir", "content": "files"},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]
    msgs = OpenAICompatProvider._to_openai_messages("sys", hist)
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[2]["tool_calls"][0]["function"]["arguments"] == '{"path": "~"}'
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "files"}
    assert "tool_calls" not in msgs[4]

    a = AnthropicProvider._to_anthropic_messages(hist)
    assert a[1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "list_dir", "input": {"path": "~"}}
    assert a[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "files"}]}
    assert a[3]["content"] == [{"type": "text", "text": "done"}]


def test_settings_roundtrip_and_keys():
    s = _settings(provider="groq", model="llama-3.3-70b-versatile")
    s.update({"api_keys": {"groq": "gsk_secret"}, "unknown_key": 1})
    s2 = Settings(s.path)
    assert s2.get("provider") == "groq" and s2.api_key("groq") == "gsk_secret"
    assert "unknown_key" not in s2.data
    assert s2.public()["api_keys"]["groq"] == "set"
    assert s2.api_key("ollama") is None
    for pid, info in PROVIDERS.items():
        assert info["kind"] in ("openai", "anthropic") and "label" in info


def test_system_prompt_lists_tools():
    sp = system_prompt(_settings())
    assert "generate_video" in sp and "run_command" in sp and "APPROVAL_REQUIRED" in sp


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                failures += 1
                import traceback
                print("FAIL", name, "\n   ", e)
                traceback.print_exc()
    sys.exit(1 if failures else 0)
