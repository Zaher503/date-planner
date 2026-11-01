"""Google Places photos for a place, or for the venue of an event (needs GOOGLE_PLACES_KEY)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import google_places
from app.api.auth import current_user
from app.db.models import Event, Place, User
from app.db.session import get_db

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
        raise HTTPException(502, "Google did not return the photo")
    return Response(got[0], media_type=got[1], headers={"Cache-Control": CACHE_CONTROL})
