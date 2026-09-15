# AI Studio — free, unlimited, offline image & video generation, driven by Claude

Everything needed to turn a **Lenovo Legion 7 16ITHg6 (RTX 3080 Laptop, 16 GB VRAM, i9)** into a
local video/image generator that Claude can operate for you:

| Piece | What it does |
|---|---|
| `INSTALL.bat` / `install.ps1` | One-click installer: ComfyUI portable, ComfyUI Manager, ComfyUI-GGUF, VideoHelperSuite, Git if missing, model downloads, Claude hookup. Safe to re-run. |
| `download-models.ps1` / `Download-Models.bat` | Resumable downloads of the model packs listed in `models.json`. |
| `Start-ComfyUI.bat` | Launches ComfyUI with flags tuned for a 16 GB laptop GPU and the Manager enabled. |
| `claude-comfy/` | **MCP server** that gives Claude tools like `generate_image`, `generate_video`, `comfy_status`. Also a CLI. |
| `workflows/` | Ready-made ComfyUI workflows (drag-and-drop into the ComfyUI page). |
| `install-claude.ps1` | Registers the MCP server in Claude Desktop and Claude Code. |
| `tests/` | Validation of every workflow against the ComfyUI node definitions and an end-to-end MCP test. |

Nothing here calls a paid API. Once the models are downloaded it runs fully offline, as many
images and videos as you want, at the cost of electricity only.

---

## 1. Install (about 30–60 minutes, mostly downloading)

**Requirements:** Windows 10/11, NVIDIA driver up to date (GeForce Experience or nvidia.com),
~45 GB free on `C:` for the starter pack (more for extra packs), a stable connection.

1. Download this repository as a ZIP (GitHub → Code → Download ZIP) or `git clone` it.
2. Open the `ai-studio` folder.
3. **Right-click `INSTALL.bat` → Run as administrator.** Admin is only needed if it has to install Git or 7-Zip.
4. Wait. The script prints numbered steps. Each step is skipped if already done, so if anything
   fails (Wi-Fi drop, etc.) just run it again.

Options (run from a PowerShell window inside `ai-studio`):

```powershell
.\install.ps1                              # C:\ComfyUI, "starter" pack (FLUX images + Wan 2.2 5B video)
.\install.ps1 -Pack all                    # every pack (~85 GB)
.\install.ps1 -InstallDir D:\ComfyUI       # different drive
.\install.ps1 -Pack none -SkipClaude       # only ComfyUI + nodes; models and Claude later
```

### What you get after the installer

```
C:\ComfyUI\
  Start-ComfyUI.bat        <- double-click to start ComfyUI (keep the window open)
  Check-Setup.bat          <- verifies GPU, nodes and model files
  Download-Models.bat      <- fetch more packs later
  ComfyUI\models\...       <- the model files
  ComfyUI\output\claude\   <- every image / video Claude generates
  claude-comfy\            <- the MCP server Claude talks to
  python_embeded\          <- ComfyUI's own Python (also runs the MCP server, no extra install)
```

### Verify

1. Double-click `C:\ComfyUI\Start-ComfyUI.bat`. A console window opens, then the browser shows
   the ComfyUI page at `http://127.0.0.1:8188` with a **Manager** button in the top bar.
2. Double-click `Check-Setup.bat`. It should print your GPU, `GGUF OK | VideoHelperSuite OK`,
   and `[x]` next to the downloaded model files.
3. (Optional) In the ComfyUI page: Workflow → Open → pick `ai-studio\workflows\image_flux_schnell_gguf.json`
   → **Run**. An image appears in a few seconds.

---

## 2. Connect it to Claude

`install.ps1` already ran `install-claude.ps1`, which:

* adds a `comfyui` entry to `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop), and
* runs `claude mcp add --scope user comfyui ...` if the Claude Code CLI is installed.

**Fully quit Claude Desktop (right-click the tray icon → Quit) and start it again.** The tools
icon in the chat box should now list `comfyui` with tools such as `generate_image` and `generate_video`.

Then just talk to Claude:

> "Check comfy status."
> "Generate a 1024x1024 image of a minimalist abstract wall art print in warm terracotta tones, product photo style."
> "Make a 2-second video: slow camera push-in on that framed print hanging in a bright living room."
> "Animate C:\Users\me\Pictures\poster.png into a 3 second clip with gentle parallax, use the ltx model."
> "Use seed 1234 again but at 1280x704 with 81 frames."

Claude starts ComfyUI itself if it is not running (`start_comfyui`), waits for the job, and returns
the file path (and a preview for images). Files are saved under `C:\ComfyUI\ComfyUI\output\claude\`.

### Tools Claude gets

| Tool | Purpose |
|---|---|
| `comfy_status` | Is ComfyUI up? GPU/VRAM, queue, which presets have all model files. |
| `start_comfyui` | Launch `Start-ComfyUI.bat` and wait for the API. |
| `list_presets` | Presets, defaults, limits, required files. |
| `generate_image` | FLUX.1 schnell text-to-image (4 steps, ~10–20 s at 1024²). Returns paths + preview. |
| `generate_video` | Text-to-video or image-to-video (`image_path=`) with `wan22-5b`, `ltx` or `wan21-14b`. Returns MP4 path. |
| `job_status` / `wait_for_job` | Poll long jobs (`wait=false` mode). |
| `cancel_current_job`, `free_memory` | Interrupt; unload models from VRAM. |
| `list_outputs`, `view_image` | Browse results; show an image to Claude. |

Manual config, if you ever need it (`claude_desktop_config.json` or a project `.mcp.json`):

```json
{
  "mcpServers": {
    "comfyui": {
      "command": "C:\\ComfyUI\\python_embeded\\python.exe",
      "args": ["C:\\ComfyUI\\claude-comfy\\server.py"],
      "env": { "COMFY_DIR": "C:\\ComfyUI", "COMFY_URL": "http://127.0.0.1:8188" }
    }
  }
}
```

Claude Code CLI: `claude mcp add --scope user comfyui -- C:\ComfyUI\python_embeded\python.exe C:\ComfyUI\claude-comfy\server.py`

---

## 3. Models and what fits in 16 GB

| Pack | Files | Size | Use |
|---|---|---|---|
| `starter` (default) | FLUX.1 schnell Q4 GGUF + T5/CLIP-L/VAE, **Wan 2.2 5B** + VAE + UMT5 | ~30 GB | Images + the best video model for this GPU |
| `ltx` | LTX-Video 2B 0.9.5 (+ shared T5) | ~6 GB extra | Very fast previews/clips |
| `wan21-14b` | Wan 2.1 14B T2V + I2V-480p **Q4_K_M GGUF**, VAE, CLIP-vision | ~29 GB | Highest fidelity, slowest |
| `flux-fp8` | Single-file FLUX schnell checkpoint | ~17 GB | Fallback if the GGUF download fails |

`models.json` lists every file, its target folder and download URL. The Wan/LTX/T5/VAE links are
the same ones ComfyUI's official templates use. The GGUF files come from `city96` on Hugging Face.
If Hugging Face renames a file, open the `/tree/main` link the downloader prints, download the
matching file manually, and drop it in `ComfyUI\models\<folder>\`.

**Recommended first video test** (matches the guide you were following): `wan22-5b`, 1280×704
(720p, rounded to the model's 32-px grid), **49 frames ≈ 2 s at 24 fps**. That takes a few
minutes on the 3080 Laptop. Once it works, go to 81 or 121 frames.

Preset defaults (Claude uses these unless you ask otherwise):

| Preset | Size | Frames / fps | Steps | Notes |
|---|---|---|---|---|
| `wan22-5b` | 1280×704 | 49 @ 24 (max 121) | 20, cfg 5 | Text→video and image→video. Frames rounded to 4n+1. |
| `ltx` | 768×512 | 97 @ 25 | 30, cfg 3 | Seconds per clip. Frames rounded to 8n+1. |
| `wan21-14b` | 832×480 | 33 @ 16 (max 81) | 20, cfg 6 | GGUF Q4; 720p works but is slow. |
| `flux-schnell` | 1024×1024 | – | 4, cfg 1 | Up to ~1536×1536. |

---

## 4. Using it without Claude

The ComfyUI page works as usual (drag `workflows\*.json` onto it, or use its built-in
Templates menu). The same code Claude uses is also a CLI:

```bat
cd C:\ComfyUI
python_embeded\python.exe -s claude-comfy\cli.py status
python_embeded\python.exe -s claude-comfy\cli.py image "framed abstract print, warm tones, product photo"
python_embeded\python.exe -s claude-comfy\cli.py video "slow push-in on a framed painting, sunlit room" --frames 49
python_embeded\python.exe -s claude-comfy\cli.py video "the painting comes alive" --image C:\art\poster.png --model ltx
```

---

## 5. Manual install (if the script cannot run)

These are the same steps the installer automates:

1. Download `ComfyUI_windows_portable_nvidia.7z` from the ComfyUI GitHub *Releases* page, extract
   with 7-Zip, move the contents of `ComfyUI_windows_portable` to `C:\ComfyUI`, run `run_nvidia_gpu.bat` once.
2. Install Git for Windows. Then in `C:\ComfyUI`:
   `python_embeded\python.exe -s -m pip install -r ComfyUI\manager_requirements.txt`
   and start ComfyUI with `--enable-manager` (this is what `Start-ComfyUI.bat` does).
   Older builds instead: `git clone https://github.com/ltdrdata/ComfyUI-Manager.git ComfyUI\custom_nodes\comfyui-manager`.
3. In `C:\ComfyUI\ComfyUI\custom_nodes`:
   `git clone https://github.com/city96/ComfyUI-GGUF.git` and
   `git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git`, then
   `python_embeded\python.exe -s -m pip install -r <each>\requirements.txt`.
   (Or use Manager → Install Custom Nodes → search *ComfyUI-GGUF* and *VideoHelperSuite*.)
4. Download the files in `models.json` into `ComfyUI\models\<folder>\`.
5. Copy `claude-comfy\` (plus `models.json` and `workflows\`) to `C:\ComfyUI\claude-comfy`, run
   `python_embeded\python.exe -s -m pip install -r claude-comfy\requirements.txt`, then `install-claude.ps1`.

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| **`CUDA out of memory`** during video | Fewer frames (33 → 49 → 81), smaller size, or tell Claude to call `free_memory` first. As a last resort start with `Start-ComfyUI.bat --lowvram`. In NVIDIA Control Panel → Manage 3D settings → *CUDA – Sysmem Fallback Policy* → **Prefer Sysmem Fallback** avoids hard crashes (slower instead of failing). |
| `Value not in list: unet_name` / "model file missing" | The file is not in `ComfyUI\models\<folder>`. Run `Download-Models.bat` for the right pack and **restart ComfyUI** so it re-scans. |
| Claude says the `comfyui` server is not available | Fully quit Claude Desktop from the tray and reopen. Check `%APPDATA%\Claude\claude_desktop_config.json` contains the `comfyui` entry, and that `C:\ComfyUI\claude-comfy\server.py` exists. Claude Desktop → Settings → Developer shows server logs. |
| Tools exist but every call says "ComfyUI is not running" | Ask Claude to run `start_comfyui`, or double-click `Start-ComfyUI.bat`. Check the browser opens `http://127.0.0.1:8188`. |
| No **Manager** button | The Manager package failed to install. Run `python_embeded\python.exe -s -m pip install -r ComfyUI\manager_requirements.txt` in `C:\ComfyUI`, or install it into `custom_nodes` (step 2 above). |
| `Video Combine` node missing / `VHS_VideoCombine` error | VideoHelperSuite is not installed: Manager → Install Custom Nodes → *ComfyUI-VideoHelperSuite*, restart. |
| Extraction of the 7z fails | Install 7-Zip from 7-zip.org and re-run the installer. |
| Very slow first run | Models load from disk into VRAM (10–20 GB). Second run is much faster. Keep the models on the NVMe drive. |
| Laptop throttles / fans | Set Lenovo Vantage to Performance mode and plug in the 230 W adapter. Video generation is a sustained 100 % GPU load. |

Updating ComfyUI later: run `C:\ComfyUI\update\update_comfyui.bat`. Re-run `INSTALL.bat` any time to
refresh the custom nodes and the bridge.

---

## 7. Developing / testing the bridge

```bash
pip install "mcp>=1.2" httpx pillow
python tests/test_workflows.py          # validates every workflow against the ComfyUI node schemas
python tests/test_mcp_end_to_end.py     # runs the real MCP server against a mock ComfyUI
python claude-comfy/export_workflows.py # regenerates workflows/*.json after editing workflows.py
```

The server works with both the 1.x (`FastMCP`) and 2.x (`MCPServer`) Python MCP SDKs.
Environment variables: `COMFY_URL` (default `http://127.0.0.1:8188`), `COMFY_DIR`, `COMFY_OUTPUT_DIR`.
