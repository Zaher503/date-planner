"""Google Places photos for a place, or for the venue of an event (needs GOOGLE_PLACES_KEY)."""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import google_places
from app.api.auth import current_user
from app.api.common import has_image
from app.config import get_settings
from app.db.models import Event, ItemImage, ItemSource, Place, Source, User
from app.db.session import get_db
from app.ingest import media

router = APIRouter()

CACHE_CONTROL = "private, max-age=3600"


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


def save_hero(db: Session, kind: str, item_id: uuid.UUID, body: bytes, ctype: str, author: str | None) -> bool:
    """Keep the first Google photo as the hero of an item that has no picture at all, so the list can show it
    without asking Google again. A real picture from a later import replaces it."""
    ext = EXT.get(ctype.split(";")[0].strip().lower())
    if ext is None or not get_settings().google_save_hero:
        return False
    col, link = (ItemImage.event_id, ItemSource.event_id) if kind == "event" else (ItemImage.place_id, ItemSource.place_id)
    if db.scalars(select(ItemImage.id).where(col == item_id)).first() is not None:
        return False
    if db.scalars(select(Source.id).join(ItemSource, ItemSource.source_id == Source.id)
                  .where(link == item_id, has_image())).first() is not None:
        return False
    folder = media.media_root() / "item-images"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"google-{uuid.uuid4().hex}{ext}"
    tmp = folder / f".{name}.tmp"
    tmp.write_bytes(body)
    os.replace(tmp, folder / name)
    db.add(ItemImage(kind="google", path=f"item-images/{name}", rank=0, chosen=True, attribution=author,
                     **{col.key: item_id}))
    db.commit()
    return True


@router.get("/api/google-photos/{kind}/{item_id}")
def list_photos(kind: str, item_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    photos = google_places.photos_for(_query(db, kind, item_id))
    return {"photos": [{"url": f"/api/google-photo/{kind}/{item_id}/{i}", "author": p["author"]}
                       for i, p in enumerate(photos)]}


@router.get("/api/google-photo/{kind}/{item_id}/{index}")
def photo(kind: str, item_id: uuid.UUID, index: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    photos = google_places.photos_for(_query(db, kind, item_id))
    if not 0 <= index < len(photos):
        raise HTTPException(404)
    got = google_places.fetch_photo(photos[index]["name"])
    if got is None:
        raise HTTPException(429 if google_places.capped() else 502, "No Google photo right now")
    if index == 0:
        save_hero(db, kind, item_id, got[0], got[1], photos[0]["author"])
    return Response(got[0], media_type=got[1], headers={"Cache-Control": CACHE_CONTROL})
