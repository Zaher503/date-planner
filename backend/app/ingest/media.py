"""Video download (yt-dlp) and the media archive under DATA_DIR/media/<source_id>/.

The slow path needs the video file; the archive keeps it (plus the thumbnail) so a
deleted TikTok can still be watched later.
"""
import hashlib
import json
import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Media, Source
from app.net import check_url

log = logging.getLogger(__name__)

MAX_DURATION_S = 15 * 60  # date-idea videos are short; anything longer is not worth the GPU time
FORMAT = "bv*[height<=720]+ba/b[height<=720]/b"


class MediaError(RuntimeError):
    pass


@dataclass
class Download:
    folder: Path
    video: Path | None = None
    thumb: Path | None = None
    subs: Path | None = None
    info: dict = field(default_factory=dict)


def media_root() -> Path:
    return get_settings().data_dir / "media"


def media_dir(source_id: uuid.UUID | str) -> Path:
    return media_root() / str(source_id)


def _yt_dlp(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["yt-dlp", "--no-warnings", "--no-playlist", "--ignore-config", *args],
                              check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip().splitlines()[-1:] or ["no output"]
        raise MediaError(f"yt-dlp failed: {tail[0][:300]}") from e
    except subprocess.TimeoutExpired as e:
        raise MediaError("yt-dlp timed out") from e
    except FileNotFoundError as e:
        raise MediaError("yt-dlp is not installed in this image") from e


def probe(url: str) -> dict:
    """Video metadata without downloading (title, description, duration, uploader, subtitles)."""
    check_url(url)
    out = _yt_dlp(["--skip-download", "--dump-single-json", url], timeout=120)
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError as e:
        raise MediaError("yt-dlp returned no metadata") from e


def subtitles(url: str, folder: Path) -> Path | None:
    """English auto-captions only (no video), for the YouTube fast path."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        _yt_dlp(["--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
                 "--sub-format", "vtt", "-o", str(folder / "subs.%(ext)s"), url], timeout=120)
    except MediaError as e:
        log.info("no subtitles: %s", e)
        return None
    return next(iter(sorted(folder.glob("subs*.vtt"))), None)


def download(url: str, source_id: uuid.UUID | str, info: dict | None = None) -> Download:
    """Video (720p at most), thumbnail and auto-captions into the source's media folder."""
    check_url(url)
    info = info or probe(url)
    duration = info.get("duration") or 0
    if duration and duration > MAX_DURATION_S:
        raise MediaError(f"video is {int(duration // 60)} min long, over the {MAX_DURATION_S // 60} min limit")
    folder = media_dir(source_id)
    folder.mkdir(parents=True, exist_ok=True)
    _yt_dlp(["-f", FORMAT, "--merge-output-format", "mp4", "-o", str(folder / "video.%(ext)s"),
             "--write-thumbnail", "--convert-thumbnails", "jpg",
             "--write-auto-subs", "--sub-langs", "en.*,en", "--sub-format", "vtt",
             "--max-filesize", "300M", url], timeout=600)
    video = next((p for p in folder.glob("video.*") if p.suffix in (".mp4", ".webm", ".mkv", ".mov")), None)
    thumb = folder / "video.jpg"
    if thumb.exists():
        thumb = thumb.replace(folder / "thumb.jpg")
    subs = next(iter(sorted(folder.glob("video*.vtt"))), None)
    if video is None:
        raise MediaError("yt-dlp finished but no video file was written")
    return Download(folder=folder, video=video, thumb=thumb if thumb.exists() else None, subs=subs, info=info)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(db: Session, src: Source, path: Path, kind: str) -> Media:
    """Add (or refresh) the Media row for a file in the archive."""
    rel = str(path.relative_to(media_root())).replace("\\", "/")
    row = db.scalars(select(Media).where(Media.source_id == src.id, Media.kind == kind)).first()
    if row is None:
        row = Media(source_id=src.id, kind=kind, path=rel)
        db.add(row)
    row.path, row.bytes, row.sha256 = rel, path.stat().st_size, _sha256(path)
    db.flush()
    return row


def archive(db: Session, src: Source, dl: Download) -> list[str]:
    kinds = []
    if dl.video:
        record(db, src, dl.video, "video")
        kinds.append("video")
    if dl.thumb:
        record(db, src, dl.thumb, "thumb")
        kinds.append("thumb")
    return kinds


def remove(source_id: uuid.UUID | str) -> None:
    shutil.rmtree(media_dir(source_id), ignore_errors=True)


def has_video(db: Session, src: Source) -> Path | None:
    row = db.scalars(select(Media).where(Media.source_id == src.id, Media.kind == "video")).first()
    if row is None:
        return None
    path = media_root() / row.path
    return path if path.exists() else None
