"""Hero picture candidates per item: video frames at the moment it comes up, or page photos."""
import logging
import subprocess
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Event, ItemImage, ItemSource, Place, Source
from app.ingest import media, ocr
from app.ingest.items import ItemHint
from app.ingest.timing import mention_time, spread, vtt_cues

log = logging.getLogger(__name__)

# Seconds around the mention: the first is the default, the rest are backups to pick from
OFFSETS = (0.0, 2.0, 4.0, -2.0, 6.0)
FRAME_WIDTH = 720


def frame_times(t: float, duration: float) -> list[float]:
    top = max(duration - 0.5, 0.0)
    out: list[float] = []
    for o in OFFSETS:
        x = round(min(max(t + o, 0.0), top), 2)
        if x not in out:
            out.append(x)
    return out


def extract_frame(video: Path, t: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "3", str(out)], check=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("frame at %.1fs of %s failed: %s", t, video.name, e)
        return False
    return out.is_file() and out.stat().st_size > 0


def _cues(src: Source, video: Path) -> list[tuple[float, str]]:
    stored = (src.raw or {}).get("cues") or []
    if stored:
        return [(float(t), str(x)) for t, x in stored]
    vtt = next(iter(sorted(video.parent.glob("video*.vtt"))), None)
    return vtt_cues(vtt.read_text(encoding="utf-8", errors="replace")) if vtt else []


def _forget(db: Session, src: Source, col, item_id, kind: str) -> bool:
    """Drop this source's earlier candidates for the item. True when the user had picked another image."""
    rows = db.scalars(select(ItemImage).where(ItemImage.source_id == src.id, col == item_id,
                                              ItemImage.kind == kind)).all()
    for r in rows:
        if r.path and kind == "frame":
            (media.media_root() / r.path).unlink(missing_ok=True)
    db.execute(delete(ItemImage).where(ItemImage.source_id == src.id, col == item_id, ItemImage.kind == kind))
    return db.scalars(select(ItemImage.id).where(col == item_id, ItemImage.chosen.is_(True))).first() is not None


def video_images(db: Session, src: Source, video: Path) -> int:
    """Note when each item is mentioned and save a few frames from there. Returns images saved."""
    links = db.scalars(select(ItemSource).where(ItemSource.source_id == src.id)
                       .order_by(ItemSource.position, ItemSource.id)).all()
    if not links:
        return 0
    positions = sorted({link.position for link in links})
    duration = ocr.duration_of(video)
    cues = _cues(src, video)
    names: dict[int, list[str]] = {}
    for link in links:
        item = db.get(Event, link.event_id) if link.event_id else db.get(Place, link.place_id)
        if item is not None:
            names.setdefault(link.position, []).extend(
                [getattr(item, "title", None) or getattr(item, "name", None), getattr(item, "venue_name", None)])
    times = {}
    for pos in positions:
        t = mention_time([n for n in names.get(pos, []) if n], cues)
        times[pos] = t if t is not None else spread(positions.index(pos), len(positions), duration)
    multi = len(positions) > 1
    saved = 0
    for link in links:
        link.mention_at = times[link.position]
        col, item_id = (ItemImage.event_id, link.event_id) if link.event_id else (ItemImage.place_id, link.place_id)
        picked_elsewhere = _forget(db, src, col, item_id, "frame")
        folder = media.media_dir(src.id) / "items"
        for rank, t in enumerate(frame_times(times[link.position], duration)):
            out = folder / f"{item_id}_{rank}.jpg"
            if extract_frame(video, t, out):
                db.add(ItemImage(source_id=src.id, kind="frame", at_seconds=t, rank=rank,
                                 path=str(out.relative_to(media.media_root())).replace("\\", "/"),
                                 chosen=multi and rank == 0 and not picked_elsewhere,
                                 **{col.key: item_id}))
                saved += 1
    db.commit()
    return saved


def page_images(db: Session, src: Source, hint: ItemHint, *, place: Place | None, event: Event | None,
                multi: bool) -> None:
    urls = list(dict.fromkeys(u for u in [*hint.images, hint.image_url] if u))
    for item, col in ((event, ItemImage.event_id), (place, ItemImage.place_id)):
        if item is None:
            continue
        picked_elsewhere = _forget(db, src, col, item.id, "page")
        for rank, url in enumerate(urls):
            db.add(ItemImage(source_id=src.id, kind="page", url=url, rank=rank,
                             chosen=multi and rank == 0 and not picked_elsewhere, **{col.key: item.id}))
