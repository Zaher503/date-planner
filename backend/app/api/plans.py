"""Date-night planner: suggested itineraries and saved plans."""
import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.config import get_settings
from app.db.models import Plan, User
from app.db.session import get_db
from app.ingest.store import home_point
from app.plan import osrm
from app.plan.loader import load_candidates
from app.plan.picker import REACH_M_PER_MIN, Request, suggest

router = APIRouter()

DEFAULT_TRAVEL_MIN = {"drive": 30, "walk": 25}


class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class SuggestIn(BaseModel):
    day: date
    start_time: time
    end_time: time  # earlier than start_time means after midnight
    budget: float | None = Field(default=None, ge=0)
    vibe: list[str] = Field(default_factory=list, max_length=20)
    start: PointIn | None = None
    mode: Literal["drive", "walk"] = "drive"
    max_travel_min: float | None = Field(default=None, gt=0, le=120)


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().default_tz)


def window(day: date, start: time, end: time) -> tuple[datetime, datetime]:
    zone = _tz()
    a = datetime.combine(day, start.replace(tzinfo=None), tzinfo=zone)
    b = datetime.combine(day, end.replace(tzinfo=None), tzinfo=zone)
    if b <= a:
        b = datetime.combine(day + timedelta(days=1), end.replace(tzinfo=None), tzinfo=zone)
    return a, b


@router.post("/api/plans/suggest")
def suggest_plans(body: SuggestIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    start, end = window(body.day, body.start_time, body.end_time)
    origin = (body.start.lat, body.start.lon) if body.start else home_point(db)
    max_travel = body.max_travel_min or DEFAULT_TRAVEL_MIN[body.mode]
    req = Request(start=start, end=end, origin=origin, mode=body.mode, budget=body.budget,
                  vibe=[v.strip().lower() for v in body.vibe if v.strip()], max_travel_min=max_travel)
    reach = max_travel * REACH_M_PER_MIN[body.mode]
    cands = load_candidates(db, start, end, origin, reach, get_settings().default_tz)
    with httpx.Client() as client:
        plans = suggest(cands, req, lambda o, ds, mode: osrm.table(o, ds, mode, client=client))
    return {
        "itineraries": plans,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "start": {"lat": origin[0], "lon": origin[1], "source": "given" if body.start else "home"},
        "considered": {"events": sum(c.type == "event" for c in cands),
                       "places": sum(c.type == "place" for c in cands)},
    }


class ItemRef(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["place", "event"]
    id: str
    title: str


class StopIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    item: ItemRef
    arrive: datetime
    leave: datetime
    role: str | None = None
    travel_min: float | None = None
    mode: Literal["drive", "walk"] | None = None

    @field_validator("arrive", "leave")
    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=_tz())

    @model_validator(mode="after")
    def _order(self):
        if self.leave < self.arrive:
            raise ValueError("leave is before arrive")
        return self


class PlanIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    day: date
    window_start: time | None = Field(default=None, validation_alias=AliasChoices("window_start", "start_time"))
    window_end: time | None = Field(default=None, validation_alias=AliasChoices("window_end", "end_time"))
    budget: float | None = Field(default=None, ge=0)
    vibe: list[str] = Field(default_factory=list, max_length=20)
    stops: list[StopIn] = Field(default_factory=list, max_length=12)


class PlanPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    day: date | None = None
    window_start: time | None = None
    window_end: time | None = None
    budget: float | None = Field(default=None, ge=0)
    vibe: list[str] | None = Field(default=None, max_length=20)
    stops: list[StopIn] | None = Field(default=None, max_length=12)


def _hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def plan_json(p: Plan, users: dict[int, User]) -> dict:
    who = users.get(p.created_by) if p.created_by else None
    return {
        "id": str(p.id), "title": p.title, "day": p.day.isoformat(),
        "window_start": _hhmm(p.window_start), "window_end": _hhmm(p.window_end),
        "budget": float(p.budget) if p.budget is not None else None, "vibe": list(p.vibe or []),
        "stops": p.stops or [],
        "created_by": {"id": who.id, "display_name": who.display_name or who.username} if who else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "ics": f"/api/plans/{p.id}.ics",
    }


def _users(db: Session) -> dict[int, User]:
    return {u.id: u for u in db.scalars(select(User))}


def _stops(stops: list[StopIn]) -> list[dict]:
    return [s.model_dump(mode="json") for s in sorted(stops, key=lambda s: s.arrive)]


def _get(db: Session, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "no such plan")
    return plan


@router.get("/api/plans")
def list_plans(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Upcoming plans soonest first, then past plans newest first."""
    today = datetime.now(_tz()).date()
    plans = db.scalars(select(Plan).order_by(Plan.day.desc()).limit(500)).all()
    upcoming = sorted((p for p in plans if p.day >= today), key=lambda p: (p.day, p.window_start or time.min))
    past = [p for p in plans if p.day < today]
    users = _users(db)
    return [{**plan_json(p, users), "past": p.day < today} for p in upcoming + past]


@router.post("/api/plans", status_code=201)
def create_plan(body: PlanIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    title = (body.title or "").strip() or " + ".join(s.item.title for s in body.stops)[:200] or "Date night"
    plan = Plan(title=title, day=body.day, window_start=body.window_start, window_end=body.window_end,
                budget=body.budget, vibe=body.vibe, stops=_stops(body.stops), created_by=user.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan_json(plan, _users(db))


@router.get("/api/plans/{plan_id:uuid}")
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return plan_json(_get(db, plan_id), _users(db))


@router.patch("/api/plans/{plan_id:uuid}")
def update_plan(plan_id: uuid.UUID, body: PlanPatch, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    plan = _get(db, plan_id)
    for key in body.model_fields_set:
        value = getattr(body, key)
        if key == "stops":
            value = _stops(value or [])
        elif key in ("title", "day", "vibe") and value is None:
            raise HTTPException(422, f"{key} cannot be null")
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return plan_json(plan, _users(db))


@router.delete("/api/plans/{plan_id:uuid}", status_code=204)
def delete_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(current_user)):
    db.delete(_get(db, plan_id))
    db.commit()
    return Response(status_code=204)
