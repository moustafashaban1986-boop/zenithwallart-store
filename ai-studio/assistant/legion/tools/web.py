"""Web tools (only work when online): fetch a page as text, quick web search (DuckDuckGo)."""
from __future__ import annotations

import html
import re

import httpx

from . import tool

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Legion/0.1"}


def _strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


@tool(category="web")
def fetch_url(url: str, max_chars: int = 15000) -> str:
    """Download a web page and return its readable text (requires internet).
    url: http(s) address
    max_chars: truncate after this many characters
    """
    try:
        r = httpx.get(url, headers=UA, follow_redirects=True, timeout=30.0)
        r.raise_for_status()
    except Exception as e:
        return f"Error fetching {url}: {e}"
    ctype = r.headers.get("content-type", "")
    text = _strip_html(r.text) if "html" in ctype else r.text
    return text[:max_chars] + ("\n... [truncated]" if len(text) > max_chars else "")


@tool(category="web")
def web_search(query: str, max_results: int = 6) -> str:
    """Search the web (DuckDuckGo) and return titles, links and snippets (requires internet).
    query: what to search for
    max_results: number of results
    """
    try:
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=UA, timeout=30.0,
                       follow_redirects=True)
        r.raise_for_status()
    except Exception as e:
        return f"Error: search failed ({e}). Are you online?"
    results = re.findall(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?'
                         r'<a class="result__snippet"[^>]*>(.*?)</a>', r.text, flags=re.S)
    out = []
    for href, title, snippet in results[:max_results]:
        out.append(f"- {_strip_html(title)}\n  {html.unescape(href)}\n  {_strip_html(snippet)}")
    return "\n".join(out) if out else "no results"
