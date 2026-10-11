"""TikTok fast path: everything useful without downloading the video.

From the public video page's rehydration JSON we get the caption, on-screen text
stickers (list videos put every item there), the place tag (POI), @mentions,
hashtags, TikTok's suggested search words and, often, TikTok's own auto-caption
transcript (WebVTT). oEmbed adds the thumbnail.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app.ingest.timing import vtt_cues
from app.net import fetch_text, public_client

REHYDRATION = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', re.S)
# A POI tag at these levels only says "Los Angeles", which does not help
VAGUE_POI = {"city", "state", "province", "country", "region", "county", "district", "continent"}
MENTION = re.compile(r"(?<![\w.])@([A-Za-z0-9_.]{2,30})")


@dataclass
class TikTokPost:
    url: str
    video_id: str | None = None
    author: str | None = None
    caption: str = ""
    stickers: list[str] = field(default_factory=list)
    transcript: str = ""
    poi: dict | None = None  # {name, address, city, category}, only when specific
    mentions: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    suggested: list[str] = field(default_factory=list)
    posted_at: datetime | None = None
    duration_s: int | None = None
    thumbnail_url: str | None = None
    caption_url: str | None = None
    cues: list = field(default_factory=list)  # (start seconds, text) from the captions

    def as_text(self) -> str:
        """Everything the extractor should read, labelled."""
        parts = [f"Caption: {self.caption.strip()}"]
        if self.stickers:
            parts.append("On-screen text:\n" + "\n".join(self.stickers))
        if self.poi:
            parts.append("Location tag: " + ", ".join(v for v in (self.poi.get("name"), self.poi.get("address")) if v))
        if self.mentions:
            parts.append("Mentioned accounts: " + ", ".join("@" + m for m in self.mentions))
        if self.suggested:
            parts.append("TikTok search suggestions: " + "; ".join(self.suggested))
        if self.transcript:
            parts.append("Spoken (auto-captions):\n" + self.transcript)
        return "\n\n".join(parts)


def parse_item(html: str) -> dict:
    m = REHYDRATION.search(html)
    if not m:
        raise ValueError("TikTok page had no video data (blocked, private or removed)")
    detail = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
    item = (detail.get("itemInfo") or {}).get("itemStruct")
    if not item:
        raise ValueError(f"TikTok video unavailable ({detail.get('statusMsg') or detail.get('statusCode')})")
    return item


def _clean(s: str) -> str:
    return re.sub(r"[ \t ]+", " ", s).strip()


def stickers_of(item: dict) -> list[str]:
    out: list[str] = []
    for st in item.get("stickersOnItem") or []:
        for t in st.get("stickerText") or []:
            t = "\n".join(_clean(line) for line in str(t).splitlines() if _clean(line))
            if t and t not in out:
                out.append(t)
    return out


def poi_of(item: dict) -> dict | None:
    p = item.get("poi") or {}
    level = (p.get("ttTypeNameTiny") or "").lower()
    if not p.get("name") or level in VAGUE_POI:
        return None
    return {"name": p.get("name"), "address": p.get("address") or None, "city": p.get("city") or None,
            "category": p.get("ttTypeNameMedium") or p.get("category"), "id": p.get("id")}


def caption_url_of(item: dict) -> str | None:
    video = item.get("video") or {}
    caps = (video.get("claInfo") or {}).get("captionInfos") or []
    subs = video.get("subtitleInfos") or []
    eng = [c.get("url") for c in caps if str(c.get("language", "")).startswith("en")]
    eng += [s.get("Url") for s in subs if str(s.get("LanguageCodeName", "")).startswith("en")]
    return next((u for u in eng if u), None)


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit() or line.startswith("NOTE"):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if not lines or lines[-1] != line:
            lines.append(line)
    return " ".join(lines)


def build_post(url: str, item: dict, oembed: dict | None = None) -> TikTokPost:
    caption = item.get("desc") or (oembed or {}).get("title") or ""
    mentions = [t.get("userUniqueId") for t in item.get("textExtra") or [] if t.get("userUniqueId")]
    mentions += MENTION.findall(caption)
    hashtags = [t["hashtagName"] for t in item.get("textExtra") or [] if t.get("hashtagName")]
    created = item.get("createTime")
    author = (item.get("author") or {}).get("uniqueId") or (oembed or {}).get("author_unique_id")
    return TikTokPost(
        url=url,
        video_id=str(item.get("id")) if item.get("id") else None,
        author=author,
        caption=caption,
        stickers=stickers_of(item),
        poi=poi_of(item),
        mentions=list(dict.fromkeys(m for m in mentions if m and m != author)),
        hashtags=list(dict.fromkeys(hashtags)),
        suggested=list(dict.fromkeys(item.get("suggestedWords") or []))[:10],
        posted_at=datetime.fromtimestamp(int(created), timezone.utc) if created else None,
        duration_s=(item.get("video") or {}).get("duration"),
        thumbnail_url=(oembed or {}).get("thumbnail_url"),
        caption_url=caption_url_of(item),
    )


def fetch_post(url: str) -> TikTokPost:
    """Network: short-link redirect, page JSON, oEmbed (best effort), auto-captions (best effort)."""
    with public_client(timeout=20) as client:
        final_url, html = fetch_text(url, client)
        canonical = final_url.split("?")[0]
        item = parse_item(html)
        oembed = None
        try:
            r = client.get("https://www.tiktok.com/oembed", params={"url": canonical})
            if r.status_code == 200:
                oembed = r.json()
        except (httpx.HTTPError, ValueError):
            pass
        post = build_post(canonical, item, oembed)
        if post.caption_url:
            try:
                r = client.get(post.caption_url)
                if r.status_code == 200:
                    post.transcript = vtt_to_text(r.text)[:6000]
                    post.cues = vtt_cues(r.text)
            except httpx.HTTPError:
                pass
    return post
