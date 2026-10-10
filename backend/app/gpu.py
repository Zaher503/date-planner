"""One GPU (8 GB) shared with Recipe Box and the Transcriber.

Every GPU step runs inside gpu_lock(): a host-wide flock (/srv/gpu/gpu.lock mounted at
/locks), and, until the other two apps take the same lock, a wait while either of them
reports work in progress.
"""
import fcntl
import logging
import os
import time
from contextlib import contextmanager

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

LOCK_PATH = os.environ.get("GPU_LOCK", "/locks/gpu.lock")
NEIGHBOURS = {
    "recipebox": "http://host.docker.internal:8800/api/jobs",
    "transcriber": "http://host.docker.internal:8810/api/status",
}
MAX_WAIT_S = 45 * 60


def _busy(name: str, data) -> bool:
    if name == "recipebox":
        jobs = data if isinstance(data, list) else data.get("jobs", [])
        return any(j.get("status") in ("queued", "running") for j in jobs)
    return bool(data.get("running") or data.get("queued"))


def neighbours_busy() -> list[str]:
    busy = []
    for name, url in NEIGHBOURS.items():
        try:
            r = httpx.get(url, timeout=3)
            if r.status_code == 200 and _busy(name, r.json()):
                busy.append(name)
        except (httpx.HTTPError, ValueError):
            pass  # down or unreachable means it is not using the GPU
    return busy


def unload_llm() -> None:
    s = get_settings()
    for model in (s.llm_model, s.embed_model):
        try:
            httpx.post(f"{s.ollama_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=30)
        except httpx.HTTPError:
            pass


@contextmanager
def gpu_lock(stage_cb=None):
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "a+") as fh:
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                busy = ["another app (lock)"]
            else:
                busy = neighbours_busy()
                if not busy:
                    break
                fcntl.flock(fh, fcntl.LOCK_UN)
            if time.monotonic() - start > MAX_WAIT_S:
                raise TimeoutError(f"GPU busy for {MAX_WAIT_S // 60} min: {', '.join(busy)}")
            if stage_cb:
                stage_cb(f"waiting for GPU ({', '.join(busy)})")
            time.sleep(10)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
