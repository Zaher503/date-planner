"""Speech to text through the shared AI hub's Whisper (the gateway queues it with the other GPU work).

Only used for videos without TikTok auto-captions or YouTube subtitles. The audio is extracted here
and sent as a small 16 kHz mono file; the model lives in the hub, not in this container.
"""
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.config import get_settings
from app.llm import ollama

log = logging.getLogger(__name__)

MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
# Outro boilerplate Whisper hallucinates on music or silence
JUNK = re.compile(r"thank(s| you) (so much )?for (watching|listening)|subscribe|like and follow|^\W*$", re.I)


class TranscribeError(RuntimeError):
    pass


def audio_of(video: Path, out: Path) -> float:
    """Write 16 kHz mono WAV; returns its length in seconds."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(out)],
                   check=True, capture_output=True, timeout=300)
    return max((out.stat().st_size - 44) / 32000, 0.0)  # 16-bit mono at 16 kHz


def keep_segment(s: dict) -> bool:
    return s.get("no_speech_prob", 0) < 0.5 and s.get("avg_logprob", 0) > -1.0 and not JUNK.search(s.get("text", ""))


def clean_segments(segments: list[dict]) -> str:
    keep = [s["text"].strip() for s in segments if keep_segment(s)]
    return " ".join(t for t in keep if t)


def transcribe(video: Path) -> tuple[str, list[tuple[float, str]]]:
    """Transcript plus (start seconds, text) for each kept segment."""
    s = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        try:
            seconds = audio_of(video, wav)
        except (subprocess.SubprocessError, OSError) as e:
            raise TranscribeError(f"could not read the audio: {e}") from e
        if seconds < 1:
            return "", []
        ollama.announce("transcribe", MODEL, seconds)
        try:
            with open(wav, "rb") as f:
                r = httpx.post(f"{s.ollama_url}/v1/audio/transcriptions", files={"file": ("audio.wav", f, "audio/wav")},
                               data={"model": MODEL, "vad_filter": "true", "beam_size": "5"},
                               headers={**ollama.headers(seconds), "X-Model": MODEL}, timeout=3600)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TranscribeError(f"whisper call failed: {type(e).__name__}: {e}") from e
    kept = [g for g in data.get("segments", []) if keep_segment(g)]
    text = clean_segments(kept)
    log.info("whisper %s: %d chars, language %s", video.name, len(text), data.get("language"))
    return text[:8000], [(float(g["start"]), g["text"].strip()) for g in kept if g.get("text", "").strip()]
