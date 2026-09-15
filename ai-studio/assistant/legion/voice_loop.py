"""Hands-free terminal voice loop: listen (VAD) -> whisper -> agent -> speak.

    python -m legion voice            # continuous listening
    python -m legion voice --ptt      # push-to-talk: press Enter to talk, Enter to stop

Say "stop" / "quit" to exit. Optional wake word in settings ("legion"): only sentences that
start with it are handled.
"""
from __future__ import annotations

import queue
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from .agent import Agent
from .config import Settings
from .speech import STT, TTS

SR = 16000


def _record_vad(threshold: float = 0.015, silence_s: float = 1.2, max_s: float = 30.0) -> np.ndarray | None:
    """Record from the default mic until `silence_s` of quiet after speech began."""
    import sounddevice as sd
    q: queue.Queue = queue.Queue()

    def cb(indata, frames, t, status):
        q.put(indata.copy())

    chunks, started, last_voice, t0 = [], False, time.time(), time.time()
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=int(SR * 0.05), callback=cb):
        while True:
            block = q.get()
            level = float(np.sqrt(np.mean(block ** 2)))
            now = time.time()
            if level > threshold:
                if not started:
                    started = True
                    print("  listening...", end="\r", flush=True)
                last_voice = now
            if started:
                chunks.append(block)
                if now - last_voice > silence_s or now - t0 > max_s:
                    break
            elif now - t0 > 60:  # nothing said for a minute -> return and let the loop continue
                return None
    return np.concatenate(chunks)[:, 0] if chunks else None


def _record_ptt() -> np.ndarray | None:
    import sounddevice as sd
    input("Press Enter and speak; press Enter again when done... ")
    frames = []

    def cb(indata, frames_, t, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", callback=cb):
        input()
    return np.concatenate(frames)[:, 0] if frames else None


def _save_wav(audio: np.ndarray) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(tmp.name, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return tmp.name


def run(ptt: bool = False) -> int:
    try:
        import sounddevice  # noqa: F401  (presence check)
    except ImportError:
        print("pip install sounddevice soundfile   (microphone support)")
        return 1
    settings = Settings()
    agent, stt, tts = Agent(settings), STT(settings), TTS(settings)
    wake = (settings.get("wake_word") or "").lower().strip()
    print(f"Legion voice mode. Brain: {settings.get('provider')}/{settings.get('model')}  Voice: {settings.get('voice')}")
    print("Say 'stop' or 'quit' to exit." + (f" Wake word: '{wake}'" if wake else ""))
    tts.synthesize("Ready.", play=True)
    while True:
        audio = _record_ptt() if ptt else _record_vad()
        if audio is None or len(audio) < SR * 0.4:
            continue
        path = _save_wav(audio)
        try:
            text = stt.transcribe_file(path).strip()
        finally:
            Path(path).unlink(missing_ok=True)
        if not text:
            continue
        low = text.lower().strip(" .!?")
        if wake:
            if not low.startswith(wake):
                continue
            text = text[len(wake):].strip(" ,.!?") or text
            low = text.lower()
        print(f"\nYou: {text}")
        if low in ("stop", "quit", "exit", "goodbye"):
            tts.synthesize("Goodbye.", play=True)
            return 0
        if agent.pending and low in ("yes", "yes do it", "approve", "ok", "okay", "go ahead", "confirm"):
            result = agent.approve(True)
        elif agent.pending and low in ("no", "cancel", "decline", "stop that"):
            result = agent.approve(False)
        else:
            result = agent.ask(text)
        for ev in result.tool_events:
            print(f"  [tool] {ev['tool']} -> {ev['result'][:120].replace(chr(10), ' ')}")
        print(f"Legion: {result.text}")
        speech = result.text
        if result.needs_approval:
            speech += " Say yes to approve or no to cancel."
        try:
            tts.synthesize(speech[:1500], play=True)
        except Exception as e:
            print(f"  (voice output failed: {e})")


if __name__ == "__main__":
    sys.exit(run(ptt="--ptt" in sys.argv))
