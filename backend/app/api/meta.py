"""App settings and filter facets for the UI."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.config import get_settings
from app.db.models import AppSettings, Event, Place, User
from app.db.session import get_db
from app.ingest.store import home_point

router = APIRouter()

# Matches scripts/fetch_tiles.sh; the SOURCE file it writes wins when present
DEFAULT_BOUNDS = [-120.3, 32.5, -116.0, 35.8]


def _user(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name}


def tile_bounds() -> list[float]:
    """Bbox of the extracted basemap, read from tiles/SOURCE ("<build> w,s,e,n")."""
    try:
        text = (get_settings().data_dir / "tiles" / "SOURCE").read_text().split()
        bounds = [float(x) for x in text[1].split(",")]
        if len(bounds) == 4:
            return bounds
    except (OSError, IndexError, ValueError):
        pass
    return DEFAULT_BOUNDS


@router.get("/api/settings")
def settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(AppSettings, 1)
    lat, lon = home_point(db)
    users = db.scalars(select(User).order_by(User.id)).all()
    return {
        "home": {"lat": round(lat, 6), "lon": round(lon, 6), "source": s.home_source if s else "default"},
        "radius_km": s.radius_km if s else 40,
        "units": s.units if s else "mi",
        "tz": get_settings().default_tz,
        "user": _user(user),
        "users": [_user(u) for u in users],
        "map": {"tiles": "/tiles/region.pmtiles", "assets": "/tiles/assets", "bounds": tile_bounds()},
    }


@router.get("/api/facets")
def facets(db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Tag and category counts over items that are not dismissed."""
    tags = union_all(
        select(func.unnest(Place.tags).label("tag")).where(Place.review_status != "dismissed"),
        select(func.unnest(Event.tags).label("tag")).where(Event.review_status != "dismissed"),
    ).subquery()
    n = func.count().label("n")
    tag_rows = db.execute(select(tags.c.tag, n).group_by(tags.c.tag).order_by(n.desc(), tags.c.tag).limit(100)).all()
    cats = union_all(
        select(Place.category.label("cat")).where(Place.review_status != "dismissed", Place.category.isnot(None)),
        select(Event.category.label("cat")).where(Event.review_status != "dismissed", Event.category.isnot(None)),
    ).subquery()
    cat_rows = db.execute(select(cats.c.cat, n).group_by(cats.c.cat).order_by(n.desc(), cats.c.cat)).all()
    return {"tags": [{"tag": t, "n": c} for t, c in tag_rows],
            "categories": [{"cat": t, "n": c} for t, c in cat_rows]}
