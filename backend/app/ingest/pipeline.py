"""The ingest job: one shared link, text or screenshot -> pinned places and events.

Fast path (no video download): TikTok page data and auto-captions, YouTube metadata and
subtitles, maps links, JSON-LD on web pages, the local model for free text and screenshots.
Slow path, only for videos the fast path could not place confidently: download, Whisper
(when there are no captions), on-screen text from frames, then extract and resolve again.
Items that still cannot be placed confidently are pinned but marked for review.
"""
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app import browser, jobs
from app.db.models import Job, Source
from app.ingest import maps_links, media, ocr, store
from app.ingest.event_page import parse_page
from app.ingest.items import ItemHint
from app.llm.ollama import describe, waiting
from app.ingest import images, page_images, pricing
from app.ingest.timing import vtt_cues
from app.ingest.tiktok import TikTokPost, fetch_post, vtt_to_text
from app.llm import extract as llm
from app.net import BlockedURL, fetch_text
from app.resolve.resolver import resolve
from app.resolve.scorer import name_similarity

log = logging.getLogger(__name__)
# A pin on a whole city or county tells you nothing; neighborhoods (Venice) are fine
TOO_BIG = {"city", "town", "county", "state", "country", "region", "province", "municipality"}
VIDEO_KINDS = {"tiktok", "youtube"}


@dataclass
class Gathered:
    """What the fast path read, kept so the slow path can extract again with more text."""
    hints: list[ItemHint]
    text: str = ""
    posted: date | None = None
    post: TikTokPost | None = None
    info: dict = field(default_factory=dict)


class Unprocessable(Exception):
    """The link can never work (removed video, blocked page). No retry."""
    permanent = True


def _json_safe(d: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, (datetime, date)) else v) for k, v in d.items()}


def _in_line(db: Session, job: Job, pct: int):
    """While the AI hub makes this job wait, show where it is in line."""
    return waiting(lambda est: jobs.set_stage(db, job, describe(est), pct))


def _llm(db: Session, job: Job, fn, *args, **kwargs):
    with _in_line(db, job, 30):
        jobs.set_stage(db, job, "reading with the local model", 35)
        return fn(*args, **kwargs)


def _tiktok_hints(db: Session, job: Job, post: TikTokPost, text: str) -> list[ItemHint]:
    is_list, hints = _llm(db, job, llm.extract, text, posted=post.posted_at.date() if post.posted_at else None)
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


def _from_tiktok(db: Session, job: Job, src: Source) -> Gathered:
    try:
        post = fetch_post(src.url)
    except ValueError as e:
        raise Unprocessable(str(e)) from e
    first_line = post.caption.strip().splitlines()[0] if post.caption.strip() else ""
    src.title = (first_line or f"TikTok by @{post.author}")[:140]
    src.caption, src.transcript = post.caption, post.transcript or None
    src.raw = {**(src.raw or {}), "tiktok": _json_safe({k: v for k, v in asdict(post).items()
                                                        if k not in ("transcript", "cues")}),
               "cues": [[t, x] for t, x in post.cues]}
    db.commit()
    text = post.as_text()
    return Gathered(hints=_tiktok_hints(db, job, post, text), text=text, post=post,
                    posted=post.posted_at.date() if post.posted_at else None)


def youtube_text(info: dict, transcript: str) -> str:
    parts = [f"Title: {info.get('title') or ''}".strip()]
    if info.get("description"):
        parts.append(f"Description: {info['description'][:3000]}")
    if info.get("uploader"):
        parts.append(f"Channel: {info['uploader']}")
    if transcript:
        parts.append("Spoken (captions):\n" + transcript)
    return "\n\n".join(parts)


def _from_youtube(db: Session, job: Job, src: Source) -> Gathered:
    try:
        info = media.probe(src.url)
    except media.MediaError as e:
        raise Unprocessable(str(e)) from e
    subs = media.subtitles(src.url, media.media_dir(src.id) / "subs")
    vtt = subs.read_text(encoding="utf-8", errors="replace") if subs else ""
    transcript = vtt_to_text(vtt)[:6000] if vtt else ""
    src.title = (info.get("title") or "YouTube video")[:140]
    src.caption, src.transcript = info.get("description") or None, transcript or None
    src.raw = {**(src.raw or {}), "youtube": {k: info.get(k) for k in
                                              ("id", "uploader", "duration", "thumbnail", "upload_date", "webpage_url")},
               "cues": [[t, x] for t, x in vtt_cues(vtt)]}
    db.commit()
    posted = None
    if info.get("upload_date"):
        try:
            posted = datetime.strptime(info["upload_date"], "%Y%m%d").date()
        except ValueError:
            pass
    text = youtube_text(info, transcript)
    is_list, hints = _llm(db, job, llm.extract, text, posted=posted)
    return Gathered(hints=prune(hints, is_list), text=text, posted=posted, info=info)


def _from_image(db: Session, job: Job, src: Source) -> Gathered:
    rel = (src.raw or {}).get("image")
    path = media.media_root() / rel if rel else None
    if path is None or not path.exists():
        raise Unprocessable("the screenshot file is missing")
    with _in_line(db, job, 20):
        jobs.set_stage(db, job, "reading the screenshot", 25)
        text = ocr.read_screenshot(path)
        src.ocr_text = text or None
        src.title = (text.strip().splitlines()[0] if text.strip() else "Screenshot")[:140]
        db.commit()
        if len(text) < 4:
            raise Unprocessable("no readable text in the screenshot")
        jobs.set_stage(db, job, "reading with the local model", 40)
        is_list, hints = llm.extract(f"Text read from a screenshot:\n{text}")
    return Gathered(hints=prune(hints, is_list), text=text)


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
            code = e.response.status_code
            why = "blocks automated readers" if code in (401, 403) else "has no page there" if code in (404, 410) else "refused the page"
            raise Unprocessable(f"the site {why} (HTTP {code})") from e
        raise
    page = parse_page(final, html)
    src.title = (page.title or final)[:140]
    src.raw = {**(src.raw or {}), "page": {"url": final, "title": page.title, "description": page.description,
                                           "image": page.image, "jsonld_items": len(page.items)}}
    db.commit()
    context = "\n".join(x for x in (page.title, page.description) if x)
    if page.items:
        _llm(db, job, llm.classify, page.items, context)
        if len(page.items) > 1:
            page_images.attach(page.items, html, final)
        return page.items
    text = "\n\n".join(x for x in (f"Page title: {page.title}" if page.title else None,
                                   page.description, page.text[:6000]) if x)
    if len(text) < 40 and browser.available():
        # Pages built by JavaScript have no text until a browser runs them
        try:
            final, html = browser.render(final)
            page = parse_page(final, html)
            if page.items:
                _llm(db, job, llm.classify, page.items, context)
                return page.items
            text = "\n\n".join(x for x in (f"Page title: {page.title}" if page.title else None,
                                           page.description, page.text[:6000]) if x)
        except Exception as e:
            log.info("browser render of %s failed: %s", final, e)
    if len(text) < 40:
        raise Unprocessable("the page had no readable text (it may need a browser)")
    is_list, hints = _llm(db, job, llm.extract, text)
    hints = prune(hints, is_list)
    page_images.attach(hints, html, final)
    return hints


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


def weak(resolved: list) -> bool:
    """True when nothing was placed confidently (so the video is worth the slow path)."""
    return not any(r.best is not None and not r.needs_review and not too_vague(r) for _, r in resolved)


def strength(resolved: list) -> tuple[int, float]:
    good = [r for _, r in resolved if r.best is not None and not too_vague(r)]
    return sum(1 for r in good if not r.needs_review), sum(r.confidence for r in good)


def _resolve_all(db: Session, job: Job, hints: list[ItemHint], home, pct: tuple[int, int]) -> list:
    out = []
    lo, hi = pct
    for i, hint in enumerate(hints):
        jobs.set_stage(db, job, f"finding place {i + 1} of {len(hints)}", lo + int((hi - lo) * i / len(hints)))
        out.append((hint, resolve(db, hint, home)))
    return out


def slow_text(db: Session, job: Job, src: Source, g: Gathered) -> str:
    """Download the video, transcribe it when there were no captions, read on-screen text.
    Returns the extra text (empty when nothing new was found). The video stays archived."""
    jobs.set_stage(db, job, "downloading the video", 55)
    video = media.has_video(db, src)
    if video is None:
        try:
            dl = media.download(src.url, src.id, info=g.info or None)
        except media.MediaError as e:
            log.info("slow path skipped for %s: %s", src.id, e)
            return ""
        media.archive(db, src, dl)
        db.commit()
        video = dl.video
    extra: list[str] = []
    with _in_line(db, job, 58):
        if not src.transcript:
            jobs.set_stage(db, job, "transcribing", 60)
            try:
                from app.ingest.transcribe import transcribe
                said, cues = transcribe(video)
            except Exception as e:  # missing CUDA, broken audio: carry on with the frames
                log.warning("whisper failed for %s: %s", src.id, e)
                said, cues = "", []
            if said:
                src.transcript = said
                src.raw = {**(src.raw or {}), "cues": [[round(t, 2), x] for t, x in cues]}
                extra.append("Spoken (transcribed):\n" + said)
        jobs.set_stage(db, job, "reading on-screen text", 70)
        try:
            frames = ocr.extract_frames(video, Path(video).parent / "frames")
        except Exception as e:
            log.warning("frames failed for %s: %s", src.id, e)
            frames = []
        seen = ocr.read_frames(frames, progress=lambda i, n: jobs.set_stage(
            db, job, f"reading on-screen text ({i + 1} of {n})", 70 + int(12 * i / max(n, 1))))
        if seen:
            src.ocr_text = seen
            extra.append("Text seen in the video:\n" + seen)
    db.commit()
    return "\n\n".join(extra)


def _extract_again(db: Session, job: Job, g: Gathered, extra: str) -> list[ItemHint]:
    text = f"{g.text}\n\n{extra}"
    jobs.set_stage(db, job, "reading everything again", 84)
    if g.post is not None:
        return _tiktok_hints(db, job, g.post, text)
    is_list, hints = _llm(db, job, llm.extract, text, posted=g.posted)
    return prune(hints, is_list)


def run(db: Session, job: Job) -> dict:
    src = db.get(Source, uuid.UUID(job.payload["source_id"]))
    if src is None:
        return {"skipped": "source deleted"}
    jobs.set_stage(db, job, "reading the link", 10)
    try:
        if src.kind == "tiktok":
            g = _from_tiktok(db, job, src)
        elif src.kind == "youtube":
            g = _from_youtube(db, job, src)
        elif src.kind in ("gmaps", "applemaps"):
            hints = _from_maps(src)
            _llm(db, job, llm.classify, hints, src.title or "")
            g = Gathered(hints=hints)
        elif src.kind == "event_page":
            g = Gathered(hints=_from_page(db, job, src))
        elif src.kind == "text":
            g = Gathered(hints=_from_text(db, job, src))
        elif src.kind == "image":
            g = _from_image(db, job, src)
        else:
            raise Unprocessable(f"{src.kind} links are not supported yet")
    except (Unprocessable, BlockedURL) as e:
        src.status, src.error = "failed", str(e)
        db.commit()
        raise Unprocessable(str(e)) from e

    now = datetime.now(timezone.utc)
    hints = [tidy(h, now) for h in g.hints if h.name or h.event_title]
    src.fetched_at = now
    if any(h.kind == "event" and not pricing.has_price(h) for h in hints):
        jobs.set_stage(db, job, "checking ticket prices", 44)
        try:
            with _in_line(db, job, 44):
                pricing.enrich(hints, src.url if src.kind == "event_page" else None)
        except Exception as e:  # a price is a nicety; the item is saved without it
            log.warning("price check failed for %s: %s", src.id, e)
    home = store.home_point(db)
    resolved = _resolve_all(db, job, hints, home, (45, 55))
    slow = False

    if src.kind in VIDEO_KINDS and src.url and weak(resolved) and not job.payload.get("fast_only"):
        extra = slow_text(db, job, src, g)
        if extra:
            slow = True
            again = [tidy(h, now) for h in _extract_again(db, job, g, extra) if h.name or h.event_title]
            if again:
                second = _resolve_all(db, job, again, home, (86, 92))
                if strength(second) >= strength(resolved):
                    hints, resolved = again, second

    if not hints:
        src.status, src.error = "failed", "no place or event found in this link"
        db.commit()
        return {"items": [], "error": src.error, "slow_path": slow}

    results = []
    for i, (hint, res) in enumerate(resolved):
        jobs.set_stage(db, job, "saving", 93 + int(6 * i / len(resolved)))
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
            images.page_images(db, src, hint, place=place, event=event, multi=len(resolved) > 1)
            row.update(type="event", id=str(event.id), event_title=event.title, new=event_new,
                       review=event.review_status == "needs_review")
        store.link(db, src, place=place, position=i, confidence=res.confidence)
        if hint.kind != "event":
            images.page_images(db, src, hint, place=place, event=None, multi=len(resolved) > 1)
        db.commit()
        results.append(row)

    placed = [r for r in results if "id" in r]
    src.status = "done" if placed else "failed"
    src.error = None if placed else "could not find any of the places on the map"
    src.raw = {**(src.raw or {}), "slow_path": slow,
               "hints": [_json_safe({k: v for k, v in asdict(h).items() if v not in (None, [], False, "")})
                         for h in hints]}
    db.commit()
    video = media.has_video(db, src) if placed and src.kind in VIDEO_KINDS else None
    if video:
        try:
            images.video_images(db, src, video)
        except Exception as e:  # pictures are a nicety; the items are already saved
            log.warning("frame pictures failed for %s: %s", src.id, e)
    # Keep a copy of the video even when the fast path was enough
    if placed and src.kind in VIDEO_KINDS and media.has_video(db, src) is None:
        jobs.enqueue(db, "archive", {"source_id": str(src.id)}, source_id=src.id, submitted_by=src.submitted_by)
        db.commit()
    return {"items": results, "placed": len(placed), "review": sum(1 for r in placed if r["review"]),
            "slow_path": slow}
