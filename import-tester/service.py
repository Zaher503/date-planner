"""Container entrypoint for the import tester (see server.py's own docstring for what it
runs). The desktop run.bat runs server.py directly against an SSH tunnel; this wraps the
same app unchanged, for the "tester" service in deploy/compose.yaml:

- binds 0.0.0.0 instead of opening a local browser window
- requires an X-Tester-Key header on every route except /healthz
- refuses to start at all if TESTER_KEY is not set (fail closed, never fail open)

Reachable only through its own keyed Caddy route (see deploy/caddy-snippet.txt), never through
the main dates.zkocr.com auth. It never touches the real database or /srv/dateplanner: no
volume is mounted for it in compose.yaml, and it runs the same database-stubbed code path
server.py uses for the desktop tool.
"""
import os
import sys
from pathlib import Path

# backend/ is copied flat into /app (deploy/Dockerfile.app), so the "app" package lives at
# /app/app. Add that before importing server.py, whose own sys.path line (HERE.parent /
# "backend") assumes the desktop's repo layout and resolves to a path that doesn't exist in
# this image - harmless, since a missing sys.path entry is just skipped.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402

TESTER_KEY = os.environ.get("TESTER_KEY", "")
if not TESTER_KEY:
    sys.exit("TESTER_KEY is not set - refusing to start with no key check")

app = server.app


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.middleware("http")
async def check_key(request, call_next):
    from fastapi.responses import JSONResponse

    if request.url.path == "/healthz":
        return await call_next(request)
    if request.headers.get("X-Tester-Key") != TESTER_KEY:
        return JSONResponse({"detail": "bad or missing X-Tester-Key"}, status_code=401)
    return await call_next(request)


if __name__ == "__main__":
    import logging

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger().addHandler(server.Capture())
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    port = int(os.environ.get("PORT", "8899"))
    print(f"Import tester service on :{port}, keyed", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
