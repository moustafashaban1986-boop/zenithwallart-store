# Legion — your local AI that runs this PC (voice in, voice out, offline-capable)

Legion is a personal assistant that lives on the Lenovo Legion 7 and can **do things**, not just chat:

| Part | What it uses (all free / open source) | Offline? |
|---|---|---|
| **Brain** | Ollama with local models (Qwen 3, Llama 3.1, Gemma 3, DeepSeek-R1 …). Optional online brains from the same dropdown: **Claude**, **Kimi K2** (Moonshot / Groq / OpenRouter), Groq, Google Gemini, DeepSeek, OpenRouter free models | Ollama: yes |
| **Ears** | faster-whisper (Whisper) speech-to-text, auto-detects language (Arabic, English, …) | yes |
| **Voice** | Kokoro TTS with 13 voices, Windows built-in voices (incl. Arabic if installed), **voice cloning** with Chatterbox from a short sample | yes |
| **Hands** | Run commands, open apps, read/write/search/move files, screenshots, mouse & keyboard, windows, clipboard, volume, lock/sleep/shutdown, web search + fetch (online), **generate images and videos** through the ComfyUI setup from `ai-studio` | yes |
| **Interface** | Local web page (`http://127.0.0.1:7860`) with chat, a microphone button, hands-free mode, spoken replies and dropdowns for Brain / Model / Voice / Image model / Video model; a terminal voice loop; a CLI | yes |
| **Claude link** | Legion registers itself as an MCP tool server in Claude Desktop and Claude Code, so Claude can also use all of Legion's hands on this PC | Claude itself needs internet |

Honest note about **Kimi**: Kimi K2 is a 1-trillion-parameter model. It cannot run on a laptop, so it appears in the dropdown as an online option (Moonshot API, or free through Groq / OpenRouter). Everything marked 🖥️ in the dropdown runs on your GPU with no internet.

---

## 1. Install

Prerequisite: run `ai-studio\INSTALL.bat` first (it installs ComfyUI and its Python, which Legion reuses so there is no second multi-gigabyte PyTorch download).

Then **right-click `INSTALL-ASSISTANT.bat` → Run as administrator.** It will:

1. Install **Ollama** (winget) and pull `qwen3:8b` (about 5 GB, fits easily in 16 GB VRAM, good at tool calling).
2. Copy Legion to `C:\ComfyUI\legion` and install its Python packages (core + voice).
3. Register the `legion` MCP server in Claude Desktop (and Claude Code if installed).

Options: `INSTALL-ASSISTANT.bat -Model llama3.1:8b`, `-SkipVoice`, `-SkipOllama`, `-ComfyDir D:\ComfyUI`.

## 2. Start

| Double-click | You get |
|---|---|
| `C:\ComfyUI\legion\Start-Assistant.bat` | The web UI in your browser. Type, or click 🎤 (or press Space) and talk. Replies are spoken. Turn on **Hands-free** to keep listening. |
| `C:\ComfyUI\legion\Start-Assistant-Voice.bat` | Terminal voice loop with no browser. Say "stop" to quit. Add `--ptt` for push-to-talk. |
| `C:\ComfyUI\legion\legion.cmd doctor` | Checks brain, ears, voice, tools and ComfyUI. (`legion.cmd` wraps `python_embeded\python.exe -s legion\run_legion.py`, which is needed because the embedded Python ignores `-m legion`.) |

Things to say:

* "Open Notepad and write a shopping list for a barbecue."
* "Take a screenshot and tell me what's on my screen."
* "Find all PDF files in my Downloads bigger than 10 MB."
* "Generate an image of a minimalist poster with a golden sunset." (FLUX, ~15 s)
* "Make a 2-second video of ocean waves at sunset." (Wan 2.2, a few minutes)
* "Animate C:\art\poster.png into a clip with slow zoom."
* "Clone my voice from C:\samples\me.wav and call it me." then pick `clone:me` in the Voice dropdown.
* "Set the volume to 30 percent." / "Lock the PC." / "Search the web for today's weather in Cairo."

## 3. Safety

`Safe mode` is **on by default** (switch in the header). With it on, tools that change the system (run commands, write/delete/move files, mouse/keyboard, kill process, power) stop and ask; you click **Approve** or say "yes". Switch it off for fully autonomous operation. Deletes go to the Recycle Bin. Slamming the mouse into the top-left corner aborts any mouse/keyboard automation instantly.

For Claude Desktop the same rule applies: dangerous tools are blocked while Legion's safe mode is on. To let Claude act freely, turn safe mode off in the Legion web UI, or set `LEGION_MCP_ALLOW_DANGEROUS=1` in the `legion` entry of `claude_desktop_config.json`.

## 4. Brains, models and keys

* **Ollama (offline)** — the Model dropdown shows what is installed plus suggestions; choosing a suggestion downloads it. Good picks for 16 GB: `qwen3:8b` (default), `llama3.1:8b`, `gemma3:12b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`, `phi4:14b`.
* **Online** — click **API keys** in the header and paste keys. Free keys: [console.groq.com](https://console.groq.com) (also serves Kimi K2), [openrouter.ai](https://openrouter.ai) (`:free` models incl. Kimi K2), [aistudio.google.com](https://aistudio.google.com) (Gemini). Paid: [console.anthropic.com](https://console.anthropic.com) (Claude), [platform.moonshot.ai](https://platform.moonshot.ai) (Kimi direct), [platform.deepseek.com](https://platform.deepseek.com). Keys can also be set as environment variables (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`, …).
* Settings live in `%LOCALAPPDATA%\Legion\settings.json`. CLI: `legion.cmd set provider groq`, `legion.cmd set model llama-3.3-70b-versatile`, `legion.cmd key groq gsk_...`, `legion.cmd models`.

## 5. Voices

* **Kokoro** (offline, English, natural): `af_heart`, `af_bella`, `af_nicole`, `af_sarah`, `af_sky`, `am_adam`, `am_michael`, `am_fenrir`, `am_puck`, `bf_emma`, `bf_isabella`, `bm_george`, `bm_lewis`.
* **Windows voices** (offline): whatever is installed under Settings → Time & language → Speech (add Arabic there for Arabic replies).
* **Cloned voices**: `clone_voice` tool or say "clone this voice from <file.wav>". First use downloads the Chatterbox model. Install with `python_embeded\python.exe -s -m pip install chatterbox-tts` if the doctor reports it missing.
* Speech rate: `legion.cmd set speech_rate 1.2`. Whisper model size: `legion.cmd set stt_model medium` (better Arabic; `small` is the default).

## 6. Claude + Legion

After installing, restart Claude Desktop. Two servers are available: `comfyui` (from `ai-studio`) and `legion`. Ask Claude things like "use legion to take a screenshot and describe it", "open my Downloads folder", or "speak the summary out loud". Claude Code: `claude mcp list` should show `legion`.

Manual entry for `claude_desktop_config.json`:

```json
"legion": {
  "command": "C:\\ComfyUI\\python_embeded\\python.exe",
  "args": ["-s", "C:\\ComfyUI\\legion\\run_legion.py", "mcp"],
  "env": { "COMFY_BRIDGE_DIR": "C:\\ComfyUI\\claude-comfy" }
}
```

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Header says "Ollama is not running" | Start Ollama from the Start menu (or `ollama serve`). |
| "model 'x' is not pulled" | `ollama pull x`, or pick it in the dropdown (auto-download). |
| Microphone button errors | Browsers only allow the mic on `http://127.0.0.1` / `localhost`; allow the permission prompt. |
| No spoken replies | `legion.cmd doctor` → if `kokoro` is False, `python_embeded\python.exe -s -m pip install -r legion\requirements-voice.txt`. Windows voices are used as fallback automatically. |
| Slow first answer | The local model loads into VRAM once (5–10 s); later answers stream in seconds. Running a video generation at the same time shares the GPU, so expect slowdowns. |
| Image/video tools say ComfyUI is not running | Legion starts it automatically via `Start-ComfyUI.bat`; if that fails, start it yourself and retry. |
| Arabic replies read in an English voice | Pick a Windows Arabic voice in the Voice dropdown (install the Arabic speech pack in Windows settings). Whisper understands Arabic without changes. |

## 8. Developing

```bash
pip install -r requirements.txt            # + requirements-voice.txt for speech
python tests/test_agent.py                 # agent loop, approvals, tool schemas, provider conversions
python tests/test_web_and_mcp.py           # web API + MCP server end-to-end
python run_legion.py serve                 # web UI on Linux/macOS works too (desktop tools are Windows-first)
```

Adding a tool is one function with type hints and a docstring in `legion/tools/*.py`, decorated with `@tool(dangerous=...)`. It appears in the LLM's function list, in the MCP server and in the system prompt automatically.
