"""Which importer and model produced an item. Stored in import_info, never shown in the UI."""
import hashlib
from datetime import datetime, timezone

from app.config import get_settings

# Bump when extraction rules, prompts, resolver or parsers change in a way that can alter what is saved
IMPORTER_VERSION = "2026.10.26-1"
HISTORY_KEEP = 5


def prompt_hash() -> str:
    from app.llm.extract import SYSTEM  # late: extract imports the pipeline pieces
    return hashlib.sha1(SYSTEM.encode()).hexdigest()[:8]


def model_name() -> str:
    s = get_settings()
    return s.openrouter_model if s.llm_provider == "openrouter" else s.llm_model


def current(engine: str = "llm", source_id=None) -> dict:
    """engine: llm | verified | parser:<name> | manual."""
    info = {"importer_version": IMPORTER_VERSION, "engine": engine,
            "model": model_name() if engine in ("llm", "verified") else None,
            "prompt_hash": prompt_hash() if engine in ("llm", "verified") else None,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if source_id is not None:
        info["source_id"] = str(source_id)
    return info


def stamp(item, engine: str = "llm", source_id=None) -> dict:
    """Record this read on the item; the earlier reads stay in history (newest first)."""
    before = dict(item.import_info or {})
    history = list(before.pop("history", []))
    if before:
        history.insert(0, before)
    info = {**current(engine, source_id), "history": history[:HISTORY_KEEP]}
    item.import_info = info
    return info


def is_older(info: dict | None) -> bool:
    """True when the item was read by an earlier importer version (or by none that was recorded)."""
    return (info or {}).get("importer_version") != IMPORTER_VERSION
