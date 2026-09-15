"""Tool registry shared by the agent (function calling) and the MCP server."""
from __future__ import annotations

import inspect
import json
import traceback
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean", list: "array", dict: "object"}


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict
    dangerous: bool = False
    category: str = "general"
    required: list[str] = field(default_factory=list)


REGISTRY: dict[str, Tool] = {}


def _resolve_hints(fn: Callable) -> dict:
    try:
        return typing.get_type_hints(fn)
    except Exception:
        return {}


def _json_type(ann) -> str:
    """Map a Python annotation (possibly Optional / X | None / list[str]) to a JSON schema type."""
    if isinstance(ann, str):  # unresolved forward ref
        base = ann.replace("Optional[", "").replace("]", "").split("|")[0].strip()
        return {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array",
                "dict": "object"}.get(base.split("[")[0], "string")
    origin = typing.get_origin(ann)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return _json_type(args[0]) if args else "string"
    if origin in (list, tuple, set):
        return "array"
    if origin is dict:
        return "object"
    return _PY_TO_JSON.get(ann, "string")


def _schema_from_signature(fn: Callable) -> tuple[dict, list[str]]:
    sig = inspect.signature(fn)
    hints = _resolve_hints(fn)
    props, required = {}, []
    doc = inspect.getdoc(fn) or ""
    # "param: description" lines in the docstring become parameter descriptions
    param_docs = {}
    for line in doc.splitlines():
        line = line.strip()
        if ":" in line and not line.endswith(":"):
            k, _, v = line.partition(":")
            if k.strip().isidentifier():
                param_docs[k.strip()] = v.strip()
    for name, p in sig.parameters.items():
        if name.startswith("_"):
            continue
        ann = hints.get(name, p.annotation if p.annotation is not inspect._empty else str)
        jtype = _json_type(ann)
        schema: dict[str, Any] = {"type": jtype}
        if jtype == "array":
            schema["items"] = {"type": "string"}
        if name in param_docs:
            schema["description"] = param_docs[name]
        if p.default is inspect._empty:
            required.append(name)
        elif p.default is not None:
            schema["default"] = p.default
        props[name] = schema
    return {"type": "object", "properties": props, "required": required}, required


def tool(name: str | None = None, description: str | None = None, dangerous: bool = False, category: str = "general"):
    """Register a plain function as a tool. Parameter schema comes from type hints,
    descriptions from 'param: text' lines in the docstring."""
    def deco(fn: Callable):
        tname = name or fn.__name__
        desc = description or (inspect.getdoc(fn) or "").split("\n\n")[0].split("\n")[0]
        params, required = _schema_from_signature(fn)
        REGISTRY[tname] = Tool(tname, desc, fn, params, dangerous, category, required)
        return fn
    return deco


def tool_specs(names: list[str] | None = None) -> list[dict]:
    """JSON-schema tool list for the LLM."""
    out = []
    for t in REGISTRY.values():
        if names and t.name not in names:
            continue
        d = t.description + ("  [DANGEROUS: needs user approval]" if t.dangerous else "")
        out.append({"name": t.name, "description": d, "parameters": t.parameters})
    return out


def run_tool(name: str, arguments: dict | None) -> str:
    """Execute a tool and always return a string (errors included)."""
    t = REGISTRY.get(name)
    if not t:
        return f"Error: unknown tool '{name}'. Available: {', '.join(sorted(REGISTRY))}"
    args = dict(arguments or {})
    args.pop("_raw", None)
    try:
        sig = inspect.signature(t.fn)
        accepted = {k: v for k, v in args.items() if k in sig.parameters}
        missing = [r for r in t.required if r not in accepted]
        if missing:
            return f"Error: missing required argument(s) {missing} for {name}"
        result = t.fn(**accepted)
        if isinstance(result, (dict, list)):
            return json.dumps(result, ensure_ascii=False, default=str)
        return "" if result is None else str(result)
    except Exception as e:  # never crash the agent loop
        return f"Error in {name}: {e.__class__.__name__}: {e}\n{traceback.format_exc(limit=2)}"


def load_all():
    """Import every tool module (idempotent)."""
    from . import files, system, desktop, web, media  # noqa: F401
    return REGISTRY
