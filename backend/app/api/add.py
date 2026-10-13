"""Add a link, text or screenshot. Creates a Source and queues an ingest job."""
import hashlib
import logging
import time
from collections import deque
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import jobs
from app.api.auth import current_user, require_key, upsert_user, username_from_request
from app.db.models import Job, Source, User
from app.db.session import SessionLocal, get_db
from app.ingest import media
from app.ingest.urls import classify, first_url, identity_of, is_short_link, normalize
from app.net import resolve_redirects

router = APIRouter()
log = logging.getLogger(__name__)

MAX_TEXT = 8000
RATE_PER_MIN = 90
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


def link_identity(url: str) -> str | None:
    """Id of the page behind a link, following share-link redirects, so repeat shares collapse."""
    target = url
    if is_short_link(url):
        try:
            target = resolve_redirects(url, timeout=6)
        except Exception as e:  # best effort: ingest still merges true duplicates later
            log.info("could not resolve %s: %s", url, e)
            return None
    return identity_of(target)


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
        ext_id = link_identity(url)
        if ext_id:
            existing = db.scalars(select(Source).where(Source.adapter == "link",
                                                       Source.external_id == ext_id)).first()
            if existing:
                return AddOut(status="exists", source_id=str(existing.id), kind=existing.kind)
    else:
        kind, url_norm, ext_id = "text", None, None

    src = Source(url=url, url_norm=url_norm, kind=kind, caption=raw if kind == "text" else None,
                 adapter="link" if ext_id else None, external_id=ext_id,
                 raw={"shared_text": raw} if url and raw != url else {},
                 submitted_by=user.id if user else None,
                 status="stub" if kind == "instagram" else "pending",
                 error="Instagram is not supported, saved for manual review" if kind == "instagram" else None)
    db.add(src)
    try:
        db.flush()
        job = None
        if kind != "instagram":
            # Ingest jobs run one at a time in the GPU lane (most of them call the local model)
            job = jobs.enqueue(db, "ingest", {"source_id": str(src.id)}, source_id=src.id, needs_gpu=True,
                               submitted_by=user.id if user else None)
        db.commit()
    except IntegrityError:
        # Same link sent twice at once: the unique constraints let only one through
        db.rollback()
        existing = db.scalars(select(Source).where(
            or_(Source.url_norm == url_norm, (Source.adapter == "link") & (Source.external_id == ext_id)))).first()
        if not existing:
            raise
        return AddOut(status="exists", source_id=str(existing.id), kind=existing.kind)
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


class BulkIn(BaseModel):
    urls: list[str] = Field(max_length=100)


class BulkOut(BaseModel):
    accepted: int


def _add_many(urls: list[str], user_id) -> None:
    """Runs after the response: each link gets its own session so one bad link cannot stop the rest."""
    for url in urls:
        try:
            with SessionLocal() as db:
                user = db.get(User, user_id) if user_id else None
                add_item(db, AddIn(url=url[:4000]), user)
        except Exception as e:
            log.warning("bulk add of %s failed: %s", url, e)


@router.post("/api/ui/add-bulk", response_model=BulkOut)
def add_bulk_from_ui(body: BulkIn, tasks: BackgroundTasks, user: User = Depends(current_user)):
    """Take a whole list at once; the links are saved and queued in the background."""
    urls = list(dict.fromkeys(u.strip() for u in body.urls if u.strip()))
    if not urls:
        raise HTTPException(400, "send at least one link")
    tasks.add_task(_add_many, urls, user.id)
    return BulkOut(accepted=len(urls))


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
