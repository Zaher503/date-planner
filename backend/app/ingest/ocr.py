"""On-screen text from video frames and screenshots, read by the local vision model.

Callers hold the GPU lock. Frames are taken every 2 s (at most 20, spread over the
whole video) and read one at a time; repeated lines are dropped.
"""
import base64
import logging
import re
import subprocess
from pathlib import Path

from app.llm.ollama import LLMError, chat_json

log = logging.getLogger(__name__)

EVERY_S = 2.0
MAX_FRAMES = 20
WIDTH = 768

FRAME_SYSTEM = """You read text off images. Copy every piece of readable text exactly as written:
captions, place names, addresses, prices, dates, times, signs and menus. One item per line.
Ignore app buttons, usernames in the interface, like counts and watermarks. Return an empty
string when there is no text. Never describe the picture and never add words that are not visible."""
FRAME_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

SCREENSHOT_SYSTEM = """You read a screenshot someone saved as a date idea (a social post, a map,
an event page, a menu or a message). Copy all readable text exactly, top to bottom, one item per
line: names of places and events, addresses, dates, times, prices and captions. Skip interface
chrome (status bar, buttons, like counts). Then, on a final line starting with "Picture:", say in
a few words what the image shows if it helps identify the place (for example "rooftop bar with
city view"). Never invent text that is not visible."""


def duration_of(video: Path) -> float:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(video)], check=True, capture_output=True, text=True, timeout=60).stdout
        return float(out.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def frame_interval(duration: float, every: float = EVERY_S, max_frames: int = MAX_FRAMES) -> float:
    """Spread frames over long videos instead of reading only the first 40 seconds."""
    if duration <= 0:
        return every
    return max(every, duration / max_frames)


def extract_frames(video: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("f_*.jpg"):
        f.unlink()
    step = frame_interval(duration_of(video))
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=1/{step:.3f},scale={WIDTH}:-2",
                    "-frames:v", str(MAX_FRAMES), "-q:v", "3", str(out / "f_%03d.jpg")],
                   check=True, timeout=300)
    return sorted(out.glob("f_*.jpg"))


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def dedupe_lines(texts: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for t in texts:
        for line in t.splitlines():
            line = line.strip()
            key = re.sub(r"\W+", " ", line.lower()).strip()
            if key and key not in seen:
                seen.add(key)
                out.append(line)
    return "\n".join(out)


def read_frames(frames: list[Path], progress=None) -> str:
    texts = []
    for i, f in enumerate(frames):
        if progress:
            progress(i, len(frames))
        try:
            texts.append(str(chat_json(FRAME_SYSTEM, "Text in this video frame:", FRAME_SCHEMA,
                                       images=[_b64(f)], timeout=120).get("text", "")))
        except LLMError as e:
            log.warning("frame %s: %s", f.name, e)
    return dedupe_lines(texts)[:6000]


def read_screenshot(image: Path) -> str:
    out = chat_json(SCREENSHOT_SYSTEM, "Read this screenshot:", FRAME_SCHEMA, images=[_b64(image)], timeout=180)
    return str(out.get("text", "")).strip()[:6000]
