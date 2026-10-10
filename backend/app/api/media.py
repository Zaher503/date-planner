"""Source thumbnails: fetched once, then served from DATA_DIR/media/thumbs."""
import hashlib
import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.api.common import image_url
from app.config import get_settings
from app.db.models import Media, Source, User
from app.db.session import get_db
from app.net import BlockedURL, public_client

router = APIRouter()

TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
         "image/avif": ".avif", "image/heic": ".heic"}
MEDIA_TYPE = {ext: ctype for ctype, ext in TYPES.items()}
MAX_BYTES = 5_000_000
CACHE_CONTROL = "private, max-age=604800"
OEMBED = "https://www.tiktok.com/oembed"
# Signed TikTok CDN links expire; these statuses mean "ask oEmbed for a fresh one"
EXPIRED = {403, 404, 410}
MISS_SECONDS = 3600
_misses: dict[uuid.UUID, float] = {}


class NotImage(ValueError):
    pass


def thumbs_dir() -> Path:
    return get_settings().data_dir / "media" / "thumbs"


def cached(source_id: uuid.UUID) -> Path | None:
    # The video archive keeps the original thumbnail; screenshots are their own picture
    folder = get_settings().data_dir / "media" / str(source_id)
    for name in ("thumb.jpg", "image.jpg", "image.png", "image.webp"):
        if (folder / name).is_file():
            return folder / name
    for ext in MEDIA_TYPE:
        p = thumbs_dir() / f"{source_id}{ext}"
        if p.is_file():
            return p
    return None


def fetch_image(client: httpx.Client, url: str) -> tuple[bytes, str]:
    """GET an image, at most 5 MB. Returns (body, content type)."""
    with client.stream("GET", url, headers={"Accept": "image/*"}) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype not in TYPES:
            raise NotImage(f"not an image ({ctype or 'no type'})")
        if int(r.headers.get("content-length") or 0) > MAX_BYTES:
            raise NotImage("image too large")
        chunks, size = [], 0
        for chunk in r.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise NotImage("image too large")
            chunks.append(chunk)
    return b"".join(chunks), ctype


def fresh_tiktok_thumb(client: httpx.Client, db: Session, src: Source) -> str | None:
    """Ask TikTok oEmbed again and store the new thumbnail URL."""
    tt = (src.raw or {}).get("tiktok") or {}
    r = client.get(OEMBED, params={"url": tt.get("url") or src.url})
    if r.status_code != 200:
        return None
    url = r.json().get("thumbnail_url")
    if url:
        src.raw = {**(src.raw or {}), "tiktok": {**tt, "thumbnail_url": url}}
        db.commit()
    return url


def download(db: Session, src: Source) -> tuple[bytes, str]:
    url = image_url(src.raw)
    with public_client(timeout=15) as client:
        if src.kind != "tiktok":
            if not url:
                raise NotImage("no image")
            return fetch_image(client, url)
        try:
            if url:
                return fetch_image(client, url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in EXPIRED:
                raise
        except NotImage:
            pass
        url = fresh_tiktok_thumb(client, db, src)
        if not url:
            raise NotImage("TikTok has no thumbnail for this video")
        return fetch_image(client, url)


def save(db: Session, source_id: uuid.UUID, body: bytes, ctype: str) -> Path:
    """Write atomically (temp file + rename) and record it in media."""
    folder = thumbs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source_id}{TYPES[ctype]}"
    tmp = folder / f".{source_id}.{uuid.uuid4().hex}.tmp"
    tmp.write_bytes(body)
    os.replace(tmp, path)
    rel = f"thumbs/{path.name}"
    if db.scalars(select(Media.id).where(Media.source_id == source_id, Media.kind == "thumb")).first() is None:
        db.add(Media(source_id=source_id, kind="thumb", path=rel, bytes=len(body),
                     sha256=hashlib.sha256(body).hexdigest()))
        db.commit()
    return path


def _file(path: Path) -> FileResponse:
    return FileResponse(path, media_type=MEDIA_TYPE[path.suffix], headers={"Cache-Control": CACHE_CONTROL})


@router.get("/api/thumb/{source_id}")
def thumb(source_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    path = cached(source_id)
    if path:
        return _file(path)
    if time.monotonic() - _misses.get(source_id, -MISS_SECONDS) < MISS_SECONDS:
        raise HTTPException(404, "no image for this source")
    src = db.get(Source, source_id)
    if src is None:
        raise HTTPException(404, "no such source")
    try:
        body, ctype = download(db, src)
    except (httpx.HTTPError, BlockedURL, NotImage, ValueError):
        _misses[source_id] = time.monotonic()
        raise HTTPException(404, "no image for this source") from None
    return _file(save(db, source_id, body, ctype))


@router.get("/api/media/{source_id}/video")
def video(source_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """The archived copy of a source's video (Range requests work, so it can be scrubbed)."""
    row = db.scalars(select(Media).where(Media.source_id == source_id, Media.kind == "video")).first()
    path = get_settings().data_dir / "media" / row.path if row else None
    if path is None or not path.is_file():
        raise HTTPException(404, "no archived video for this source")
    ctype = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}.get(path.suffix, "video/mp4")
    return FileResponse(path, media_type=ctype, headers={"Cache-Control": CACHE_CONTROL})
