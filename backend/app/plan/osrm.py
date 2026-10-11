"""Drive and walk times from the self-hosted OSRM servers.

Points are (lat, lon). When OSRM is down or has no route, the leg is estimated from
the straight-line distance and a typical speed, and marked estimated=True.
"""
import logging
import math
from dataclasses import dataclass

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

Point = tuple[float, float]

# mode -> (settings attribute, OSRM profile, fallback speed in km/h)
PROFILES = {
    "drive": ("osrm_car_url", "driving", 30.0),
    "walk": ("osrm_foot_url", "foot", 4.8),
}
TIMEOUT = httpx.Timeout(4.0, connect=2.0)


@dataclass
class Leg:
    minutes: float
    metres: float
    estimated: bool = False


def haversine_m(a: Point, b: Point) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def estimate(a: Point, b: Point, mode: str) -> Leg:
    metres = haversine_m(a, b)
    kmh = PROFILES[mode][2]
    return Leg(minutes=metres / 1000 / kmh * 60, metres=metres, estimated=True)


def _base(mode: str) -> tuple[str, str]:
    if mode not in PROFILES:
        raise ValueError(f"unknown mode {mode!r}")
    attr, profile, _ = PROFILES[mode]
    return getattr(get_settings(), attr).rstrip("/"), profile


def _coords(points: list[Point]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)


def _get(client: httpx.Client | None, url: str, params: dict) -> dict | None:
    try:
        if client is not None:
            r = client.get(url, params=params, timeout=TIMEOUT)
        else:
            r = httpx.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("osrm %s failed: %s", url.split("/v1/")[0], type(e).__name__)
        return None
    return data if data.get("code") == "Ok" else None


def route(a: Point, b: Point, mode: str = "drive", client: httpx.Client | None = None) -> Leg:
    """Travel time and distance from a to b."""
    base, profile = _base(mode)
    data = _get(client, f"{base}/route/v1/{profile}/{_coords([a, b])}", {"overview": "false"})
    routes = (data or {}).get("routes") or []
    if not routes:
        return estimate(a, b, mode)
    return Leg(minutes=routes[0]["duration"] / 60, metres=routes[0]["distance"])


def table(origin: Point, dests: list[Point], mode: str = "drive", client: httpx.Client | None = None) -> list[Leg]:
    """Travel from one origin to many destinations, in the same order as dests."""
    if not dests:
        return []
    base, profile = _base(mode)
    params = {"sources": "0", "destinations": ";".join(str(i) for i in range(1, len(dests) + 1)),
              "annotations": "duration,distance"}
    data = _get(client, f"{base}/table/v1/{profile}/{_coords([origin, *dests])}", params)
    durations = ((data or {}).get("durations") or [[]])[0]
    distances = ((data or {}).get("distances") or [[]])[0]
    out = []
    for i, d in enumerate(dests):
        sec = durations[i] if i < len(durations) else None
        m = distances[i] if i < len(distances) else None
        # Unreachable entries come back as null
        out.append(estimate(origin, d, mode) if sec is None else
                   Leg(minutes=sec / 60, metres=m if m is not None else haversine_m(origin, d)))
    return out
