"""Worker process: job lanes plus the scheduler.

One GPU lane (at most one GPU job at a time) and two CPU lanes. Run: python -m app.worker
"""
import logging
import signal
import threading
import time
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs
from app.db.models import Job
from app.db.session import SessionLocal
from app.tasks import HANDLERS

log = logging.getLogger("worker")
stop = threading.Event()
IDLE_SLEEP = 2.0
CPU_LANES = 2


def run_one(db: Session, job: Job) -> None:
    fn = HANDLERS.get(job.type)
    if fn is None:
        jobs.fail(db, job, f"no handler for job type {job.type!r}", retry=False)
        return
    log.info("job %s %s start (attempt %s)", job.id, job.type, job.attempts)
    try:
        result = fn(db, job)
    except Exception as e:  # a job must never take the lane down
        db.rollback()
        log.error("job %s %s failed: %s\n%s", job.id, job.type, e, traceback.format_exc())
        jobs.fail(db, job, f"{type(e).__name__}: {e}", retry=not getattr(e, "permanent", False))
    else:
        jobs.finish(db, job, result)
        log.info("job %s %s done", job.id, job.type)


def lane(gpu: bool) -> None:
    while not stop.is_set():
        with SessionLocal() as db:
            job = jobs.claim(db, gpu=gpu, types=list(HANDLERS))
            if job:
                run_one(db, job)
                continue
        stop.wait(IDLE_SLEEP)


def enqueue_once(type_: str, payload: dict | None = None, needs_gpu: bool = False) -> None:
    """Scheduler helper: skip if the same job type is already waiting or running."""
    with SessionLocal() as db:
        waiting = db.scalars(select(Job.id).where(Job.type == type_, Job.status.in_(("queued", "running")))).first()
        if waiting is None:
            jobs.enqueue(db, type_, payload, needs_gpu=needs_gpu)
            db.commit()


def make_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="America/Los_Angeles")
    sched.add_job(enqueue_once, "cron", hour=4, minute=10, args=["refresh_home"], id="refresh_home")
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        n = jobs.requeue_stale(db)
        if n:
            log.info("requeued %s jobs left running by the last worker", n)
    enqueue_once("refresh_home")

    threads = [threading.Thread(target=lane, args=(True,), name="gpu", daemon=True)]
    threads += [threading.Thread(target=lane, args=(False,), name=f"cpu{i}", daemon=True) for i in range(CPU_LANES)]
    for t in threads:
        t.start()
    sched = make_scheduler()
    sched.start()

    def _stop(*_):
        stop.set()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker up: handlers %s", sorted(HANDLERS))
    while not stop.is_set():
        time.sleep(1)
    sched.shutdown(wait=False)
    for t in threads:
        t.join(timeout=30)


if __name__ == "__main__":
    main()
