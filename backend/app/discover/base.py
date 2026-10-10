"""Discovery adapter interface. Each free event source is one Adapter subclass."""
import math
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx

USER_AGENT = "DatePlanner/0.1 (personal, non-commercial; +https://dates.zkocr.com)"


@dataclass
class Area:
    lat: float
    lon: float
    radius_km: float


@dataclass
class RawEvent:
    """One event as a source reports it, before geocoding, dedup and scoring."""
    adapter: str
    external_id: str
    title: str
    url: str | None = None
    starts_at: datetime | None = None  # timezone-aware
    ends_at: datetime | None = None
    all_day: bool = False
    tz: str | None = None
    status: str = "scheduled"  # scheduled, cancelled
    venue_name: str | None = None
    address_text: str | None = None
    lat: float | None = None
    lon: float | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    is_free: bool | None = None
    price_text: str | None = None
    description: str | None = None
    image_url: str | None = None
    categories: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class Adapter(ABC):
    name: str
    # Settings attribute holding the API key, or None when the source needs no key
    key_setting: str | None = None
    min_interval_s: float = 1.0  # between requests
    daily_quota: int | None = None

    def __init__(self, client: httpx.Client | None = None, key: str | None = None):
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT},
                                             follow_redirects=True)
        self.key = key
        self.calls = 0
        self._last = 0.0

    def enabled(self) -> bool:
        return self.key_setting is None or bool(self.key)

    def _throttle(self) -> None:
        if self.daily_quota is not None and self.calls >= self.daily_quota:
            raise RuntimeError(f"{self.name}: daily quota reached")
        wait = self.min_interval_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.calls += 1

    def get(self, url: str, **params) -> httpx.Response:
        """Rate-limited GET that counts calls against the quota."""
        self._throttle()
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r

    def post(self, url: str, json: dict | list | None = None, headers: dict | None = None) -> httpx.Response:
        """Rate-limited POST with a JSON body, counted like get()."""
        self._throttle()
        r = self.client.post(url, json=json, headers=headers)
        r.raise_for_status()
        return r

    @abstractmethod
    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        """Yield events whose start falls in [start, end) within the area."""


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def in_area(area: Area, lat: float | None, lon: float | None) -> bool:
    """True when the point is inside the area, or unknown (kept for geocoding later)."""
    if lat is None or lon is None:
        return True
    return distance_km(area.lat, area.lon, lat, lon) <= area.radius_km


def in_window(e: RawEvent, start: datetime, end: datetime) -> bool:
    """Start falls in [start, end). All-day events count while their day overlaps the window."""
    if e.starts_at is None:
        return False
    if e.all_day:
        return e.starts_at + timedelta(days=1) > start and e.starts_at < end
    return start <= e.starts_at < end


PRICE_NUM = re.compile(r"\d+(?:\.\d{1,2})?")


def parse_price(text: str | None) -> tuple[float | None, float | None, bool | None]:
    """Free-text price ("$25-45", "Free", "15 / 20") -> (min, max, is_free).

    A bare "0" is treated as unknown: sources use it for "not filled in".
    """
    if not text:
        return None, None, None
    t = text.lower()
    nums = [float(n) for n in PRICE_NUM.findall(t.replace(",", ""))]
    if "free" in t and not any(nums):
        return 0.0, 0.0, True
    if not nums or not any(nums):
        return None, None, None
    return min(nums), max(nums), False
