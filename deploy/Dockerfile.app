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
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
COPY --from=frontend /fe/build /app/static
EXPOSE 8820
