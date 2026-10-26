"""Job handlers. Each takes (db, job) and returns a result dict or raises."""
import logging
from collections.abc import Callable

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.db.models import AppSettings, Job
from app.notify import ha

log = logging.getLogger(__name__)

Handler = Callable[[Session, Job], dict]
HANDLERS: dict[str, Handler] = {}


def handler(name: str):
    def wrap(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return wrap


@handler("ingest")
def ingest(db: Session, job: Job) -> dict:
    import uuid

    from app import watch
    from app.db.models import Source
    from app.ingest.pipeline import run
    try:
        result = run(db, job)
    except Exception as e:
        db.rollback()
        src = db.get(Source, uuid.UUID(job.payload["source_id"])) if job.payload.get("source_id") else None
        if src is not None and (getattr(e, "permanent", False) or job.attempts >= job.max_attempts):
            watch.after_run(db, src, None, error=f"{type(e).__name__}: {e}")  # last try: record the failure
        raise
    src = db.get(Source, uuid.UUID(job.payload["source_id"])) if job.payload.get("source_id") else None
    if src is not None:
        watch.after_run(db, src, result)
    return result


@handler("watch_scan")
def watch_scan(db: Session, job: Job) -> dict:
    """Queue a read of every standing venue whose weekly check is due."""
    from app import watch
    return watch.scan_due(db)


@handler("expand_occurrences")
def expand_occurrences(db: Session, job: Job) -> dict:
    """Extend every repeating event's dates 120 days ahead."""
    from app import occurrences
    return occurrences.refresh_all(db)


@handler("refresh_home")
def refresh_home(db: Session, job: Job) -> dict:
    """Map center and discovery origin follow HA zone.home unless set by hand."""
    s = db.get(AppSettings, 1)
    if s.home_source != "ha":
        return {"skipped": "home set manually"}
    loc = ha.home_location()
    if not loc:
        raise RuntimeError("Home Assistant did not return zone.home")
    lat, lon = loc
    s.home = from_shape(Point(lon, lat), srid=4326)
    db.commit()
    return {"lat": round(lat, 4), "lon": round(lon, 4)}


@handler("archive")
def archive(db: Session, job: Job) -> dict:
    """Keep a copy of a video (and its thumbnail) the fast path read without downloading."""
    import uuid

    from app.db.models import Source
    from app.ingest import media
    src = db.get(Source, uuid.UUID(job.payload["source_id"]))
    if src is None or not src.url:
        return {"skipped": "source gone"}
    if media.has_video(db, src):
        return {"skipped": "already archived"}
    try:
        dl = media.download(src.url, src.id)
    except media.MediaError as e:
        # Not worth retrying: the video is too long, removed or blocked
        return {"skipped": str(e)}
    kinds = media.archive(db, src, dl)
    db.commit()
    from app.ingest import images
    try:
        images.video_images(db, src, dl.video)
    except Exception as e:  # pictures are a nicety
        log.warning("frame pictures failed for %s: %s", src.id, e)
    return {"archived": kinds, "bytes": sum(p.stat().st_size for p in (dl.video, dl.thumb) if p)}
