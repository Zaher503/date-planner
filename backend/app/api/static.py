"""Map files (open, cacheable) and the built SvelteKit app. The app shell route
catches every other path, so this router must be included last."""
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.config import get_settings

router = APIRouter()

TILES_CACHE = "public, max-age=86400"
ASSETS_CACHE = "public, max-age=2592000"
IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
OTHER_CACHE = "public, max-age=3600"
ASSET_TYPES = {".pbf": "application/x-protobuf", ".json": "application/json", ".png": "image/png"}
# First path segments that never fall through to the app shell
NOT_APP = {"api", "tiles", "healthz", "cal"}
for _ext, _type in ((".webmanifest", "application/manifest+json"), (".mjs", "text/javascript"),
                    (".wasm", "application/wasm"), (".svg", "image/svg+xml")):
    mimetypes.add_type(_type, _ext)
NOT_BUILT = ("<!doctype html><meta charset=utf-8><title>Date Planner</title>"
             "<p>The UI is not built yet. The API is running.</p>")


def safe_file(base: Path, rel: str) -> Path | None:
    """A file inside base, or None (missing, a directory, or outside base)."""
    try:
        root = base.resolve()
        p = (root / rel.lstrip("/")).resolve()
    except (OSError, ValueError):
        return None
    if not p.is_relative_to(root) or not p.is_file():
        return None
    return p


@router.api_route("/tiles/region.pmtiles", methods=["GET", "HEAD"], include_in_schema=False)
def pmtiles():
    """Basemap; FileResponse answers Range requests with 206."""
    p = get_settings().data_dir / "tiles" / "region.pmtiles"
    if not p.is_file():
        raise HTTPException(404, "map tiles are not installed (scripts/fetch_tiles.sh)")
    return FileResponse(p, media_type="application/octet-stream", headers={"Cache-Control": TILES_CACHE})


@router.api_route("/tiles/assets/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def map_assets(path: str):
    """Glyphs and sprites from scripts/fetch_map_assets.sh."""
    p = safe_file(get_settings().data_dir / "tiles" / "assets", path)
    if p is None:
        raise HTTPException(404, "no such map asset")
    ctype = ASSET_TYPES.get(p.suffix) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=ctype, headers={"Cache-Control": ASSETS_CACHE})


def cache_for(rel: str) -> str:
    if rel.startswith("_app/immutable/"):
        return IMMUTABLE
    if rel.endswith(".html") or rel == "service-worker.js":
        return NO_CACHE
    return OTHER_CACHE


@router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def app_shell(path: str):
    """Files from the built app; client-side routes get index.html."""
    if path.split("/", 1)[0] in NOT_APP:
        raise HTTPException(404, "not found")
    root = get_settings().static_dir
    if not (root / "index.html").is_file():
        return HTMLResponse(NOT_BUILT, status_code=503, headers={"Cache-Control": NO_CACHE})
    rel = path.strip("/")
    f = None
    if rel:
        f = safe_file(root, rel) or safe_file(root, f"{rel}/index.html") or safe_file(root, f"{rel}.html")
    if f is None:
        last = rel.rsplit("/", 1)[-1]
        if rel.startswith("_app/") or "." in last:
            raise HTTPException(404, "not found")  # a missing asset, not a page
        f = root / "index.html"
    rel_name = f.resolve().relative_to(root.resolve()).as_posix()
    return FileResponse(f, headers={"Cache-Control": cache_for(rel_name)})
