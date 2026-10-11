# Date Planner

Send it a TikTok, an event page, a Google/Apple Maps link or plain text. It works out the place or event (name, address, price, dates, duration) and pins it on a map shared by Zaher and Katherine. Later phases add a map UI, video transcription for videos without captions, and a discovery job that looks for nearby events matching their interests every 3 days.

Runs on the Zephyrus as a Docker Compose stack, all AI local (Ollama gemma4:e4b on the RTX 3070, shared with Recipe Box). No paid services. The full design and the phase list are in [docs/PLAN.md](docs/PLAN.md).

## Status

| Phase | State |
|---|---|
| 1 Foundation (stack, schema, API skeleton, deploy) | Done |
| 2 Geo infra (Photon, OSRM car/foot, SearXNG, SoCal map tiles) | Done |
| 3 Ingestion fast path (TikTok, maps links, web pages, text; resolver; review API) | Done |
| 4 Map UI (SvelteKit + MapLibre) | Deployed 2026-10-10 (`acc5cca`), not yet checked in a browser |
| 5 Video slow path (Whisper, frame OCR, media archive, screenshots) | Deployed 2026-10-10 (worker on the GPU), no video has gone through it yet |
| 6 Caddy + Authentik at dates.zkocr.com, iPhone Shortcut | Caddy snippet + Shortcut/`add-date.ps1` written; Cloudflare CNAME, Authentik group and NAS install still **need Zaher** |
| 7 Interests + discovery (Ticketmaster key set, dry run finds ~760 events / 21 days) | Started (RA/Luma/Eventbrite/iCal adapters half-built on an unmerged branch) |
| 8 Date-night planner + calendar | Half-built on an unmerged branch |
| 9 Lifecycle, backups, Homarr tile | Homarr tile done (2026-10-10, both boards); widget and the rest not started |

**Next step:** try the deployed map and the video slow path, then Phase 6 (Caddy, Cloudflare, Authentik) and the unmerged Phase 7/8 branches. See `docs/TODO-ZAHER.md`.

Accuracy on the golden set (`backend/tests/golden.json`, 22 real links, 28 expected places): 28/28 correct, 0 wrong auto-accepts.

## How a link becomes a pin

1. `POST /api/add` (key) or `/api/ui/add` (Authentik) stores a Source and queues an `ingest` job. Duplicate links (ignoring tracking parameters) return `exists`.
2. The worker reads the link without downloading video:
   - **TikTok:** the public page's JSON gives the caption, on-screen text stickers (list videos put every item there), the location tag, @mentions, TikTok's search suggestions and TikTok's own auto-caption transcript. oEmbed adds the thumbnail.
   - **Maps links:** name, address and coordinates are parsed from the (expanded) URL.
   - **Web pages:** schema.org JSON-LD (Event, LocalBusiness); otherwise the page text.
   - **Free text:** straight to the model.
3. The local model extracts items into a strict JSON schema. Prices, dates, times and street addresses that are not in the text are dropped (no invented numbers).
4. The resolver finds each place: exact pin, then stated street address (local Photon, then public Nominatim for house numbers), then a name search near home, then the venue's own website or search snippets via SearXNG. Venues inside other venues are pinned at their host.
5. Confident matches are pinned; unsure ones are pinned with `needs_review` and up to 5 alternatives. Places from several sources merge into one; user edits (`user_overrides`) are never overwritten.

## Layout

| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI app (routers in `app/api/`: `add`, `health`, `review`, `auth`) |
| `backend/app/worker.py`, `tasks.py`, `jobs.py` | Worker: Postgres job queue (SKIP LOCKED), one GPU lane + two CPU lanes, APScheduler |
| `backend/app/ingest/` | `urls` (normalize/classify), `tiktok`, `maps_links`, `event_page`, `pipeline` (the ingest job), `store` (upsert/merge) |
| `backend/app/llm/` | `ollama` client, `extract` (prompt + schema), `verify` (no invented numbers) |
| `backend/app/resolve/` | `candidates` (Photon, Overpass, Nominatim, SearXNG), `scorer`, `resolver` |
| `backend/app/discover/` | Adapter framework, Ticketmaster adapter, dry-run CLI |
| `backend/app/gpu.py` | GPU lock shared with Recipe Box and the Transcriber |
| `backend/app/eval.py` | Golden-set accuracy check (writes nothing) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | pytest, offline fixtures (real TikTok/page responses, trimmed) |
| `deploy/` | `compose.yaml`, Dockerfiles, SearXNG settings, `.env.example` |
| `scripts/` | `deploy.sh`, `init-env.sh`, `photon_import.sh`, `fetch_tiles.sh`, `build_osrm.sh` |
| `docs/` | `PLAN.md` (design + phases), `OPERATIONS.md` (running it) |
| `frontend/` | SvelteKit app: map, filters, item list/detail/edit, Add box, settings, PWA shell |

## Everyday commands

```bash
scripts/deploy.sh
```

Ships the committed `HEAD` to `~/dateplanner/src` on the Zephyrus and runs `docker compose up -d --build` (uncommitted changes are not deployed). `scripts/deploy.sh worker` rebuilds one service.

```bash
cd backend && .venv/Scripts/python -m pytest -q tests
```

Unit tests (offline). Create the venv once with `python -m venv .venv` and `pip install -r requirements.txt pytest`.

```bash
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose exec -T worker python -m app.eval'
```

Golden-set accuracy. Run it after any change to extraction or resolving.

```bash
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose exec -T worker python -m app.discover.run --dry-run'
```

Discovery dry run (Ticketmaster skips itself until `TICKETMASTER_KEY` is set in `~/dateplanner/.env`).

Adding a link by hand (the key is `DATES_KEY` in `~/.claude/secrets/homelab.env`):

```bash
curl -X POST http://192.168.0.172:8820/api/add -H "X-Dates-Key: $DATES_KEY" -H "Content-Type: application/json" -d '{"url":"https://www.tiktok.com/@user/video/123","user":"zaher"}'
```

The API trusts the `X-Authentik-Username` header only from the NAS (192.168.0.70). To call identity-protected routes before Phase 6, go through the NAS (`ssh` to it and `curl -H 'X-Authentik-Username: zaher' http://192.168.0.172:8820/api/review`) or set `DEV_USER=zaher` in `~/dateplanner/.env` temporarily.

More in [docs/OPERATIONS.md](docs/OPERATIONS.md).
