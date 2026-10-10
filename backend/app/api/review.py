"""Review queue: pins the resolver was unsure about, with their alternatives."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.db.models import Candidate, Event, Place, User
from app.db.session import get_db

router = APIRouter()


def _point(geom) -> dict:
    p = to_shape(geom)
    return {"lat": round(p.y, 6), "lon": round(p.x, 6)}


@router.get("/api/review")
def review_queue(db: Session = Depends(get_db), _: User = Depends(current_user)):
    places = db.scalars(select(Place).where(Place.review_status == "needs_review")
                        .order_by(Place.created_at.desc()).limit(100)).all()
    out = []
    for p in places:
        cands = db.scalars(select(Candidate).where(Candidate.place_id == p.id)
                           .order_by(Candidate.chosen.desc(), Candidate.score.desc())).all()
        out.append({
            "id": str(p.id), "name": p.name, "category": p.category, "address": p.address_text,
            "confidence": p.confidence, **_point(p.geom),
            "candidates": [{"id": c.id, "name": c.name, "address": c.address_text, "score": c.score,
                            "provider": c.provider, "chosen": c.chosen, **_point(c.geom)} for c in cands],
        })
    return out


class Choice(BaseModel):
    candidate_id: int | None = None  # None confirms the current pin


@router.post("/api/places/{place_id}/resolve")
def choose(place_id: uuid.UUID, body: Choice, db: Session = Depends(get_db), _: User = Depends(current_user)):
    place = db.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "no such place")
    if body.candidate_id is not None:
        cand = db.get(Candidate, body.candidate_id)
        if cand is None or cand.place_id != place.id:
            raise HTTPException(400, "that candidate does not belong to this place")
        payload = cand.payload or {}
        place.geom = cand.geom
        place.address_text = cand.address_text or place.address_text
        if payload.get("osm_id") and payload.get("kind") == "poi":
            clash = db.scalars(select(Place.id).where(Place.osm_type == payload.get("osm_type"),
                                                      Place.osm_id == payload["osm_id"], Place.id != place.id)).first()
            if clash is None:
                place.osm_type, place.osm_id = payload.get("osm_type"), payload["osm_id"]
        db.execute(update(Candidate).where(Candidate.place_id == place.id).values(chosen=False))
        cand.chosen = True
        # Events at this place move with it
        db.execute(update(Event).where(Event.place_id == place.id)
                   .values(geom=cand.geom, address_text=place.address_text))
    # A person decided: reprocessing must not undo it
    place.user_overrides = {**(place.user_overrides or {}), "geom": True, "review_status": True}
    place.review_status = "ok"
    place.confidence = 1.0
    db.execute(update(Event).where(Event.place_id == place.id, Event.review_status == "needs_review")
               .values(review_status="ok"))
    db.commit()
    return {"id": str(place.id), "review_status": place.review_status, **_point(place.geom)}
