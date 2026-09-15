"""Speech-to-text (faster-whisper) and text-to-speech (Kokoro -> Windows voices -> Chatterbox clones).

Every engine is optional: missing packages degrade gracefully and report what to install.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from .config import KOKORO_VOICES, Settings, data_dir

IS_WIN = sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------
class STT:
    _model = None
    _model_name = None

    def __init__(self, settings: Settings):
        self.settings = settings

    def _load(self):
        name = self.settings.get("stt_model", "small")
        if STT._model is None or STT._model_name != name:
            from faster_whisper import WhisperModel  # pip install faster-whisper
            try:
                STT._model = WhisperModel(name, device="cuda", compute_type="float16")
            except Exception:
                STT._model = WhisperModel(name, device="cpu", compute_type="int8")
            STT._model_name = name
        return STT._model

    def transcribe_file(self, path: str, language: str | None = None) -> str:
        try:
            model = self._load()
        except ImportError:
            return "Error: pip install faster-whisper"
        lang = language or self.settings.get("stt_language") or None
        segments, info = model.transcribe(str(path), language=lang, vad_filter=True, beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
        return text

    def transcribe_bytes(self, data: bytes, suffix: str = ".webm", language: str | None = None) -> str:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            tmp = fh.name
        try:
            return self.transcribe_file(tmp, language=language)
        finally:
            try:
                Path(tmp).unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
def _write_wav(path: Path, samples, sample_rate: int) -> None:
    import numpy as np
    arr = np.asarray(samples, dtype="float32")
    pcm = (np.clip(arr, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def play_wav(path: Path) -> None:
    """Play a wav file through the default output device (blocking)."""
    try:
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(str(path), dtype="float32")
        sd.play(data, sr)
        sd.wait()
        return
    except Exception:
        pass
    if IS_WIN:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    elif shutil.which("aplay"):
        subprocess.run(["aplay", "-q", str(path)])
    elif shutil.which("afplay"):
        subprocess.run(["afplay", str(path)])


class TTS:
    _kokoro = None

    def __init__(self, settings: Settings):
        self.settings = settings
        self.out_dir = data_dir() / "tts"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.clone_dir = data_dir() / "voices"
        self.clone_dir.mkdir(parents=True, exist_ok=True)

    # -- catalog -------------------------------------------------------------
    def windows_voices(self) -> list[str]:
        if not IS_WIN:
            return []
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Add-Type -AssemblyName System.Speech; "
                                  "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
                                  "| % { $_.VoiceInfo.Name }"], capture_output=True, text=True, timeout=20)
            return [v.strip() for v in out.stdout.splitlines() if v.strip()]
        except Exception:
            return []

    def clones(self) -> list[str]:
        return sorted(p.stem for p in self.clone_dir.glob("*.wav"))

    def available_voices(self) -> dict:
        kokoro_ok = self._kokoro_available()
        return {
            "kokoro": KOKORO_VOICES if kokoro_ok else [],
            "kokoro_installed": kokoro_ok,
            "windows": [f"windows:{v}" for v in self.windows_voices()],
            "clones": [f"clone:{c}" for c in self.clones()],
            "current": self.settings.get("voice"),
        }

    @staticmethod
    def _kokoro_available() -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except Exception:
            return False

    # -- engines -------------------------------------------------------------
    def _kokoro_synth(self, text: str, voice: str, out: Path) -> Path:
        import numpy as np
        from kokoro import KPipeline  # pip install kokoro soundfile
        lang = "b" if voice.startswith("b") else "a"
        if TTS._kokoro is None or TTS._kokoro[0] != lang:
            TTS._kokoro = (lang, KPipeline(lang_code=lang))
        pipe = TTS._kokoro[1]
        chunks = []
        for _, _, audio in pipe(text, voice=voice, speed=float(self.settings.get("speech_rate", 1.0))):
            chunks.append(np.asarray(audio))
        _write_wav(out, np.concatenate(chunks) if chunks else np.zeros(1), 24000)
        return out

    def _windows_synth(self, text: str, voice_name: str | None, out: Path) -> Path:
        rate = int((float(self.settings.get("speech_rate", 1.0)) - 1.0) * 5)  # SAPI rate -10..10
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            + (f"try {{ $s.SelectVoice('{voice_name}') }} catch {{}}; " if voice_name else "")
            + f"$s.Rate = {rate}; "
            f"$s.SetOutputToWaveFile('{out}'); "
            "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", script], input=text, text=True,
                       capture_output=True, timeout=120)
        return out

    def _clone_synth(self, text: str, name: str, out: Path) -> Path:
        sample = self.clone_dir / f"{name}.wav"
        if not sample.exists():
            raise FileNotFoundError(f"no cloned voice '{name}'. Available: {self.clones()}")
        import torchaudio as ta
        from chatterbox.tts import ChatterboxTTS  # pip install chatterbox-tts
        model = ChatterboxTTS.from_pretrained(device="cuda")
        wav = model.generate(text, audio_prompt_path=str(sample))
        ta.save(str(out), wav, model.sr)
        return out

    # -- public --------------------------------------------------------------
    def synthesize(self, text: str, voice: str | None = None, play: bool = False) -> Path | None:
        text = (text or "").strip()
        if not text:
            return None
        voice = voice or self.settings.get("voice") or "af_heart"
        engine = self.settings.get("tts_engine", "auto")
        out = self.out_dir / f"say_{int(time.time() * 1000)}.wav"
        if engine == "none":
            return None
        try:
            if voice.startswith("clone:"):
                self._clone_synth(text, voice[6:], out)
            elif voice.startswith("windows:") or engine == "windows":
                self._windows_synth(text, voice[8:] if voice.startswith("windows:") else None, out)
            elif engine in ("auto", "kokoro") and self._kokoro_available():
                self._kokoro_synth(text, voice if voice in KOKORO_VOICES else "af_heart", out)
            elif IS_WIN:
                self._windows_synth(text, None, out)
            else:
                return None
        except Exception as e:
            if IS_WIN and not voice.startswith("windows:"):
                try:
                    self._windows_synth(text, None, out)
                except Exception:
                    raise RuntimeError(f"TTS failed: {e}")
            else:
                raise RuntimeError(f"TTS failed: {e}")
        if play and out.exists():
            play_wav(out)
        return out if out.exists() else None

    def add_clone(self, name: str, sample_wav: str) -> str:
        src = Path(sample_wav).expanduser()
        if not src.is_file():
            return f"Error: {src} not found"
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_").lower() or "voice"
        dst = self.clone_dir / f"{safe}.wav"
        if src.suffix.lower() != ".wav":
            try:
                import soundfile as sf
                data, sr = sf.read(str(src))
                sf.write(str(dst), data, sr)
            except Exception as e:
                return f"Error converting sample to wav: {e}"
        else:
            shutil.copy2(src, dst)
        try:
            import chatterbox  # noqa: F401
            note = ""
        except Exception:
            note = " Install the cloning engine with:  pip install chatterbox-tts"
        return f"Voice 'clone:{safe}' saved.{note}"


def doctor() -> dict:
    """Report which speech components are installed."""
    def has(mod):
        try:
            __import__(mod)
            return True
        except Exception:
            return False
    return {
        "faster_whisper (ears)": has("faster_whisper"),
        "kokoro (voice)": has("kokoro"),
        "chatterbox (voice cloning)": has("chatterbox"),
        "sounddevice (mic/speaker)": has("sounddevice"),
        "soundfile": has("soundfile"),
        "windows_voices": len(TTS(Settings()).windows_voices()) if IS_WIN else 0,
    }
