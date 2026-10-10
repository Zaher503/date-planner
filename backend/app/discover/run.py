"""Discovery entry point. For now only a dry run that prints what each adapter finds.

    python -m app.discover.run --dry-run [--adapter ticketmaster] [--days 21]

The full run (geocode, dedup, embed, score, inbox, push) arrives with Phase 7.
"""
import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from geoalchemy2.shape import to_shape

from app.config import get_settings
from app.db.models import AppSettings
from app.db.session import SessionLocal
from app.discover.adapters import ADAPTERS
from app.discover.base import Area


def home_area() -> Area:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None or s.home is None:
            sys.exit("no home location yet (refresh_home job has not run)")
        p = to_shape(s.home)
        return Area(lat=p.y, lon=p.x, radius_km=s.radius_km)


def build(name: str):
    cls = ADAPTERS[name]
    key = getattr(get_settings(), cls.key_setting) if cls.key_setting else None
    return cls(key=key)


def dry_run(names: list[str], days: int) -> None:
    area = home_area()
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    print(f"area {area.lat:.4f},{area.lon:.4f} r={area.radius_km:g} km, next {days} days")
    for name in names:
        ad = build(name)
        if not ad.enabled():
            print(f"{name}: skipped (no {ad.key_setting.upper()} in .env)")
            continue
        try:
            events = list(ad.fetch(area, start, end))
        except Exception as e:
            print(f"{name}: FAILED after {ad.calls} calls: {type(e).__name__}: {e}")
            continue
        cats = Counter(c for e in events for c in e.categories[:1])
        located = sum(1 for e in events if e.lat is not None)
        priced = sum(1 for e in events if e.price_min is not None)
        print(f"{name}: {len(events)} events in {ad.calls} calls, {located} with coordinates, "
              f"{priced} with prices; top: {dict(cats.most_common(6))}")
        for e in events[:10]:
            when = e.starts_at.astimezone().strftime("%a %b %d %H:%M") if e.starts_at else "TBA"
            price = f"${e.price_min:g}" if e.price_min is not None else "-"
            print(f"   {when}  {price:>6}  {e.title[:60]}  @ {e.venue_name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", required=True)
    ap.add_argument("--adapter", action="append", choices=sorted(ADAPTERS))
    ap.add_argument("--days", type=int, default=21)
    a = ap.parse_args()
    dry_run(a.adapter or sorted(ADAPTERS), a.days)


if __name__ == "__main__":
    main()
