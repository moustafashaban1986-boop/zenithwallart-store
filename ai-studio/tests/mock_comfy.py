"""A tiny fake ComfyUI HTTP server used by the end-to-end test.

It implements just enough of the real API (/system_stats, /queue, /models/{folder},
/object_info/{cls}, /prompt, /history/{id}, /upload/image, /interrupt, /free) to
exercise the MCP server without a GPU.  Workflows are validated with the same
node schema the unit tests use, and fake output files are written to OUTPUT_DIR.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from node_schema import NODES, validate  # noqa: E402

OUTPUT_DIR = Path(os.environ["MOCK_OUTPUT_DIR"])
INPUT_DIR = Path(os.environ["MOCK_INPUT_DIR"])
MODELS = json.loads(os.environ.get("MOCK_MODELS", "{}"))  # folder -> [files]
FAIL_NEXT = {"oom": False}

HISTORY: dict[str, dict] = {}
PNG_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGM8URHAAANMDEgANwcAT5wBmBS18PkAAAAASUVORK5CYII=")  # valid 4x4 RGB PNG


def _outputs_for(workflow: dict) -> dict:
    outputs = {}
    for nid, node in workflow.items():
        prefix = node["inputs"].get("filename_prefix", "ComfyUI")
        sub, _, base = prefix.rpartition("/")
        folder = OUTPUT_DIR / sub
        folder.mkdir(parents=True, exist_ok=True)
        if node["class_type"] == "SaveImage":
            fn = f"{base}_00001_.png"
            (folder / fn).write_bytes(PNG_1x1)
            outputs[nid] = {"images": [{"filename": fn, "subfolder": sub, "type": "output"}]}
        elif node["class_type"] == "VHS_VideoCombine":
            fn = f"{base}_00001.mp4"
            (folder / fn).write_bytes(b"\x00\x00\x00\x18ftypmp42")
            outputs[nid] = {"gifs": [{"filename": fn, "subfolder": sub, "type": "output",
                                      "format": node["inputs"]["format"], "frame_rate": node["inputs"]["frame_rate"]}]}
    return outputs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/system_stats":
            return self._json({"system": {"comfyui_version": "mock-0.35"},
                               "devices": [{"name": "NVIDIA GeForce RTX 3080 Laptop GPU (mock)",
                                            "vram_total": 16 * 2**30, "vram_free": 15 * 2**30}]})
        if path == "/queue":
            return self._json({"queue_running": [], "queue_pending": []})
        m = re.match(r"^/models/([a-z_]+)$", path)
        if m:
            return self._json(MODELS.get(m.group(1), []))
        m = re.match(r"^/object_info/([A-Za-z0-9_]+)$", path)
        if m:
            cls = m.group(1)
            if cls in NODES:
                return self._json({cls: {"input": {}, "name": cls}})
            return self._json({}, 404)
        m = re.match(r"^/history/([0-9a-f-]+)$", path)
        if m:
            pid = m.group(1)
            return self._json({pid: HISTORY[pid]} if pid in HISTORY else {})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if path == "/prompt":
            data = json.loads(raw)
            wf = data["prompt"]
            problems = validate(wf)
            node_errors = {}
            # Simulate ComfyUI's model-file check.
            have = {f for files in MODELS.values() for f in files}
            for nid, node in wf.items():
                for key in ("unet_name", "ckpt_name", "clip_name", "clip_name1", "clip_name2", "vae_name"):
                    val = node["inputs"].get(key)
                    if val and val not in have:
                        node_errors[nid] = {"class_type": node["class_type"], "errors": [
                            {"message": f"Value not in list: {key}", "details": f"'{val}' not in {sorted(have)}"}]}
            if problems or node_errors:
                return self._json({"error": {"type": "prompt_outputs_failed_validation",
                                             "message": "Prompt outputs failed validation",
                                             "details": "; ".join(problems)},
                                   "node_errors": node_errors}, 400)
            pid = str(uuid.uuid4())
            if FAIL_NEXT["oom"]:
                FAIL_NEXT["oom"] = False
                HISTORY[pid] = {"prompt": [0, pid, wf, {}, []], "outputs": {},
                                "status": {"status_str": "error", "completed": False, "messages": [
                                    ["execution_error", {"node_type": "KSampler",
                                                         "exception_message": "CUDA out of memory. Tried to allocate 2.00 GiB"}]]}}
            else:
                HISTORY[pid] = {"prompt": [0, pid, wf, {}, []], "outputs": _outputs_for(wf),
                                "status": {"status_str": "success", "completed": True, "messages": []}}
            return self._json({"prompt_id": pid, "number": 0, "node_errors": {}})
        if path == "/upload/image":
            ctype = self.headers.get("Content-Type", "")
            m = re.search(r'boundary="?([^";]+)"?', ctype)
            boundary = m.group(1).encode()
            fields = {}
            for part in raw.split(b"--" + boundary):
                if b"Content-Disposition" not in part:
                    continue
                head, _, body = part.partition(b"\r\n\r\n")
                body = body.rstrip(b"\r\n--")
                name = re.search(rb'name="([^"]+)"', head).group(1).decode()
                fname = re.search(rb'filename="([^"]+)"', head)
                fields[name] = (fname.group(1).decode(), body) if fname else body.decode()
            fname, body = fields["image"]
            sub = fields.get("subfolder", "")
            target = INPUT_DIR / sub
            target.mkdir(parents=True, exist_ok=True)
            (target / fname).write_bytes(body)
            return self._json({"name": fname, "subfolder": sub, "type": "input"})
        if path in ("/interrupt", "/free"):
            if path == "/free" and b"oom-test" in raw:
                FAIL_NEXT["oom"] = True
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/mock/fail_next_oom":
            FAIL_NEXT["oom"] = True
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def main():
    port = int(os.environ.get("MOCK_PORT", "8189"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock comfy on {port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
