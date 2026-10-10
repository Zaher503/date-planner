# Date Planner

Send it a TikTok, an event page, a Google/Apple Maps link, plain text or a screenshot. It works out the place or event (name, address, price, dates, duration) and pins it on a shared map. Every 3 days it looks for nearby events that match your interests and puts them in a Suggested inbox.

Runs on the Zephyrus as a Docker Compose stack, served at https://dates.zkocr.com behind Authentik. All AI is local (Ollama + Whisper on the RTX 3070). No paid services.

## Layout

| Path | What |
|---|---|
| `backend/app/` | FastAPI app and worker (same image) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | pytest, offline fixtures only |
| `frontend/` | SvelteKit + MapLibre UI, built to static files served by the API |
| `deploy/` | `compose.yaml`, Dockerfiles, SearXNG config, Caddy snippet, `.env.example` |
| `scripts/` | deploy, tiles/OSRM/Photon setup, backup pull |
| `docs/` | Shortcut setup and operations |

## Deploy

```bash
scripts/deploy.sh
```

Ships the committed `HEAD` to `~/dateplanner` on the Zephyrus and runs `docker compose up -d --build`. See `docs/OPERATIONS.md`.
