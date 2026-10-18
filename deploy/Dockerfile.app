# UI: the SvelteKit app (adapter-static) built into frontend/build.
# Until frontend/ has a package.json the build is empty and the API serves a "not built" page.
FROM node:22-bookworm-slim AS frontend
WORKDIR /fe
COPY frontend/ ./
RUN if [ -f package.json ]; then \
      if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi \
      && npm run build; \
    else mkdir -p build; fi

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
# ffmpeg for audio and frames (slow path)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
# The keyed tester service (deploy/compose.yaml "tester") runs this unchanged, wrapped by
# import-tester/service.py. cookies.txt/.venv/.data are never in the build context (.dockerignore).
COPY import-tester/ ./import-tester/
COPY --from=frontend /fe/build /app/static
EXPOSE 8820
