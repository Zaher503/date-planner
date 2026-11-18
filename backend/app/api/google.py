"""Google Places photos for a place, or for the venue of an event (needs GOOGLE_PLACES_KEY)."""
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import google_places
from app.api.auth import current_user
from app.api.common import has_image
from app.api.items import detail, load
from app.config import get_settings
from app.db.models import Event, ItemImage, ItemSource, Place, Source, User
from app.db.session import get_db
from app.ingest import media

router = APIRouter()


def _query(db: Session, kind: str, item_id: uuid.UUID) -> str:
    if kind == "event":
        ev = db.get(Event, item_id)
        place = db.get(Place, ev.place_id) if ev and ev.place_id else None
    elif kind == "place":
        place = db.get(Place, item_id)
    else:
        raise HTTPException(404)
    if place is None:
        raise HTTPException(404)
    return " ".join(p for p in (place.name, place.address_text) if p)


EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _has_picture(db: Session, kind: str, item_id: uuid.UUID) -> bool:
    """The item already has a picture of its own: a saved one, or an image on one of its links."""
    col, link = (ItemImage.event_id, ItemSource.event_id) if kind == "event" else (ItemImage.place_id, ItemSource.place_id)
    if db.scalars(select(ItemImage.id).where(col == item_id)).first() is not None:
        return True
    return db.scalars(select(Source.id).join(ItemSource, ItemSource.source_id == Source.id)
                      .where(link == item_id, has_image())).first() is not None


def _digest(path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def save_search(db: Session, kind: str, item_id: uuid.UUID, photos: list[tuple[bytes, str, str | None]],
                existing: list[ItemImage], first_picture: bool) -> int:
    """Keep every photo of one Google search on disk and put them at the top of the item's Google photos, in
    Google's order; a photo already saved (same bytes) moves up instead of being saved twice. On an item with no
    picture at all the top one becomes the main picture. Returns how many new files were written."""
    col = ItemImage.event_id if kind == "event" else ItemImage.place_id
    root = media.media_root()
    folder = root / "item-images"
    by_hash = {h: row for row in existing if row.path and (h := _digest(root / row.path))}
    top: list[ItemImage] = []
    new = 0
    for body, ctype, author in photos:
        ext = EXT.get(ctype.split(";")[0].strip().lower())
        if ext is None:
            continue
        h = hashlib.sha256(body).hexdigest()
        row = by_hash.get(h)
        if row is None:
            folder.mkdir(parents=True, exist_ok=True)
            name = f"google-{uuid.uuid4().hex}{ext}"
            tmp = folder / f".{name}.tmp"
            tmp.write_bytes(body)
            os.replace(tmp, folder / name)
            row = ItemImage(kind="google", path=f"item-images/{name}", chosen=False, attribution=author,
                            **{col.key: item_id})
            db.add(row)
            by_hash[h] = row
            new += 1
        if row not in top:
            top.append(row)
    for rank, row in enumerate(top + [r for r in existing if r not in top]):
        row.rank = rank
    if first_picture and top:
        top[0].chosen = True
    db.commit()
    return new


@router.post("/api/google-photos/{kind}/{item_id}")
def search_photos(kind: str, item_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Find the place on Google, download every photo it gives (each one a counted download) and keep them all."""
    if not get_settings().google_save_hero:
        raise HTTPException(409, "Saving Google photos is switched off")
    query = _query(db, kind, item_id)
    item = load(db, kind, item_id)
    photos = google_places.photos_for(query)
    got = []
    for p in photos:
        one = google_places.fetch_photo(p["name"])
        if one is None:
            if google_places.capped():
                break
            continue
        got.append((one[0], one[1], p["author"]))
    if not got:
        if google_places.capped():
            raise HTTPException(429, "Today's Google photo limit is reached")
        return {"found": 0, "new": 0, "item": detail(db, item, user)}
    col = ItemImage.event_id if kind == "event" else ItemImage.place_id
    existing = list(db.scalars(select(ItemImage).where(col == item_id, ItemImage.kind == "google")
                               .order_by(ItemImage.rank, ItemImage.id)).all())
    new = save_search(db, kind, item_id, got, existing, first_picture=not _has_picture(db, kind, item_id))
    return {"found": len(got), "new": new, "item": detail(db, item, user)}
