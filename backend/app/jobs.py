"""Postgres job queue (SELECT ... FOR UPDATE SKIP LOCKED)."""
import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.db.models import Job

WORKER_ID = socket.gethostname()


def enqueue(db: Session, type_: str, payload: dict | None = None, *, needs_gpu: bool = False,
            source_id=None, submitted_by: int | None = None, run_after: datetime | None = None) -> Job:
    job = Job(type=type_, payload=payload or {}, needs_gpu=needs_gpu, source_id=source_id,
              submitted_by=submitted_by, run_after=run_after or datetime.now(timezone.utc))
    db.add(job)
    db.flush()
    return job


def claim(db: Session, *, gpu: bool | None = None, types: list[str] | None = None) -> Job | None:
    """Lock and mark the next due job as running. gpu=None takes either kind.
    types limits it to job types this worker can handle (others stay queued)."""
    q = (select(Job).where(Job.status == "queued", Job.run_after <= datetime.now(timezone.utc))
         .order_by(Job.run_after, Job.id).limit(1).with_for_update(skip_locked=True))
    if gpu is not None:
        q = q.where(Job.needs_gpu.is_(gpu))
    if types is not None:
        q = q.where(Job.type.in_(types))
    job = db.scalars(q).first()
    if job:
        job.status, job.locked_at, job.locked_by = "running", datetime.now(timezone.utc), WORKER_ID
        job.attempts += 1
        job.stage, job.pct, job.error = "starting", 0, None
        db.commit()
    return job


def set_stage(db: Session, job: Job, stage: str, pct: int) -> None:
    db.execute(update(Job).where(Job.id == job.id).values(stage=stage, pct=max(0, min(100, pct))))
    db.commit()


def finish(db: Session, job: Job, result: dict | None = None) -> None:
    job.status, job.stage, job.pct = "done", "done", 100
    job.result = result or {}
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def fail(db: Session, job: Job, error: str, *, retry: bool = True) -> None:
    """Retry with backoff (1, 4, 9 ... minutes) until max_attempts, then fail."""
    job.error = error[:2000]
    if retry and job.attempts < job.max_attempts:
        job.status, job.stage = "queued", "retrying"
        job.run_after = datetime.now(timezone.utc) + timedelta(minutes=job.attempts ** 2)
    else:
        job.status, job.stage = "failed", "failed"
        job.finished_at = datetime.now(timezone.utc)
    db.commit()


def requeue_stale(db: Session, older_than: timedelta = timedelta(0)) -> int:
    """Put jobs that were running when the worker died back in the queue."""
    cutoff = datetime.now(timezone.utc) - older_than
    res = db.execute(update(Job).where(Job.status == "running",
                                       or_(Job.locked_at.is_(None), Job.locked_at <= cutoff))
                     .values(status="queued", stage="requeued", locked_at=None, locked_by=None))
    db.commit()
    return res.rowcount
