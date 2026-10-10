"""Discovery adapter interface. Each free event source is one Adapter subclass."""
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

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

    def get(self, url: str, **params) -> httpx.Response:
        """Rate-limited GET that counts calls against the quota."""
        if self.daily_quota is not None and self.calls >= self.daily_quota:
            raise RuntimeError(f"{self.name}: daily quota reached")
        wait = self.min_interval_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.calls += 1
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r

    @abstractmethod
    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        """Yield events whose start falls in [start, end) within the area."""
