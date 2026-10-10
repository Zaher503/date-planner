"""Reachability of the internal services, for Settings and quick checks."""
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import APIRouter, Depends

from app.api.auth import current_user
from app.config import get_settings

router = APIRouter()


def _probe(name: str, url: str, params: dict | None = None) -> dict:
    start = time.monotonic()
    try:
        r = httpx.get(url, params=params, timeout=5)
        ok = r.status_code == 200
        detail = None if ok else f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        ok, detail = False, type(e).__name__
    return {"name": name, "ok": ok, "ms": round((time.monotonic() - start) * 1000), "detail": detail}


def check_services() -> list[dict]:
    s = get_settings()
    probes = [
        ("photon", f"{s.photon_url}/api", {"q": "Los Angeles", "limit": 1}),
        ("osrm-car", f"{s.osrm_car_url}/nearest/v1/driving/-118.3265,34.0461", None),
        ("osrm-foot", f"{s.osrm_foot_url}/nearest/v1/foot/-118.3265,34.0461", None),
        ("searxng", f"{s.searxng_url}/healthz", None),
        ("ollama", f"{s.ollama_url}/api/tags", None),
    ]
    with ThreadPoolExecutor(len(probes)) as ex:
        return list(ex.map(lambda p: _probe(*p), probes))


@router.get("/api/health/services")
def services(_=Depends(current_user)):
    return check_services()
