"""Home Assistant: home location (zone.home) and phone pushes (notify.mobile_app_*)."""
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(base_url=s.ha_url, timeout=10,
                        headers={"Authorization": f"Bearer {s.ha_token}"})


def home_location() -> tuple[float, float] | None:
    """(lat, lon) of zone.home, or None if HA is unreachable."""
    if not get_settings().ha_token:
        return None
    try:
        with _client() as c:
            attrs = c.get("/api/states/zone.home").raise_for_status().json()["attributes"]
        return float(attrs["latitude"]), float(attrs["longitude"])
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("zone.home lookup failed: %s", e)
        return None


def push(title: str, message: str, url: str | None = None, targets: list[str] | None = None) -> int:
    """Send to each notify target. Returns how many were sent."""
    s = get_settings()
    targets = targets or [t.strip() for t in s.notify_targets.split(",") if t.strip()]
    if not s.ha_token or not targets:
        return 0
    data = {"title": title, "message": message}
    if url:
        data["data"] = {"url": url, "clickAction": url}
    sent = 0
    with _client() as c:
        for t in targets:
            try:
                c.post(f"/api/services/notify/{t}", json=data).raise_for_status()
                sent += 1
            except httpx.HTTPError as e:
                log.warning("push to %s failed: %s", t, e)
    return sent
