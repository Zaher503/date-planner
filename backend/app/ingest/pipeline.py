"""The ingest job: one shared link or text -> pinned places and events.

Fast path only (no video download): TikTok page data and auto-captions, maps links,
JSON-LD on web pages, the local model for free text. Items that cannot be placed
confidently are still pinned but marked for review with alternatives.
"""
import logging
import re
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app import jobs
from app.db.models import Job, Source
from app.gpu import gpu_lock
from app.ingest import maps_links, store
from app.ingest.event_page import parse_page
from app.ingest.items import ItemHint
from app.ingest.tiktok import fetch_post
from app.llm import extract as llm
from app.net import BlockedURL, fetch_text
from app.resolve.resolver import resolve
from app.resolve.scorer import name_similarity

log = logging.getLogger(__name__)
# A pin on a whole city or county tells you nothing; neighborhoods (Venice) are fine
TOO_BIG = {"city", "town", "county", "state", "country", "region", "province", "municipality"}


class Unprocessable(Exception):
    """The link can never work (removed video, blocked page). No retry."""
    permanent = True


def _json_safe(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in d.items()}


def _llm(db: Session, job: Job, fn, *args, **kwargs):
    with gpu_lock(lambda s: jobs.set_stage(db, job, s, 30)):
        jobs.set_stage(db, job, "reading with the local model", 35)
        return fn(*args, **kwargs)


def _from_tiktok(db: Session, job: Job, src: Source) -> list[ItemHint]:
    try:
        post = fetch_post(src.url)
    except ValueError as e:
        raise Unprocessable(str(e)) from e
    first_line = post.caption.strip().splitlines()[0] if post.caption.strip() else ""
    src.title = (first_line or f"TikTok by @{post.author}")[:140]
    src.caption, src.transcript = post.caption, post.transcript or None
    src.raw = {**(src.raw or {}), "tiktok": _json_safe({k: v for k, v in asdict(post).items() if k != "transcript"})}
    db.commit()
    is_list, hints = _llm(db, job, llm.extract, post.as_text(),
                          posted=post.posted_at.date() if post.posted_at else None)
    handles = [post.author or "", *post.mentions]
    for h in hints:
        h.name = readable_handle(h.name, handles)
    if post.poi:
        # The location tag fills in an address; on its own it is often just a neighborhood
        same = next((h for h in hints if name_similarity(h.name, post.poi["name"]) >= 0.7), None)
        if same:
            same.address = same.address or post.poi.get("address")
        elif not hints:
            hints = [ItemHint(kind="place", name=post.poi["name"], address=post.poi.get("address"),
                              area=post.poi.get("city"), provider="tiktok_poi")]
    return prune(hints, is_list)


def _from_maps(src: Source) -> list[ItemHint]:
    final, hint = maps_links.expand_and_parse(src.url)
    src.raw = {**(src.raw or {}), "maps_url": final}
    if not hint.usable:
        raise Unprocessable("this maps link has no place name, address or coordinates")
    item = ItemHint(kind="place", name=hint.name or "", address=hint.address, lat=hint.lat, lon=hint.lon,
                    exact_pin=hint.exact_pin, provider="maps_link")
    if not item.name:
        item.name = hint.address or "Pinned spot"
        item.flags.append("not a specific venue")
    src.title = item.name
    return [item]


def _from_page(db: Session, job: Job, src: Source) -> list[ItemHint]:
    try:
        final, html = fetch_text(src.url)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403, 404, 410, 451):
            raise Unprocessable(f"the site refused the page (HTTP {e.response.status_code})") from e
        raise
    page = parse_page(final, html)
    src.title = (page.title or final)[:140]
    src.raw = {**(src.raw or {}), "page": {"url": final, "title": page.title, "description": page.description,
                                           "image": page.image, "jsonld_items": len(page.items)}}
    db.commit()
    context = "\n".join(x for x in (page.title, page.description) if x)
    if page.items:
        _llm(db, job, llm.classify, page.items, context)
        return page.items
    text = "\n\n".join(x for x in (f"Page title: {page.title}" if page.title else None,
                                   page.description, page.text[:6000]) if x)
    if len(text) < 40:
        raise Unprocessable("the page had no readable text (it may need a browser)")
    is_list, hints = _llm(db, job, llm.extract, text)
    return prune(hints, is_list)


def _from_text(db: Session, job: Job, src: Source) -> list[ItemHint]:
    src.title = (src.caption or "").strip().splitlines()[0][:140] if src.caption else "Note"
    is_list, hints = _llm(db, job, llm.extract, src.caption or "")
    return prune(hints, is_list)


def too_vague(res) -> bool:
    return res.best is not None and res.best.kind == "area" and (res.best.osm_value or "") in TOO_BIG


def readable_handle(name: str, handles: list[str]) -> str:
    """'nightmarket_elgato' (an account handle used as a name) -> 'Nightmarket Elgato'."""
    flat = re.sub(r"[^a-z0-9]", "", name.lower())
    if flat and any(flat == re.sub(r"[^a-z0-9]", "", h.lower()) for h in handles if h) and " " not in name.strip():
        return " ".join(w.capitalize() for w in re.split(r"[_.]+", name.strip().lstrip("@")) if w)
    return name


def prune(hints: list[ItemHint], is_list: bool) -> list[ItemHint]:
    """In a post about one place, drop vague extras (a neighborhood mentioned in passing)."""
    specific = [h for h in hints if "not a specific venue" not in h.flags]
    return specific if specific and not is_list else hints


def tidy(h: ItemHint, now: datetime) -> ItemHint:
    """Turn dateless 'events' into places and long-running series into recurring events."""
    if h.kind == "event" and h.starts_at and h.ends_at and h.ends_at - h.starts_at > timedelta(days=3) \
            and h.starts_at < now:
        h.recurrence = h.recurrence or f"ongoing until {h.ends_at.date().isoformat()}"
        h.starts_at = h.ends_at = None
        h.flags.append("recurring series, dates unclear")
    if h.kind == "event" and not h.starts_at and not h.recurrence:
        h.kind = "place"
        h.flags = [f for f in h.flags if f != "event with no date"]
    if not h.name and h.event_title:
        h.name = h.event_title
        h.flags.append("not a specific venue")
    return h


def run(db: Session, job: Job) -> dict:
    src = db.get(Source, uuid.UUID(job.payload["source_id"]))
    if src is None:
        return {"skipped": "source deleted"}
    jobs.set_stage(db, job, "reading the link", 10)
    try:
        if src.kind == "tiktok":
            hints = _from_tiktok(db, job, src)
        elif src.kind in ("gmaps", "applemaps"):
            hints = _from_maps(src)
            _llm(db, job, llm.classify, hints, src.title or "")
        elif src.kind in ("event_page", "youtube"):
            hints = _from_page(db, job, src)
        elif src.kind == "text":
            hints = _from_text(db, job, src)
        else:
            raise Unprocessable(f"{src.kind} links are not supported yet")
    except (Unprocessable, BlockedURL) as e:
        src.status, src.error = "failed", str(e)
        db.commit()
        raise Unprocessable(str(e)) from e

    now = datetime.now(timezone.utc)
    hints = [tidy(h, now) for h in hints if h.name or h.event_title]
    src.fetched_at = now
    if not hints:
        src.status, src.error = "failed", "no place or event found in this link"
        db.commit()
        return {"items": [], "error": src.error}

    home = store.home_point(db)
    results = []
    for i, hint in enumerate(hints):
        jobs.set_stage(db, job, f"finding place {i + 1} of {len(hints)}", 50 + int(45 * i / len(hints)))
        res = resolve(db, hint, home)
        if res.best is None:
            results.append({"name": hint.name, "error": "not found"})
            continue
        if too_vague(res):
            results.append({"name": hint.event_title or hint.name, "error": "too vague to pin (only a city)"})
            continue
        place, place_new = store.upsert_place(db, hint, res, src.submitted_by)
        store.save_candidates(db, src, place, i, res)
        row = {"type": "place", "id": str(place.id), "name": place.name, "new": place_new,
               "confidence": res.confidence, "review": place.review_status == "needs_review",
               "method": res.method, "flags": hint.flags}
        if hint.kind == "event":
            event, event_new = store.upsert_event(db, hint, place, res, src.submitted_by)
            store.link(db, src, event=event, position=i, confidence=res.confidence)
            row.update(type="event", id=str(event.id), event_title=event.title, new=event_new,
                       review=event.review_status == "needs_review")
        store.link(db, src, place=place, position=i, confidence=res.confidence)
        db.commit()
        results.append(row)

    placed = [r for r in results if "id" in r]
    src.status = "done" if placed else "failed"
    src.error = None if placed else "could not find any of the places on the map"
    src.raw = {**(src.raw or {}), "hints": [_json_safe({k: v for k, v in asdict(h).items()
                                                        if v not in (None, [], False, "")}) for h in hints]}
    db.commit()
    return {"items": results, "placed": len(placed), "review": sum(1 for r in placed if r["review"])}
