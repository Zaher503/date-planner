# Date Planner

Send it a TikTok, an event page, a Google/Apple Maps link or plain text. It works out the place or event (name, address, price, dates, duration) and pins it on a map shared by Zaher and Katherine. Later phases add a map UI, video transcription for videos without captions, and a discovery job that looks for nearby events matching their interests every 3 days.

Runs on the Zephyrus as a Docker Compose stack, all AI local: the LLM (gemma4:e4b) and Whisper come from the shared [ai-hub](https://github.com/Zaher503/ai-hub) (one Ollama, one Whisper and a GPU queue for Dates, Foodbox and the Transcriber on the RTX 3070). Pushes to `main` deploy themselves. No paid services. The full design and the phase list are in [docs/PLAN.md](docs/PLAN.md).

## Status

| Phase | State |
|---|---|
| 1 Foundation (stack, schema, API skeleton, deploy) | Done |
| 2 Geo infra (Photon, OSRM car/foot, SearXNG, SoCal map tiles) | Done |
| 3 Ingestion fast path (TikTok, maps links, web pages, text; resolver; review API) | Done |
| 4 Map UI (SvelteKit + MapLibre) | Deployed 2026-10-10 (`acc5cca`), not yet checked in a browser |
| 5 Video slow path (Whisper, frame OCR, media archive, screenshots) | Deployed 2026-10-10; Whisper now runs in the shared AI hub |
| 6 Caddy + Authentik at dates.zkocr.com, iPhone Shortcut | Live 2026-10-11 (Caddy, Cloudflare, Authentik group `dates`: Zaher + Kathy); Shortcut not yet set up on the phones |
| 7 Interests + discovery (Ticketmaster key set, dry run finds ~760 events / 21 days) | Started (Ticketmaster, RA, Luma, Eventbrite adapters merged; iCal, venue watch, scheduler, inbox, scoring still to do) |
| 8 Date-night planner + calendar | Core merged (OSRM client, picker, opening hours); plan API, ICS feed and UI still to do |
| 9 Lifecycle, backups, Homarr tile | Homarr tile done (2026-10-10, both boards); widget and the rest not started |

**Next step:** try the video slow path through the AI hub, then the remaining Phase 7/8 work (iCal feed adapter and plan API are in the tree but not wired up). See `docs/TODO-ZAHER.md`.

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
| `backend/app/browser.py` | Drives the `browser` container (Playwright) for pages that block plain fetching or show prices only after a click; every request is checked against private addresses. CAPTCHAs are reported as blocked, never solved |
| `backend/app/resolve/` | `candidates` (Photon, Overpass, Nominatim, SearXNG), `scorer`, `resolver` |
| `backend/app/discover/` | Adapter framework, Ticketmaster adapter, dry-run CLI |
| `backend/app/llm/ollama.py`, `ingest/transcribe.py` | Clients for the AI hub (LLM and Whisper); they report where a call is in the hub's queue |
| `backend/app/eval.py` | Golden-set accuracy check (writes nothing) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | pytest, offline fixtures (real TikTok/page responses, trimmed) |
| `deploy/` | `compose.yaml`, Dockerfiles, SearXNG settings, `.env.example` |
| `.github/workflows/` | `ci.yml` (tests, frontend build, compose check, image build) and `cd.yml` (publish to GHCR, deploy to the Zephyrus) |
| `scripts/` | `deploy.bat`, `add-runner.sh`, `init-env.sh`, `photon_import.sh`, `fetch_tiles.sh`, `build_osrm.sh` |
| `docs/` | `PLAN.md` (design + phases), `OPERATIONS.md` (running it) |
| `frontend/` | SvelteKit app: map, filters, item list/detail/edit, Add box, settings, PWA shell |

## Where it fits

```
phone / browser -> Cloudflare -> NAS (Caddy + Authentik) -> api :8820 ----> db (Postgres)
                                                            worker ------> photon, osrm-car, osrm-foot, searxng
                                                               |
                                                               +--> ai-hub gateway :11434 -> ollama, whisper -> RTX 3070
```

The Dates stack is `db`, `api`, `worker`, `photon`, `osrm-car`, `osrm-foot` and `searxng`, on the Docker network `dates_default`. `api` and `worker` also join the network `ai`, created by the [ai-hub](https://github.com/Zaher503/ai-hub) stack, to reach `http://ai-hub:11434`. Foodbox and the Transcriber use the same hub. Details and rollback in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Everyday commands

```bash
git push                      # CI, then CD: publish the images and update the stack on the Zephyrus
scripts/deploy.bat            # re-run the deploy without a new commit
```

Every push to `main` runs CI (backend tests, frontend check/tests/build, compose check, image build). When it passes, CD publishes `ghcr.io/zaher503/date-planner` and `date-planner-db` and a self-hosted runner on the Zephyrus pulls them and restarts the stack. Uncommitted changes are never deployed.

```bash
cd backend && .venv/Scripts/python -m pytest -q tests
```

Unit tests (offline). Create the venv once with `python -m venv .venv` and `pip install -r requirements.txt pytest`.

```bash
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose exec -T worker python -m app.eval'
```

Golden-set accuracy. Run it after any change to extraction or resolving.

```bash
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose exec -T worker python -m app.discover.run --dry-run'
```

Discovery dry run (Ticketmaster skips itself until `TICKETMASTER_KEY` is set in `~/dateplanner/.env`).

Adding a link by hand (the key is `DATES_KEY` in `~/.claude/secrets/homelab.env`):

```bash
curl -X POST http://192.168.0.169:8820/api/add -H "X-Dates-Key: $DATES_KEY" -H "Content-Type: application/json" -d '{"url":"https://www.tiktok.com/@user/video/123","user":"zaher"}'
```

The API trusts the `X-Authentik-Username` header only from the NAS (192.168.0.70). To call identity-protected routes before Phase 6, go through the NAS (`ssh` to it and `curl -H 'X-Authentik-Username: zaher' http://192.168.0.169:8820/api/review`) or set `DEV_USER=zaher` in `~/dateplanner/.env` temporarily.

More in [docs/OPERATIONS.md](docs/OPERATIONS.md).
