"""Helpers shared by the map, list and item routes."""
from decimal import Decimal

from sqlalchemy import or_

from app.db.models import Source

CURRENCY_SYMBOL = {"USD": "$", "CAD": "$", "EUR": "€", "GBP": "£"}
MAX_PRICE_TEXT = 14

# Where an ingested source keeps a picture we can show as its thumbnail
IMAGE_PATHS = (("tiktok", "thumbnail_url"), ("page", "image"), ("image_url",))


def image_url(raw: dict | None) -> str | None:
    """First candidate image URL stored on a source."""
    for path in IMAGE_PATHS:
        v = raw or {}
        for k in path:
            v = v.get(k) if isinstance(v, dict) else None
        if isinstance(v, str) and v.startswith(("http://", "https://")):
            return v
    return None


def has_image():
    """SQL: the source has a candidate image URL (mirrors image_url)."""
    return or_(*(Source.raw[path].astext.like("http%") for path in IMAGE_PATHS))


def _money(v: float | Decimal) -> str:
    v = float(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.2f}"


def event_price_label(is_free: bool | None, price_min, price_max, price_text: str | None,
                      currency: str | None = "USD") -> str | None:
    """Short label: Free, $15, $15-30, Up to $30, or a short price_text."""
    if is_free:
        return "Free"
    sym = CURRENCY_SYMBOL.get((currency or "USD").upper())

    def fmt(s: str) -> str:
        return f"{sym}{s}" if sym else f"{s} {currency}"

    lo, hi = price_min, price_max
    if lo is not None and float(lo) == 0 and (hi is None or float(hi) == 0):
        return "Free"
    if lo is not None and hi is not None and float(hi) > float(lo):
        return fmt(f"{_money(lo)}-{_money(hi)}")
    if lo is not None:
        return fmt(_money(lo))
    if hi is not None:
        return "Up to " + fmt(_money(hi))
    text = (price_text or "").strip()
    return text if text and len(text) <= MAX_PRICE_TEXT else None


def place_price_label(price_level: int | None) -> str | None:
    if price_level is None:
        return None
    return "Free" if price_level == 0 else "$" * price_level
