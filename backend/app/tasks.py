"""Job handlers. Each takes (db, job) and returns a result dict or raises."""
import logging
from collections.abc import Callable

from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy.orm import Session

from app.db.models import AppSettings, Job
from app.notify import ha

log = logging.getLogger(__name__)

Handler = Callable[[Session, Job], dict]
HANDLERS: dict[str, Handler] = {}


def handler(name: str):
    def wrap(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return wrap


@handler("ingest")
def ingest(db: Session, job: Job) -> dict:
    from app.ingest.pipeline import run
    return run(db, job)


@handler("refresh_home")
def refresh_home(db: Session, job: Job) -> dict:
    """Map center and discovery origin follow HA zone.home unless set by hand."""
    s = db.get(AppSettings, 1)
    if s.home_source != "ha":
        return {"skipped": "home set manually"}
    loc = ha.home_location()
    if not loc:
        raise RuntimeError("Home Assistant did not return zone.home")
    lat, lon = loc
    s.home = from_shape(Point(lon, lat), srid=4326)
    db.commit()
    return {"lat": round(lat, 4), "lon": round(lon, 4)}
