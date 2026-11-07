"""Discovery settings: the iCal / RSS feed list (API only, no Settings screen yet)."""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.db.models import AdapterState, User
from app.db.session import get_db

router = APIRouter()

ADAPTER = "ical_feeds"
MAX_FEEDS = 30


class FeedIn(BaseModel):
    url: str = Field(max_length=2000)
    name: str | None = Field(default=None, max_length=80)
    default_category: str | None = Field(default=None, max_length=40)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        parts = urlsplit(v)
        if parts.scheme.lower() not in ("http", "https", "webcal") or not parts.netloc:
            raise ValueError("feed url must be http, https or webcal")
        return v

    @field_validator("name", "default_category")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class FeedsIn(BaseModel):
    feeds: list[FeedIn] = Field(max_length=MAX_FEEDS)


def _out(row: AdapterState | None) -> dict:
    cfg = (row.config if row else None) or {}
    return {
        "feeds": cfg.get("feeds", []),
        "enabled": row.enabled if row else True,
        "last_ok_at": row.last_ok_at if row else None,
        "last_error": row.last_error if row else None,
    }


@router.get("/api/discover/feeds")
def get_feeds(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return _out(db.get(AdapterState, ADAPTER))


@router.put("/api/discover/feeds")
def put_feeds(body: FeedsIn, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Replace the whole feed list; the same url twice keeps the first entry."""
    seen: set[str] = set()
    feeds = []
    for f in body.feeds:
        if f.url.lower() in seen:
            continue
        seen.add(f.url.lower())
        feeds.append(f.model_dump())
    row = db.get(AdapterState, ADAPTER)
    if row is None:
        row = AdapterState(adapter=ADAPTER, enabled=True, config={"feeds": feeds})
        db.add(row)
    else:
        row.config = {**(row.config or {}), "feeds": feeds}
    db.commit()
    return _out(row)
