"""Text cleanup shared by ingest, edits and the API."""
import re

# Pictographs, dingbats, flags, keycaps and the invisible joiners that glue emoji together
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF\U000E0020-\U000E007F"
    "☀-➿⬀-⯿⌀-⏿■-◿"
    "‼⁉™ℹⓂ〰〽㊗㊙©®"
    "︎️‍⃣]"
)


def strip_emoji(text: str | None) -> str | None:
    """Remove every emoji and tidy the gaps they leave. Empty results become None."""
    if not text:
        return text
    out = EMOJI.sub("", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+([,.;:!?])", r"\1", out)
    out = "\n".join(line.strip() for line in out.split("\n")).strip()
    return out or None


def clean_name(name: str | None) -> str:
    """A venue or event name as written in a caption, without the punctuation around it ("Bacari W Adams?")."""
    out = (name or "").strip()
    out = re.sub(r"^[\s\"'\u201c\u2018#@*]+|[\s\"'\u201d\u2019?!,:;*]+$", "", out)
    return re.sub(r"\s{2,}", " ", out)
