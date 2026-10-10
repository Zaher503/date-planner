"""Add a link, text or screenshot. Creates a Source and queues an ingest job."""
import hashlib
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import jobs
from app.api.auth import current_user, require_key, upsert_user, username_from_request
from app.db.models import Job, Source, User
from app.db.session import get_db
from app.ingest import media
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
        # Ingest jobs run one at a time in the GPU lane (most of them call the local model)
        job = jobs.enqueue(db, "ingest", {"source_id": str(src.id)}, source_id=src.id, needs_gpu=True,
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


IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE = 10_000_000


def sniff_image(head: bytes) -> str | None:
    """Content type from the file's first bytes (the upload's own type is not trusted)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


async def add_image(db: Session, file: UploadFile, user: User | None) -> AddOut:
    body = await file.read(MAX_IMAGE + 1)
    if len(body) > MAX_IMAGE:
        raise HTTPException(413, "image over 10 MB")
    ctype = sniff_image(body[:16])
    if ctype is None:
        raise HTTPException(415, "send a JPEG, PNG or WebP screenshot")
    digest = hashlib.sha256(body).hexdigest()
    existing = db.scalars(select(Source).where(Source.adapter == "upload", Source.external_id == digest)).first()
    if existing:
        return AddOut(status="exists", source_id=str(existing.id), kind="image")
    src = Source(kind="image", adapter="upload", external_id=digest, submitted_by=user.id if user else None,
                 status="pending", raw={})
    db.add(src)
    db.flush()
    folder = media.media_dir(src.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"image{IMAGE_TYPES[ctype]}"
    path.write_bytes(body)
    src.raw = {"image": f"{src.id}/{path.name}", "filename": (file.filename or "")[:200]}
    media.record(db, src, path, "photo")
    job = jobs.enqueue(db, "ingest", {"source_id": str(src.id)}, source_id=src.id, needs_gpu=True,
                       submitted_by=user.id if user else None)
    db.commit()
    return AddOut(status="queued", source_id=str(src.id), job_id=job.id, kind="image")


@router.post("/api/add-image", response_model=AddOut, dependencies=[Depends(require_key)])
async def add_image_with_key(file: UploadFile = File(...), user: str | None = Form(default=None),
                             db: Session = Depends(get_db)):
    _rate_limit()
    who = db.scalars(select(User).where(User.username == user)).first() if user else None
    return await add_image(db, file, who)


@router.post("/api/ui/add-image", response_model=AddOut)
async def add_image_from_ui(file: UploadFile = File(...), db: Session = Depends(get_db),
                            user: User = Depends(current_user)):
    _rate_limit()
    return await add_image(db, file, user)
