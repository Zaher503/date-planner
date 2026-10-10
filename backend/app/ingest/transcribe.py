"""Speech to text with faster-whisper on the GPU (callers hold the GPU lock).

Only used for videos without TikTok auto-captions or YouTube subtitles. The model is
loaded per call and freed afterwards, because the 8 GB card is shared with Ollama.
"""
import ctypes
import gc
import glob
import logging
import os
import re
import subprocess
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

MODEL = os.environ.get("WHISPER_MODEL", "large-v3-turbo")
COMPUTE = "int8_float16"
# Outro boilerplate Whisper hallucinates on music or silence
JUNK = re.compile(r"thank(s| you) (so much )?for (watching|listening)|subscribe|like and follow|^\W*$", re.I)
_cuda_ready = False


def _preload_cuda() -> None:
    """The pip CUDA wheels are not on the loader path; load them before ctranslate2 needs them."""
    global _cuda_ready
    if _cuda_ready:
        return
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return
    for pkg in (nvidia.cublas, nvidia.cudnn):
        for so in sorted(glob.glob(os.path.join(list(pkg.__path__)[0], "lib", "*.so*"))):
            try:
                ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
    _cuda_ready = True


def audio_of(video: Path):
    """16 kHz mono float32 samples via ffmpeg."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], check=True, capture_output=True, timeout=300).stdout
    return np.frombuffer(raw, dtype=np.float32)


def clean_segments(segments) -> str:
    keep = [s.text.strip() for s in segments
            if s.no_speech_prob < 0.5 and s.avg_logprob > -1.0 and not JUNK.search(s.text)]
    return " ".join(t for t in keep if t)


def transcribe(video: Path) -> str:
    _preload_cuda()
    from faster_whisper import WhisperModel
    audio = audio_of(video)
    if audio.size < 16000:  # under a second of sound
        return ""
    root = get_settings().data_dir / "models" / "whisper"
    root.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(MODEL, device="cuda", compute_type=COMPUTE, download_root=str(root))
    try:
        segments, info = model.transcribe(audio, vad_filter=True, beam_size=5, condition_on_previous_text=False)
        text = clean_segments(list(segments))
        log.info("whisper %s: %d chars, language %s", video.name, len(text), info.language)
        return text[:8000]
    finally:
        del model
        gc.collect()
