"""LLM providers behind one tiny interface.

history items (provider-neutral):
    {"role": "user", "content": str}
    {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments": dict}]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}

Provider.chat(system, history, tools) -> {"content": str, "tool_calls": [...]}
tools are JSON-schema dicts: {"name", "description", "parameters": {...}}
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .config import PROVIDERS


class ProviderError(RuntimeError):
    pass


class Provider:
    name = "base"

    def chat(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        return []

    def is_available(self) -> tuple[bool, str]:
        return True, "ok"


# ---------------------------------------------------------------------------
class OpenAICompatProvider(Provider):
    """Ollama, LM Studio, OpenRouter, Groq, Moonshot (Kimi), Gemini, DeepSeek ..."""

    def __init__(self, provider_id: str, model: str, api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 300.0):
        info = PROVIDERS.get(provider_id, {})
        self.name = provider_id
        self.model = model
        self.base_url = (base_url or info.get("base_url") or "").rstrip("/")
        self.api_key = api_key or "ollama"
        self.offline = bool(info.get("offline"))
        self._http = httpx.Client(timeout=timeout, headers=self._headers())

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.name == "openrouter":
            h["HTTP-Referer"] = "https://github.com/zenithwallart/ai-studio"
            h["X-Title"] = "Legion local assistant"
        return h

    def is_available(self) -> tuple[bool, str]:
        try:
            r = self._http.get(f"{self.base_url}/models", timeout=5.0)
            if r.status_code == 401:
                return False, "API key missing or invalid"
            return r.status_code < 500, f"HTTP {r.status_code}"
        except Exception as e:  # server down / offline
            if self.name == "ollama":
                return False, "Ollama is not running (start it from the Start menu or run 'ollama serve')"
            return False, f"unreachable: {e.__class__.__name__}"

    def list_models(self) -> list[str]:
        try:
            r = self._http.get(f"{self.base_url}/models", timeout=10.0)
            r.raise_for_status()
            ids = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
            if self.name == "openrouter":
                ids = [i for i in ids if i.endswith(":free")]
            return sorted(ids)
        except Exception:
            return []

    @staticmethod
    def _to_openai_messages(system: str, history: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}] if system else []
        for m in history:
            if m["role"] == "assistant":
                msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{
                        "id": tc["id"], "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})},
                    } for tc in m["tool_calls"]]
                out.append(msg)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": str(m.get("content", ""))})
            else:
                out.append({"role": "user", "content": m.get("content", "")})
        return out

    def chat(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": self._to_openai_messages(system, history)}
        if tools:
            body["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
        try:
            r = self._http.post(f"{self.base_url}/chat/completions", json=body)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name}: request failed ({e.__class__.__name__}). Is the server running / are you online?")
        if r.status_code != 200:
            detail = r.text[:400]
            if r.status_code == 404 and self.name == "ollama":
                detail = f"model '{self.model}' is not pulled. Run:  ollama pull {self.model}"
            raise ProviderError(f"{self.name} HTTP {r.status_code}: {detail}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        # some reasoning models put the answer in reasoning_content when content is empty
        if not content and msg.get("reasoning_content") and not msg.get("tool_calls"):
            content = msg["reasoning_content"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args) if args.strip() else {}
                except json.JSONDecodeError:
                    args = {"_raw": args}
            calls.append({"id": tc.get("id") or f"call_{len(calls)}", "name": fn.get("name", ""), "arguments": args})
        return {"content": content, "tool_calls": calls}


# ---------------------------------------------------------------------------
class AnthropicProvider(Provider):
    """Claude through the official SDK (online)."""

    def __init__(self, model: str = "claude-opus-5", api_key: str | None = None):
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError("pip install anthropic") from e
        self.name = "anthropic"
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def is_available(self) -> tuple[bool, str]:
        try:
            self.client.models.retrieve(self.model)
            return True, "ok"
        except Exception as e:
            return False, f"{e.__class__.__name__}: {str(e)[:120]}"

    def list_models(self) -> list[str]:
        try:
            return sorted(m.id for m in self.client.models.list())
        except Exception:
            return list(PROVIDERS["anthropic"]["models"])

    @staticmethod
    def _to_anthropic_messages(history: list[dict]) -> list[dict]:
        out: list[dict] = []
        pending_results: list[dict] = []

        def flush():
            nonlocal pending_results
            if pending_results:
                out.append({"role": "user", "content": pending_results})
                pending_results = []

        for m in history:
            if m["role"] == "tool":
                pending_results.append({"type": "tool_result", "tool_use_id": m["tool_call_id"],
                                        "content": str(m.get("content", ""))})
                continue
            flush()
            if m["role"] == "assistant":
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m.get("tool_calls") or []:
                    blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc.get("arguments") or {}})
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(no output)"}]})
            else:
                out.append({"role": "user", "content": m.get("content", "")})
        flush()
        return out

    def chat(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        import anthropic
        kwargs: dict[str, Any] = dict(
            model=self.model, max_tokens=16000,
            messages=self._to_anthropic_messages(history),
        )
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                               for t in tools]
        try:
            resp = self.client.messages.create(**kwargs)
        except anthropic.AuthenticationError as e:
            raise ProviderError("Claude: invalid or missing ANTHROPIC_API_KEY") from e
        except anthropic.RateLimitError as e:
            raise ProviderError("Claude: rate limited, try again in a moment") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Claude: no connection (offline?)") from e
        if resp.stop_reason == "refusal":
            return {"content": "Claude declined this request.", "tool_calls": []}
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [{"id": b.id, "name": b.name, "arguments": dict(b.input or {})} for b in resp.content if b.type == "tool_use"]
        return {"content": text, "tool_calls": calls}


# ---------------------------------------------------------------------------
def make_provider(provider_id: str, model: str, api_key: str | None = None) -> Provider:
    info = PROVIDERS.get(provider_id)
    if not info:
        raise ProviderError(f"Unknown provider '{provider_id}'. Options: {', '.join(PROVIDERS)}")
    if info.get("key_env") and not api_key:
        raise ProviderError(f"{info['label']} needs an API key. Set {info['key_env']} or add it in Settings.")
    if info["kind"] == "anthropic":
        return AnthropicProvider(model=model or info["default_model"], api_key=api_key)
    return OpenAICompatProvider(provider_id, model or info["default_model"], api_key=api_key)


def ollama_installed_models() -> list[str]:
    """Names of models already pulled into Ollama (empty if Ollama is down)."""
    try:
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json().get("models", []))
    except Exception:
        return []
