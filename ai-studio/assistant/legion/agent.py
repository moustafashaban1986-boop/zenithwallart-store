"""The agent loop: LLM <-> tools, with approval for dangerous actions."""
from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from .config import PROVIDERS, Settings
from .providers import Provider, ProviderError, make_provider
from .tools import REGISTRY, load_all, run_tool, tool_specs

MAX_STEPS = 20


def system_prompt(settings: Settings) -> str:
    tools_by_cat: dict[str, list[str]] = {}
    for t in REGISTRY.values():
        tools_by_cat.setdefault(t.category, []).append(t.name)
    cats = "\n".join(f"- {c}: {', '.join(sorted(n))}" for c, n in sorted(tools_by_cat.items()))
    extra = settings.get("system_prompt_extra") or ""
    return f"""You are Legion, a personal AI assistant running locally on the user's Windows laptop
(Lenovo Legion 7, RTX 3080 16GB). You can control the computer through tools and you speak your answers out loud,
so keep replies short and natural unless the user asks for detail. Today is {datetime.now():%A %Y-%m-%d %H:%M}.
Platform: {platform.system()} {platform.release()}.

Rules:
- Use tools to actually do things instead of describing how the user could do them.
- Prefer specific tools (open_app, list_dir, generate_image ...) over run_command; use run_command for anything else.
- Tools marked DANGEROUS may require the user's approval; if a tool returns "APPROVAL_REQUIRED", tell the user
  briefly what you want to do and stop - the user will approve or decline.
- Never invent file contents or command output; report tool results truthfully, including errors.
- For images and videos, write a rich descriptive prompt in English, then call generate_image / generate_video.
- When you take a screenshot, describe what is relevant on screen, not every pixel.
- Answer in the language the user speaks to you (Arabic, English, ...).

Tool categories:
{cats}
{extra}""".strip()


@dataclass
class PendingApproval:
    assistant_turn: dict
    calls: list[dict]                       # all tool calls of this turn
    results: dict[str, str] = field(default_factory=dict)  # results already obtained (safe tools)
    created: float = field(default_factory=time.time)

    def describe(self) -> list[dict]:
        return [{"id": c["id"], "name": c["name"], "arguments": c.get("arguments") or {}}
                for c in self.calls if c["id"] not in self.results]


@dataclass
class TurnResult:
    text: str
    tool_events: list[dict]
    needs_approval: list[dict] | None = None
    error: str | None = None


class Agent:
    def __init__(self, settings: Settings | None = None, provider: Provider | None = None,
                 on_event: Callable[[dict], None] | None = None):
        self.settings = settings or Settings()
        load_all()
        self.provider = provider
        self.history: list[dict] = []
        self.pending: PendingApproval | None = None
        self.on_event = on_event or (lambda e: None)
        self.max_history = 60

    # -- provider ------------------------------------------------------------
    def get_provider(self) -> Provider:
        if self.provider is None:
            pid = self.settings.get("provider")
            self.provider = make_provider(pid, self.settings.get("model"), self.settings.api_key(pid))
        return self.provider

    def switch(self, provider_id: str, model: str) -> None:
        self.settings.update({"provider": provider_id, "model": model})
        self.provider = None

    def reset(self) -> None:
        self.history = []
        self.pending = None

    # -- main entry ----------------------------------------------------------
    def ask(self, user_text: str, approve_all: bool = False) -> TurnResult:
        self.pending = None
        self.history.append({"role": "user", "content": user_text})
        return self._loop(approve_all=approve_all)

    def approve(self, approved: bool = True) -> TurnResult:
        """Continue a turn that stopped for approval."""
        if not self.pending:
            return TurnResult(text="Nothing is waiting for approval.", tool_events=[])
        p, self.pending = self.pending, None
        events = []
        for call in p.calls:
            if call["id"] in p.results:
                continue
            if approved:
                out = run_tool(call["name"], call.get("arguments"))
            else:
                out = "User declined this action."
            p.results[call["id"]] = out
            events.append({"tool": call["name"], "arguments": call.get("arguments"), "result": out[:2000],
                           "approved": approved})
            self.on_event(events[-1])
        self._append_results(p)
        result = self._loop(approve_all=approved)
        result.tool_events = events + result.tool_events
        return result

    # -- internals -----------------------------------------------------------
    def _append_results(self, p: PendingApproval) -> None:
        for call in p.calls:
            self.history.append({"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                                 "content": p.results.get(call["id"], "")})

    def _trim(self) -> None:
        if len(self.history) > self.max_history:
            # keep the first user message context small: drop oldest complete exchanges
            cut = len(self.history) - self.max_history
            # never cut in the middle of an assistant->tool group
            while cut < len(self.history) and self.history[cut]["role"] == "tool":
                cut += 1
            self.history = self.history[cut:]

    def _loop(self, approve_all: bool) -> TurnResult:
        events: list[dict] = []
        try:
            provider = self.get_provider()
        except ProviderError as e:
            return TurnResult(text=str(e), tool_events=[], error=str(e))
        specs = tool_specs()
        system = system_prompt(self.settings)
        for _ in range(MAX_STEPS):
            self._trim()
            try:
                reply = provider.chat(system, self.history, specs)
            except ProviderError as e:
                return TurnResult(text=f"Brain error: {e}", tool_events=events, error=str(e))
            except Exception as e:  # pragma: no cover - unexpected provider failure
                return TurnResult(text=f"Brain error: {e.__class__.__name__}: {e}", tool_events=events, error=str(e))
            turn = {"role": "assistant", "content": reply.get("content") or "", "tool_calls": reply.get("tool_calls") or []}
            self.history.append(turn)
            calls = turn["tool_calls"]
            if not calls:
                return TurnResult(text=turn["content"].strip() or "(no reply)", tool_events=events)

            pending = PendingApproval(assistant_turn=turn, calls=calls)
            safe_mode = bool(self.settings.get("safe_mode", True)) and not approve_all
            for call in calls:
                t = REGISTRY.get(call["name"])
                if t is None:
                    pending.results[call["id"]] = f"Error: unknown tool {call['name']}"
                elif t.dangerous and safe_mode:
                    continue  # needs approval
                else:
                    out = run_tool(call["name"], call.get("arguments"))
                    pending.results[call["id"]] = out
                    events.append({"tool": call["name"], "arguments": call.get("arguments"), "result": out[:2000]})
                    self.on_event(events[-1])
            if len(pending.results) < len(calls):
                self.pending = pending
                asks = pending.describe()
                names = ", ".join(f"{a['name']}({json.dumps(a['arguments'], ensure_ascii=False)[:160]})" for a in asks)
                text = turn["content"].strip() or f"I need your approval to run: {names}"
                return TurnResult(text=text, tool_events=events, needs_approval=asks)
            self._append_results(pending)
        return TurnResult(text="I stopped after too many steps. Ask me to continue if needed.", tool_events=events)


def describe_provider(settings: Settings) -> dict[str, Any]:
    pid = settings.get("provider")
    info = PROVIDERS.get(pid, {})
    return {"provider": pid, "label": info.get("label"), "model": settings.get("model"),
            "offline": info.get("offline", False)}
