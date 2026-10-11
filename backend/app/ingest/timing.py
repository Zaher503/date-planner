"""Where in a video each place is mentioned, from timed captions or a Whisper transcript."""
import re

from rapidfuzz import fuzz

Cue = tuple[float, str]
STAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
GENERIC = {"restaurant", "cafe", "coffee", "bar", "park", "the", "and", "club", "bakery", "pizza", "kitchen", "grill"}
MIN_SCORE = 88


def _seconds(stamp: str) -> float | None:
    m = STAMP.search(stamp)
    if not m:
        return None
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def vtt_cues(vtt: str) -> list[Cue]:
    """(start seconds, text) for each caption, repeated rolling-caption lines collapsed."""
    cues: list[Cue] = []
    start: float | None = None
    lines: list[str] = []

    def flush() -> None:
        text = " ".join(lines).strip()
        if start is not None and text and (not cues or cues[-1][1] != text):
            cues.append((start, text))

    for raw in vtt.splitlines():
        line = raw.strip()
        if "-->" in line:
            flush()
            start, lines = _seconds(line.split("-->")[0]), []
        elif not line:
            flush()
            start, lines = None, []
        elif start is not None:
            line = re.sub(r"<[^>]+>", "", line).strip()
            if line:
                lines.append(line)
    flush()
    return cues


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower().replace("&", " and ")).strip()


def mention_time(names: list[str], cues: list[Cue]) -> float | None:
    """Start of the first caption that says one of the names (or finishes saying it across two)."""
    wanted = [n for n in (_norm(x) for x in names if x) if len(n) >= 4]
    if not wanted or not cues:
        return None
    texts = [_norm(c[1]) for c in cues]
    for i, (start, _) in enumerate(cues):
        if any(fuzz.partial_ratio(n, texts[i]) >= MIN_SCORE for n in wanted):
            return start
    for i in range(len(cues) - 1):
        window = f"{texts[i]} {texts[i + 1]}"
        if any(fuzz.partial_ratio(n, window) >= MIN_SCORE for n in wanted):
            return cues[i][0]
    for i, (start, _) in enumerate(cues):
        words = texts[i].split()
        for n in wanted:
            keys = [w for w in n.split() if len(w) >= 5 and w not in GENERIC]
            if keys and max(keys, key=len) in words:
                return start
    return None


def spread(position: int, count: int, duration: float) -> float:
    """No captions: assume the list is told evenly across the video."""
    return duration * (position + 0.5) / max(count, 1)
