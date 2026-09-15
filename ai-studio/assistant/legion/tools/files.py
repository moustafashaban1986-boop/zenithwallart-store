"""File system tools. Deletes go to the recycle bin when send2trash is available."""
from __future__ import annotations

import fnmatch
import os
import shutil
from pathlib import Path

from . import tool

MAX_READ = 60_000


def _p(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


@tool(category="files")
def list_dir(path: str = "~", pattern: str = "*", show_hidden: bool = False) -> str:
    """List files and folders in a directory.
    path: directory path (default: home folder)
    pattern: glob filter such as *.pdf
    show_hidden: include dot-files
    """
    d = _p(path)
    if not d.is_dir():
        return f"Error: {d} is not a directory"
    rows = []
    for entry in sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        if not show_hidden and entry.name.startswith("."):
            continue
        if not fnmatch.fnmatch(entry.name, pattern):
            continue
        try:
            size = "" if entry.is_dir() else f"{entry.stat().st_size / 1024:,.0f} KB"
        except OSError:
            size = "?"
        rows.append(f"{'[DIR] ' if entry.is_dir() else '      '}{entry.name:<50} {size}")
    return f"{d}\n" + ("\n".join(rows[:400]) if rows else "(empty)") + (f"\n... {len(rows) - 400} more" if len(rows) > 400 else "")


@tool(category="files")
def read_file(path: str, max_chars: int = 20000) -> str:
    """Read a text file (txt, md, py, json, csv, html ...). PDFs and DOCX are converted to text when possible.
    path: file path
    max_chars: truncate after this many characters
    """
    f = _p(path)
    if not f.is_file():
        return f"Error: {f} not found"
    suffix = f.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(f)).pages)
        elif suffix == ".docx":
            import docx
            text = "\n".join(p.text for p in docx.Document(str(f)).paragraphs)
        else:
            text = f.read_text(encoding="utf-8", errors="replace")
    except ImportError as e:
        return f"Error: missing library to read {suffix}: {e}"
    except Exception as e:
        return f"Error reading {f}: {e}"
    limit = min(int(max_chars), MAX_READ)
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated, {len(text)} chars total]"


@tool(dangerous=True, category="files")
def write_file(path: str, content: str, append: bool = False) -> str:
    """Create or overwrite a text file (parent folders are created).
    path: file path
    content: text to write
    append: add to the end instead of overwriting
    """
    f = _p(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a" if append else "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"Wrote {len(content)} characters to {f}"


@tool(category="files")
def search_files(query: str, root: str = "~", max_results: int = 50, content: bool = False) -> str:
    """Find files by name (glob or substring), optionally searching inside text files.
    query: name pattern like *.xlsx or 'invoice', or text to search for when content=true
    root: folder to search under
    max_results: stop after this many hits
    content: search inside text files instead of file names
    """
    base = _p(root)
    hits = []
    q = query.lower()
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "$", "node_modules", "__pycache__", "AppData"))]
        for name in filenames:
            full = Path(dirpath) / name
            try:
                if content:
                    if full.suffix.lower() in (".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".ps1", ".bat", ".log", ".yaml", ".yml", ".xml"):
                        if q in full.read_text(encoding="utf-8", errors="ignore").lower():
                            hits.append(str(full))
                elif fnmatch.fnmatch(name.lower(), q) or q in name.lower():
                    hits.append(str(full))
            except Exception:
                continue
            if len(hits) >= max_results:
                return "\n".join(hits) + "\n... (limit reached)"
    return "\n".join(hits) if hits else "no matches"


@tool(dangerous=True, category="files")
def move_or_copy(src: str, dst: str, copy: bool = False) -> str:
    """Move (or copy) a file or folder.
    src: source path
    dst: destination path or folder
    copy: copy instead of move
    """
    s, d = _p(src), _p(dst)
    if not s.exists():
        return f"Error: {s} not found"
    if d.is_dir():
        d = d / s.name
    if copy:
        shutil.copytree(s, d) if s.is_dir() else shutil.copy2(s, d)
        return f"Copied {s} -> {d}"
    shutil.move(str(s), str(d))
    return f"Moved {s} -> {d}"


@tool(dangerous=True, category="files")
def delete_path(path: str) -> str:
    """Delete a file or folder (to the Recycle Bin when possible).
    path: what to delete
    """
    p = _p(path)
    if not p.exists():
        return f"Error: {p} not found"
    if len(p.parts) <= 2:
        return f"Refusing to delete a drive root or top-level folder: {p}"
    try:
        from send2trash import send2trash
        send2trash(str(p))
        return f"Sent to Recycle Bin: {p}"
    except ImportError:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return f"Deleted permanently (send2trash not installed): {p}"


@tool(category="files")
def make_dir(path: str) -> str:
    """Create a folder (and parents).
    path: folder path
    """
    d = _p(path)
    d.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {d}"


@tool(category="files")
def file_info(path: str) -> dict:
    """Size, dates and type of a file or folder.
    path: the path to inspect
    """
    p = _p(path)
    if not p.exists():
        return {"error": f"{p} not found"}
    st = p.stat()
    import datetime as dt
    return {
        "path": str(p), "is_dir": p.is_dir(), "size_bytes": st.st_size,
        "modified": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "created": dt.datetime.fromtimestamp(st.st_ctime).isoformat(timespec="seconds"),
        "suffix": p.suffix,
    }
