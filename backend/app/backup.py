"""Nightly database backup: pg_dump -Fc into DATA_DIR/backups, newest 7 kept."""
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings

log = logging.getLogger(__name__)

KEEP = 7
PREFIX = "dates-"  # only these files are ever pruned; hand-made dumps (pre-cleanup-*.dump) stay
TIMEOUT_S = 1800


class BackupError(RuntimeError):
    pass


def dump_command(database_url: str, out: Path) -> tuple[list[str], dict[str, str]]:
    """The pg_dump argument list and the extra environment (the password never goes on the command line)."""
    url = make_url(database_url)
    cmd = ["pg_dump", "-Fc", "--no-owner", "-h", url.host or "localhost", "-p", str(url.port or 5432),
           "-U", url.username or "dates", "-f", str(out), url.database or "dates"]
    return cmd, ({"PGPASSWORD": url.password} if url.password else {})


def prune(folder: Path, keep: int = KEEP) -> list[str]:
    """Delete the oldest automatic dumps beyond `keep` (names sort by date). Returns what was removed."""
    dumps = sorted(p for p in folder.glob(f"{PREFIX}*.dump") if p.is_file())
    gone = dumps[:-keep] if keep > 0 else dumps
    for p in gone:
        p.unlink()
    return [p.name for p in gone]


def run_backup(now: datetime | None = None) -> dict:
    s = get_settings()
    folder = s.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now()
    final = folder / f"{PREFIX}{now:%Y-%m-%d-%H%M}.dump"
    part = final.with_suffix(".dump.part")  # written aside so a failed run never leaves a broken dump
    cmd, extra = dump_command(s.database_url, part)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=TIMEOUT_S, env={**os.environ, **extra})
    except FileNotFoundError as e:
        raise BackupError("pg_dump is not installed in this image") from e
    except subprocess.TimeoutExpired as e:
        part.unlink(missing_ok=True)
        raise BackupError("pg_dump timed out") from e
    except subprocess.CalledProcessError as e:
        part.unlink(missing_ok=True)
        tail = (e.stderr or "").strip().splitlines()[-1:] or ["no message"]
        raise BackupError(f"pg_dump failed: {tail[0][:300]}") from e
    part.replace(final)
    removed = prune(folder)
    log.info("backup %s (%s bytes), pruned %s", final.name, final.stat().st_size, removed)
    return {"file": final.name, "bytes": final.stat().st_size, "pruned": removed}
