"""What an extractor found, before it is resolved to a real place on the map."""
from dataclasses import dataclass, field
from datetime import datetime

CATEGORIES = (
    "restaurant", "bar", "cafe", "dessert", "nightlife", "live_music", "arts", "museum",
    "outdoors", "beach", "park", "hike", "viewpoint", "market", "shopping", "activity",
    "class", "show", "comedy", "sports", "festival", "spa", "other",
)


@dataclass
class ItemHint:
    kind: str  # place or event
    name: str  # the place, or the venue of an event
    event_title: str | None = None
    address: str | None = None
    area: str | None = None  # neighborhood or city as stated
    inside: str | None = None  # host venue (a bar inside a hotel)
    lat: float | None = None
    lon: float | None = None
    exact_pin: bool = False
    category: str | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool = False
    tz: str | None = None
    recurrence: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    is_free: bool | None = None
    price_text: str | None = None
    ticket_url: str | None = None
    website: str | None = None
    phone: str | None = None
    opening_hours: str | None = None  # OSM syntax
    price_level: int | None = None
    tags: list[str] = field(default_factory=list)
    image_url: str | None = None
    images: list[str] = field(default_factory=list)  # photos next to this listing on its page
    provider: str = "llm"  # jsonld, llm, maps_link, tiktok_poi
    status: str = "scheduled"
    flags: list[str] = field(default_factory=list)  # reasons to review
