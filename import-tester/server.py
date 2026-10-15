"""Standalone import tester: paste a link, run the same ingest code as prod, see what comes out.

It reuses backend/app/ingest/pipeline.py as is (page fetch, JSON-LD, TikTok, YouTube, maps links,
the local model, ticket price hunt). Only the database is faked, so nothing is saved, and the
map-resolve step (Photon) is skipped: you see the items exactly as extracted, before pinning.
"""
import dataclasses
import json
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))
os.environ.setdefault("DATA_DIR", str(HERE / ".data"))
os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import browser, jobs  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import Source  # noqa: E402
from app.ingest import pipeline, pricing, tiktok  # noqa: E402
from app.ingest.urls import classify, first_url, normalize  # noqa: E402
from app.net import BlockedURL  # noqa: E402
import venue  # noqa: E402

log = logging.getLogger("import-tester")
JOBS: dict[str, dict] = {}


COOKIES = HERE / "cookies.txt"
_public_client = tiktok.public_client


def tiktok_cookies():
    """TikTok-only cookies from import-tester/cookies.txt (tab separated Netscape lines, header optional).
    For age-gated videos. Values are never logged."""
    from http.cookiejar import Cookie
    if not COOKIES.exists():
        return []
    out = []
    for line in COOKIES.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        if not line or line.startswith("#"):
            continue
        parts = line.split("	")
        if len(parts) != 7 or not parts[0].lstrip(".").endswith("tiktok.com"):
            continue
        domain, _, path, secure, expires, name, value = parts
        out.append(Cookie(0, name, value, None, False, domain, True, domain.startswith("."), path, True,
                          secure.upper() == "TRUE", int(float(expires)) if expires.replace(".", "").isdigit() and float(expires) > 0 else None,
                          False, None, None, {}))
    return out


def _client_with_cookies(*a, **k):
    client = _public_client(*a, **k)
    for c in tiktok_cookies():
        client.cookies.jar.set_cookie(c)
    return client


tiktok.public_client = _client_with_cookies
_fetch_post = pipeline.fetch_post


def _checked_fetch_post(url):
    """Same fetch as prod, but an empty record (age-gated or login-only video) stops before the model runs."""
    post = _fetch_post(url)
    if not post.caption.strip() and not post.author and not post.stickers:
        raise ValueError("TikTok returned an empty record for this video: it is most likely age-gated or "
                         "login-only. Export your TikTok cookies to import-tester/cookies.txt to read it")
    return post


pipeline.fetch_post = _checked_fetch_post


class StubDB:
    """Stands in for the database session: the pipeline's reads find nothing, its writes go nowhere."""
    def commit(self): pass
    def add(self, *a, **k): pass
    def flush(self): pass
    def rollback(self): pass
    def get(self, *a, **k): return None
    def execute(self, *a, **k): return None
    def scalars(self, *a, **k): return SimpleNamespace(first=lambda: None, all=lambda: [])


class Capture(logging.Handler):
    """Collect log lines made on an import's own thread, to show them next to the result."""
    def emit(self, record):
        name = threading.current_thread().name
        if name.startswith("import-"):
            JOBS[name[7:]]["logs"].append(f"{time.strftime('%H:%M:%S')} {record.levelname} {record.name}: {record.getMessage()}")


def _stage_hook(state: dict):
    def set_stage(db, job, stage, pct):
        state["stage"], state["pct"] = stage, pct
        state["stages"].append({"t": round(time.time() - state["started"], 1), "stage": stage, "pct": pct})
    return set_stage


def run_import(url: str, state: dict) -> dict:
    """The fast-path half of pipeline.run(), step for step, minus the database."""
    kind = classify(url)
    src = Source(id=uuid.uuid4(), url=url, url_norm=normalize(url), kind=kind, raw={}, status="pending")
    db, job = StubDB(), SimpleNamespace(id=0, payload={"fast_only": True})
    jobs.set_stage(db, job, "reading the link", 10)

    if kind == "tiktok":
        g = pipeline._from_tiktok(db, job, src)
    elif kind == "youtube":
        g = pipeline._from_youtube(db, job, src)
    elif kind in ("gmaps", "applemaps"):
        hints = pipeline._from_maps(src)
        pipeline._llm(db, job, pipeline.llm.classify, hints, src.title or "")
        g = pipeline.Gathered(hints=hints)
    elif kind == "event_page":
        g = pipeline.Gathered(hints=pipeline._from_page(db, job, src))
    else:
        raise pipeline.Unprocessable(f"{kind} links are not supported yet")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    hints = [pipeline.tidy(h, now) for h in g.hints if h.name or h.event_title]
    if any(h.kind == "event" and not pricing.has_price(h) for h in hints):
        jobs.set_stage(db, job, "checking ticket prices", 44)
        try:
            with pipeline._in_line(db, job, 44):
                pricing.enrich(hints, src.url if src.kind == "event_page" else None)
        except Exception as e:  # a price is a nicety, same as prod
            log.warning("price check failed: %s", e)
    # Look every place up on the web (one lookup per venue, shared by its events)
    looked: dict[tuple, dict] = {}
    per_item: list[dict | None] = []
    for i, h in enumerate(hints):
        key = (h.name.lower(), (h.address or "").lower())
        if key not in looked:
            pct = 55 + int(40 * i / max(len(hints), 1))
            try:
                looked[key] = venue.lookup(h, lambda msg, pct=pct: jobs.set_stage(db, job, msg, pct))
            except Exception as e:
                log.warning("venue lookup for %s failed: %s", h.name, e, exc_info=True)
                looked[key] = {"name": h.name, "error": f"{type(e).__name__}: {e}", "flags": []}
        per_item.append(looked[key])
        if "error" not in looked[key]:
            venue.apply(h, looked[key])
    jobs.set_stage(db, job, "done", 100)
    items = [{**dataclasses.asdict(h), "venue": v} for h, v in zip(hints, per_item)]
    return {
        "kind": kind,
        "title": src.title,
        "posted": g.posted.isoformat() if g.posted else None,
        "items": items,
        "source": {"caption": src.caption, "transcript": src.transcript, "raw": src.raw},
        "extracted_text": g.text or None,
        "note": None if hints else "no place or event found in this link",
    }


def worker(job_id: str, url: str) -> None:
    state = JOBS[job_id]
    threading.current_thread().name = f"import-{job_id}"
    jobs.set_stage = _stage_hook(state)  # shared module attribute; one import at a time is fine for a test tool
    try:
        state["result"] = run_import(url, state)
        state["status"] = "done"
    except (pipeline.Unprocessable, BlockedURL) as e:
        state["status"], state["error"] = "failed", str(e)
    except Exception as e:
        state["status"], state["error"] = "failed", f"{type(e).__name__}: {e}"
        state["logs"].append(traceback.format_exc())
    state["elapsed"] = round(time.time() - state["started"], 1)


app = FastAPI(title="Import tester")
_lock = threading.Lock()


class ImportIn(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
def status():
    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        llm = {"ok": s.llm_model in models, "url": s.ollama_url, "model": s.llm_model,
               "note": None if s.llm_model in models else f"model not found, hub has: {', '.join(models) or 'none'}"}
    except Exception as e:
        llm = {"ok": False, "url": s.ollama_url, "model": s.llm_model, "note": f"unreachable ({type(e).__name__})"}
    def up(url, path):
        try:
            return httpx.get(url + path, timeout=3).status_code < 500
        except Exception:
            return False
    return {"llm": llm, "browser": {"ok": browser.available(), "url": s.browser_url or None},
            "tiktok_cookies": {"ok": bool(tiktok_cookies())},
            "searxng": {"ok": up(s.searxng_url, "/healthz")}, "photon": {"ok": up(s.photon_url, "/status")}}


@app.post("/api/import")
def start(body: ImportIn):
    url = first_url(body.url.strip()) or body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "paste a full http(s) link")
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "an import is already running")
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"id": job_id, "url": url, "status": "running", "stage": "starting", "pct": 0,
                    "stages": [], "logs": [], "started": time.time(), "result": None, "error": None}

    def go():
        try:
            worker(job_id, url)
        finally:
            _lock.release()
    threading.Thread(target=go, daemon=True).start()
    return {"id": job_id}


@app.get("/api/import/{job_id}")
def poll(job_id: str):
    st = JOBS.get(job_id)
    if not st:
        raise HTTPException(404, "unknown import")
    out = {k: v for k, v in st.items() if k != "started"}
    out["elapsed"] = st.get("elapsed") or round(time.time() - st["started"], 1)
    return JSONResponse(json.loads(json.dumps(out, default=str)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().addHandler(Capture())
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    import socket
    import webbrowser

    def free_port(start: int) -> int:
        for p in range(start, start + 20):
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", p))
                    return p
                except OSError:
                    continue
        raise SystemExit(f"no free port from {start} to {start + 19}")

    port = free_port(int(os.environ.get("PORT", "8899")))
    print(f"\nImport tester at http://127.0.0.1:{port}  (Ctrl+C to stop)", flush=True)
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
