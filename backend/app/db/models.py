"""Database schema. Postgres 17 with PostGIS, pgvector and pg_trgm.

All times are timestamptz (stored UTC). Distances are in metres in the database.
"""
import uuid
from datetime import date, datetime, time

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Computed, Date, DateTime, Float, ForeignKey, Identity,
    Index, Integer, LargeBinary, Numeric, SmallInteger, String, Text, Time, UniqueConstraint, func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBED_DIM = 768

# Allowed values, enforced with CHECK constraints
ORIGINS = ("manual", "discovered")
REVIEW = ("ok", "needs_review", "suggested", "dismissed")
EVENT_STATUS = ("scheduled", "cancelled", "archived")
MY_STATUS = ("want", "going", "been", "dismissed")
JOB_STATUS = ("queued", "running", "done", "failed", "cancelled")
SOURCE_STATUS = ("pending", "done", "failed", "stub")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSettings(Base):
    """Single row (id = 1)."""
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    home = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    home_source: Mapped[str] = mapped_column(Text, server_default="ha")
    radius_km: Mapped[float] = mapped_column(Float, server_default="40")
    units: Mapped[str] = mapped_column(Text, server_default="mi")
    suggest_threshold: Mapped[float] = mapped_column(Float, server_default="0.6")
    notify_threshold: Mapped[float] = mapped_column(Float, server_default="0.85")
    discovery_every_days: Mapped[int] = mapped_column(Integer, server_default="3")
    notify_targets: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    cal_token: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Place(TimestampMixin, Base):
    __tablename__ = "places"
    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_places_osm"),
        CheckConstraint("price_level BETWEEN 0 AND 4", name="price_level_range"),
        CheckConstraint(_in("origin", ORIGINS), name="origin_valid"),
        CheckConstraint(_in("review_status", REVIEW), name="review_valid"),
        Index("ix_places_tags", "tags", postgresql_using="gin"),
        Index("ix_places_search", "search", postgresql_using="gin"),
        Index("ix_places_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_places_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_places_review", "review_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geography("POINT", srid=4326), nullable=False)
    address: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    address_text: Mapped[str | None] = mapped_column(Text)
    osm_type: Mapped[str | None] = mapped_column(String(1))
    osm_id: Mapped[int | None] = mapped_column(BigInteger)
    website: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[str | None] = mapped_column(Text)  # OSM opening_hours syntax
    hours_text: Mapped[str | None] = mapped_column(Text)  # hours as the venue words them
    price_level: Mapped[int | None] = mapped_column(SmallInteger)
    price_text: Mapped[str | None] = mapped_column(Text)
    price_tiers: Mapped[list[dict]] = mapped_column(JSONB, server_default="[]")  # [{label, price, note}]
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    embedding = mapped_column(Vector(EMBED_DIM))
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    review_status: Mapped[str] = mapped_column(Text, server_default="ok")
    confidence: Mapped[float | None] = mapped_column(Float)
    closed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_overrides: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    search = mapped_column(TSVECTOR, Computed(
        "to_tsvector('english'::regconfig, coalesce(name, '') || ' ' || coalesce(category, '') "
        "|| ' ' || coalesce(description, '') || ' ' || coalesce(address_text, ''))",
        persisted=True))


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(_in("origin", ORIGINS), name="origin_valid"),
        CheckConstraint(_in("review_status", REVIEW), name="review_valid"),
        CheckConstraint(_in("status", EVENT_STATUS), name="status_valid"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at", name="ends_after_start"),
        CheckConstraint("price_min IS NULL OR price_max IS NULL OR price_max >= price_min", name="price_order"),
        Index("ix_events_starts_at", "starts_at"),
        Index("ix_events_tags", "tags", postgresql_using="gin"),
        Index("ix_events_search", "search", postgresql_using="gin"),
        Index("ix_events_title_trgm", "title", postgresql_using="gin",
              postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_events_embedding", "embedding", postgresql_using="hnsw",
              postgresql_with={"m": 16, "ef_construction": 64},
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_events_review", "review_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="SET NULL"), index=True)
    # Copied from the place (or the venue geocode) so map queries need no join
    geom = mapped_column(Geography("POINT", srid=4326), nullable=False)
    venue_name: Mapped[str | None] = mapped_column(Text)
    address_text: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    duration_estimated: Mapped[bool] = mapped_column(Boolean, server_default="false")
    all_day: Mapped[bool] = mapped_column(Boolean, server_default="false")
    rrule: Mapped[str | None] = mapped_column(Text)  # RFC 5545, anchored at starts_at
    recurrence_text: Mapped[str | None] = mapped_column(Text)  # as written ("every Sunday")
    tz: Mapped[str] = mapped_column(Text, server_default="America/Los_Angeles")
    price_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), server_default="USD")
    is_free: Mapped[bool | None] = mapped_column(Boolean)
    price_text: Mapped[str | None] = mapped_column(Text)
    ticket_url: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    embedding = mapped_column(Vector(EMBED_DIM))
    origin: Mapped[str] = mapped_column(Text, server_default="manual")
    review_status: Mapped[str] = mapped_column(Text, server_default="ok")
    status: Mapped[str] = mapped_column(Text, server_default="scheduled")
    confidence: Mapped[float | None] = mapped_column(Float)
    user_overrides: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    search = mapped_column(TSVECTOR, Computed(
        "to_tsvector('english'::regconfig, coalesce(title, '') || ' ' || coalesce(venue_name, '') "
        "|| ' ' || coalesce(category, '') || ' ' || coalesce(description, ''))",
        persisted=True))


class Occurrence(Base):
    """Concrete start/end times, RRULEs expanded ahead. One row for a one-off event."""
    __tablename__ = "occurrences"
    __table_args__ = (
        UniqueConstraint("event_id", "starts_at", name="uq_occurrence"),
        Index("ix_occurrences_starts_at", "starts_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Source(Base):
    """Where an item came from: a shared link, text, a screenshot, or a discovery adapter row."""
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("adapter", "external_id", name="uq_sources_adapter_ext"),
        CheckConstraint(_in("status", SOURCE_STATUS), name="status_valid"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    url: Mapped[str | None] = mapped_column(Text)
    url_norm: Mapped[str | None] = mapped_column(Text, unique=True)
    kind: Mapped[str] = mapped_column(Text)  # tiktok, youtube, gmaps, applemaps, event_page, instagram, text, image, discovery
    adapter: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    title: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ItemSource(Base):
    """Which items a source mentions. A list video links to several places."""
    __tablename__ = "item_sources"
    __table_args__ = (
        CheckConstraint("num_nonnulls(place_id, event_id) = 1", name="one_item"),
        Index("uq_item_sources_place", "source_id", "place_id", unique=True,
              postgresql_where=text("place_id IS NOT NULL")),
        Index("uq_item_sources_event", "source_id", "event_id", unique=True,
              postgresql_where=text("event_id IS NOT NULL")),
        Index("ix_item_sources_place", "place_id"),
        Index("ix_item_sources_event", "event_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger, server_default="0")  # order in a list video
    confidence: Mapped[float | None] = mapped_column(Float)
    mention_at: Mapped[float | None] = mapped_column(Float)  # seconds into the video where it comes up


class ItemImage(Base):
    """Candidate hero pictures for one item: video frames near where it was mentioned, or page photos."""
    __tablename__ = "item_images"
    __table_args__ = (
        CheckConstraint("num_nonnulls(place_id, event_id) = 1", name="one_item"),
        Index("ix_item_images_place", "place_id"),
        Index("ix_item_images_event", "event_id"),
        Index("ix_item_images_source", "source_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)  # frame or page
    path: Mapped[str | None] = mapped_column(Text)  # relative to DATA_DIR/media
    url: Mapped[str | None] = mapped_column(Text)  # remote photo, cached into path on first view
    at_seconds: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    chosen: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Media(Base):
    __tablename__ = "media"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)  # video, thumb, photo
    path: Mapped[str] = mapped_column(Text)  # relative to DATA_DIR/media
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidate(Base):
    """Alternative place matches kept for the review picker."""
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    # The place these are alternatives for (the review picker swaps it)
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"), index=True)
    item_index: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    provider: Mapped[str] = mapped_column(Text)  # photon, address, website, maps_link
    name: Mapped[str] = mapped_column(Text)
    geom = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    address_text: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    score: Mapped[float] = mapped_column(Float)
    chosen: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JOB_STATUS), name="status_valid"),
        Index("ix_jobs_pending", "run_after", postgresql_where=text("status IN ('queued', 'running')")),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    type: Mapped[str] = mapped_column(Text)  # ingest, discover, refresh, embed, backfill
    payload: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    needs_gpu: Mapped[bool] = mapped_column(Boolean, server_default="false")
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    stage: Mapped[str | None] = mapped_column(Text)
    pct: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, server_default="3")
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserItemState(Base):
    """Per-person status, rating and notes on a place or an event (exactly one)."""
    __tablename__ = "user_item_state"
    __table_args__ = (
        CheckConstraint("num_nonnulls(place_id, event_id) = 1", name="one_item"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint(f"status IS NULL OR {_in('status', MY_STATUS)}", name="status_valid"),
        Index("uq_state_place", "user_id", "place_id", unique=True, postgresql_where=text("place_id IS NOT NULL")),
        Index("uq_state_event", "user_id", "event_id", unique=True, postgresql_where=text("event_id IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    status: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    visited_at: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Tag(Base):
    __tablename__ = "tags"
    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    grp: Mapped[str] = mapped_column(Text)  # category, vibe, setting, time, budget, free
    embedding = mapped_column(Vector(EMBED_DIM))


class Interest(Base):
    """Interest tags. user_id NULL is the shared 'us' profile."""
    __tablename__ = "interests"
    __table_args__ = (
        UniqueConstraint("user_id", "tag_slug", name="uq_interest", postgresql_nulls_not_distinct=True),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tag_slug: Mapped[str] = mapped_column(ForeignKey("tags.slug", ondelete="CASCADE"))
    weight: Mapped[float] = mapped_column(Float, server_default="1")
    kind: Mapped[str] = mapped_column(Text, server_default="seed")  # seed, learned


class TasteProfile(Base):
    __tablename__ = "taste_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_taste_user", postgresql_nulls_not_distinct=True),
    )
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    vec = mapped_column(Vector(EMBED_DIM))
    neg_vec = mapped_column(Vector(EMBED_DIM))
    n_signals: Mapped[int] = mapped_column(Integer, server_default="0")
    prefs: Mapped[dict] = mapped_column(JSONB, server_default="{}")  # learned weekday/hour weights
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(Text)
    day: Mapped[date] = mapped_column(Date)
    window_start: Mapped[time | None] = mapped_column(Time)
    window_end: Mapped[time | None] = mapped_column(Time)
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2))
    vibe: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    stops: Mapped[list] = mapped_column(JSONB, server_default="[]")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    new_items: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class AdapterState(Base):
    __tablename__ = "adapter_state"
    adapter: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true")
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    cursor: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    calls_day: Mapped[date | None] = mapped_column(Date)
    calls_today: Mapped[int] = mapped_column(Integer, server_default="0")


class HttpCache(Base):
    """Cached third-party responses, so public services see as few requests as possible."""
    __tablename__ = "http_cache"
    key: Mapped[str] = mapped_column(Text, primary_key=True)  # sha256 of method + url + body
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(SmallInteger)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
