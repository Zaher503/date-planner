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
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("DATA_DIR", str(HERE / ".data"))
os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse  # noqa: E402
from starlette.background import BackgroundTask  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import browser, jobs  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.models import Source  # noqa: E402
from app.ingest import pipeline, pricing, tiktok  # noqa: E402
from app.ingest.urls import classify, first_url, normalize  # noqa: E402
from app.net import BlockedURL  # noqa: E402
from app.ingest import venue  # noqa: E402

log = logging.getLogger("import-tester")
HOME = (float(os.environ.get("HOME_LAT", "34.0522")), float(os.environ.get("HOME_LON", "-118.2437")))
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
                looked[key] = venue.lookup(None, h, HOME, lambda msg, pct=pct: jobs.set_stage(db, job, msg, pct))
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
        try:
            build_preview(state["result"])
        except Exception:
            state["logs"].append("prod UI preview failed:\n" + traceback.format_exc())
        state["status"] = "done"
    except (pipeline.Unprocessable, BlockedURL) as e:
        state["status"], state["error"] = "failed", str(e)
    except Exception as e:
        state["status"], state["error"] = "failed", f"{type(e).__name__}: {e}"
        state["logs"].append(traceback.format_exc())
    state["elapsed"] = round(time.time() - state["started"], 1)


app = FastAPI(title="Import tester")
_lock = threading.Lock()

# The prod UI and map tiles are proxied from the running app on a second port, with a fake API fed by the last import
BUILD = HERE.parent / "frontend" / "build"
PREVIEW: dict = {"items": {}}
PREVIEW_PORT: list[int] = []


def _price_label(h: dict) -> str | None:
    if h.get("price_text"):
        return h["price_text"]
    if h.get("is_free"):
        return "Free"
    lo, hi = h.get("price_min"), h.get("price_max")
    if lo is not None and hi is not None and hi != lo:
        return f"${lo:g}-${hi:g}"
    if lo is not None or hi is not None:
        return f"${(lo if lo is not None else hi):g}"
    return None


def build_preview(result: dict) -> None:
    """Turn the extracted items into the shapes the prod API would return for them."""
    now = datetime.now(timezone.utc).isoformat()
    ns = uuid.UUID("00000000-0000-4000-8000-00000000d47e")
    places: dict[tuple, dict] = {}
    out: dict[str, dict] = {}

    def coords(h):
        return (h["lat"] if h.get("lat") is not None else HOME[0], h["lon"] if h.get("lon") is not None else HOME[1])

    def images(h):
        urls = list(dict.fromkeys(([h["image_url"]] if h.get("image_url") else []) + (h.get("images") or [])))
        return [{"id": i + 1, "kind": "page", "at": None, "chosen": i == 0, "url": u, "video": None} for i, u in enumerate(urls)]

    def common(h, iid, kind):
        lat, lon = coords(h)
        flags = h.get("flags") or []
        return {
            "id": iid, "type": kind, "title": h.get("event_title") or h["name"], "category": h.get("category"),
            "description": h.get("description"), "tags": h.get("tags") or [], "lat": lat, "lon": lon,
            "address_text": h.get("address"), "review_status": "needs_review" if flags else "ok", "confidence": None,
            "origin": "import", "created_at": now, "updated_at": now, "edited": [], "price_label": _price_label(h),
            "sources": [{"id": str(uuid.uuid5(ns, "source")), "kind": result["kind"], "url": None, "title": result.get("title"),
                         "caption": None, "thumb": None, "video": None, "created_at": now, "fetched_at": now, "submitted_by": None}],
            "review_reasons": flags, "images": images(h), "me": None, "others": [], "candidates": [],
        }

    for n, h in enumerate(result["items"]):
        key = (h["name"].lower(), (h.get("address") or "").lower())
        is_place = h["kind"] == "place"
        if key not in places:
            d = common(h, str(uuid.uuid5(ns, "place:" + "|".join(key))), "place")
            d["title"] = h["name"]
            if not is_place:  # an event's own details do not belong to its venue
                d.update(category=None, description=None, tags=[], price_label=None)
            d.update(website=h.get("website"), phone=h.get("phone"), opening_hours=h.get("opening_hours"),
                     hours_text=h.get("hours_text"), price_tiers=h.get("price_tiers") or [], open_now=None,
                     price_level=h.get("price_level"), closed=False, events=[])
            places[key] = d
        if is_place:
            continue
        place = places[key]
        d = common(h, str(uuid.uuid5(ns, f"event:{n}")), "event")
        d.update(starts_at=h.get("starts_at"), ends_at=h.get("ends_at"), duration_min=None, duration_estimated=False,
                 all_day=bool(h.get("all_day")), recurrence_text=h.get("recurrence"), tz=h.get("tz") or "America/Los_Angeles",
                 price_min=h.get("price_min"), price_max=h.get("price_max"), currency=h.get("currency") or "USD",
                 is_free=h.get("is_free"), price_text=h.get("price_text"), ticket_url=h.get("ticket_url"),
                 status=h.get("status") or "scheduled", venue_name=h["name"], occurrences=[],
                 place={"id": place["id"], "title": place["title"]})
        place["events"].append({"id": d["id"], "title": d["title"], "starts_at": d["starts_at"], "ends_at": d["ends_at"],
                                "all_day": d["all_day"], "duration_min": None, "tz": d["tz"], "dates": 1,
                                "recurrence_text": d["recurrence_text"], "price_label": d["price_label"]})
        out[d["id"]] = d
    out.update({p["id"]: p for p in places.values()})
    PREVIEW["items"] = out
    first = next((d for d in out.values() if d["type"] == "event"), next(iter(out.values()), None))
    result["preview_sel"] = f"{first['type']}:{first['id']}" if first else None


def _props(d: dict) -> dict:
    e = d["type"] == "event"
    return {
        "id": d["id"], "t": d["type"], "title": d["title"], "cat": d["category"], "start": d.get("starts_at"),
        "end": d.get("ends_at"), "all_day": d.get("all_day", False), "rec": d.get("recurrence_text"),
        "price": d["price_label"], "free": d.get("is_free"), "rs": d["review_status"], "my": None, "rating": None,
        "addr": d["address_text"], "venue": d.get("venue_name") if e else None, "dist_m": None,
        "thumb": False, "thumb_src": d["images"][0]["url"] if d["images"] else None, "tags": d["tags"],
        "place_id": d["place"]["id"] if e and d.get("place") else None,
    }


preview = FastAPI(title="Import tester: prod UI preview")


@preview.get("/api/settings")
def p_settings():
    return {"home": {"lat": HOME[0], "lon": HOME[1], "source": "tester"}, "radius_km": 400, "units": "mi",
            "tz": "America/Los_Angeles", "user": {"id": 1, "username": "tester", "display_name": "Tester"},
            "users": [{"id": 1, "username": "tester", "display_name": "Tester"}],
            "map": {"tiles": "/tiles/region.pmtiles", "assets": "/tiles/assets", "bounds": [-120.3, 32.5, -116.0, 35.8]}}


@preview.get("/api/facets")
def p_facets():
    tags: dict[str, int] = {}
    cats: dict[str, int] = {}
    for d in PREVIEW["items"].values():
        for t in d["tags"]:
            tags[t] = tags.get(t, 0) + 1
        if d["category"]:
            cats[d["category"]] = cats.get(d["category"], 0) + 1
    return {"tags": [{"tag": t, "n": n} for t, n in tags.items()], "categories": [{"cat": c, "n": n} for c, n in cats.items()]}


@preview.get("/api/map")
def p_map():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]}, "properties": _props(d)}
        for d in PREVIEW["items"].values()]}


@preview.get("/api/list")
def p_list():
    items = [{**_props(d), "lat": d["lat"], "lon": d["lon"]} for d in PREVIEW["items"].values()]
    return {"items": items, "total": len(items)}


@preview.get("/api/jobs")
def p_jobs():
    return []


@preview.get("/api/items/{kind}/{iid}")
def p_item(kind: str, iid: str):
    d = PREVIEW["items"].get(iid)
    if not d or d["type"] != kind:
        raise HTTPException(404, "no such item")
    return d


@preview.get("/service-worker.js")
def p_sw():
    return Response(status_code=404)  # no offline cache in the tester


@preview.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def p_nothing(rest: str):
    raise HTTPException(404, "the preview is read only")


PROD_URL = os.environ.get("PROD_URL", "http://192.168.0.103:8820").rstrip("/")
_PASS = ("content-type", "content-length", "content-range", "accept-ranges", "etag", "last-modified", "cache-control")
_prod = httpx.Client(timeout=30, follow_redirects=False)


@preview.api_route("/{path:path}", methods=["GET", "HEAD"])
def p_prod(path: str, request: Request):
    """The UI files and the map tiles come from the running prod app, so the preview is always the current UI.
    Falls back to frontend/build when prod cannot be reached."""
    headers = {k: v for k, v in request.headers.items() if k.lower() in ("range", "if-none-match", "if-modified-since")}
    try:
        up = _prod.send(_prod.build_request(request.method, f"{PROD_URL}/{path}", headers=headers), stream=True)
    except httpx.HTTPError:
        f = (BUILD / path).resolve()
        if path and f.is_file() and BUILD in f.parents:
            return FileResponse(f)
        if path.startswith("tiles/") or not (BUILD / "index.html").exists():
            raise HTTPException(502, f"prod app not reachable at {PROD_URL}")
        return FileResponse(BUILD / "index.html")
    out = {k: v for k, v in up.headers.items() if k.lower() in _PASS}
    return StreamingResponse(up.iter_raw(), status_code=up.status_code, headers=out, background=BackgroundTask(up.close))



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
    return {"preview": {"ok": bool(PREVIEW_PORT), "port": PREVIEW_PORT[0] if PREVIEW_PORT else None},
            "llm": llm, "browser": {"ok": browser.available(), "url": s.browser_url or None},
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
    pport = free_port(port + 1)
    PREVIEW_PORT.append(pport)
    threading.Thread(target=lambda: uvicorn.run(preview, host="127.0.0.1", port=pport, log_level="warning"), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
