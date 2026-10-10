"""Add a link, text or screenshot. Creates a Source and queues an ingest job."""
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import jobs
from app.api.auth import current_user, require_key, upsert_user, username_from_request
from app.db.models import Job, Source, User
from app.db.session import get_db
from app.ingest.urls import classify, first_url, normalize

router = APIRouter()

MAX_TEXT = 8000
RATE_PER_MIN = 30
_recent: deque[float] = deque()


class AddIn(BaseModel):
    url: str | None = Field(default=None, max_length=4000)
    text: str | None = Field(default=None, max_length=MAX_TEXT)
    # Optional: who sent it from the Shortcut (each phone can set its own)
    user: str | None = Field(default=None, max_length=64)


class AddOut(BaseModel):
    status: str  # queued, exists
    source_id: str
    job_id: int | None = None
    kind: str


def _rate_limit() -> None:
    now = time.monotonic()
    while _recent and now - _recent[0] > 60:
        _recent.popleft()
    if len(_recent) >= RATE_PER_MIN:
        raise HTTPException(429, "too many links, try again in a minute")
    _recent.append(now)


def add_item(db: Session, body: AddIn, user: User | None) -> AddOut:
    raw = (body.url or body.text or "").strip()
    if not raw:
        raise HTTPException(400, "send a url or some text")
    url = first_url(raw)
    if url:
        kind, url_norm = classify(url), normalize(url)
        existing = db.scalars(select(Source).where(Source.url_norm == url_norm)).first()
        if existing:
            return AddOut(status="exists", source_id=str(existing.id), kind=existing.kind)
    else:
        kind, url_norm = "text", None

    src = Source(url=url, url_norm=url_norm, kind=kind, caption=raw if kind == "text" else None,
                 raw={"shared_text": raw} if url and raw != url else {},
                 submitted_by=user.id if user else None,
                 status="stub" if kind == "instagram" else "pending",
                 error="Instagram is not supported, saved for manual review" if kind == "instagram" else None)
    db.add(src)
    db.flush()
    job = None
    if kind != "instagram":
        job = jobs.enqueue(db, "ingest", {"source_id": str(src.id)}, source_id=src.id,
                           submitted_by=user.id if user else None)
    db.commit()
    return AddOut(status="queued" if job else "stub", source_id=str(src.id),
                  job_id=job.id if job else None, kind=kind)


@router.post("/api/add", response_model=AddOut, dependencies=[Depends(require_key)])
def add_with_key(body: AddIn, request: Request, db: Session = Depends(get_db)):
    _rate_limit()
    user = None
    if body.user:
        # Only names that have already signed in through Authentik
        user = db.scalars(select(User).where(User.username == body.user)).first()
    elif username := username_from_request(request):
        user = upsert_user(db, username)
    return add_item(db, body, user)


@router.post("/api/ui/add", response_model=AddOut)
def add_from_ui(body: AddIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _rate_limit()
    return add_item(db, body, user)


@router.get("/api/jobs")
def list_jobs(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Queued and running jobs plus anything finished in the last 5 minutes (for toasts)."""
    recent = func.now() - timedelta(minutes=5)
    rows = db.execute(
        select(Job.id, Job.type, Job.status, Job.stage, Job.pct, Job.error, Job.result,
               Job.source_id, Job.created_at, Job.finished_at, Source.url, Source.title, Source.kind)
        .outerjoin(Source, Source.id == Job.source_id)
        .where(or_(Job.status.in_(("queued", "running")), Job.finished_at > recent))
        .order_by(Job.id.desc()).limit(50)
    ).all()
    return [dict(r._mapping) for r in rows]
