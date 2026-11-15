# Date Planner

Send it a TikTok, an event page, a Google/Apple Maps link or plain text. It works out the place or event (name, address, price, dates, duration) and pins it on a map shared by Zaher and Katherine. Later phases add a map UI, video transcription for videos without captions, and a discovery job that looks for nearby events matching their interests every 3 days.

Runs on the Zephyrus as a Docker Compose stack, all AI local: the LLM (gemma4:e4b) and Whisper come from the shared [ai-hub](https://github.com/Zaher503/ai-hub) (one Ollama, one Whisper and a GPU queue for Dates, Foodbox and the Transcriber on the RTX 3070). Pushes to `main` deploy themselves. No paid services. The full design and the phase list are in [docs/PLAN.md](docs/PLAN.md).

## Status

Updated 2026-11-10. The current, detailed state is in [status.md](status.md) and what comes next in [Roadmap.md](Roadmap.md); this table is only a summary and those two files win when they differ.

| Phase | State |
|---|---|
| 1 Foundation (stack, schema, API skeleton, deploy) | Done |
| 2 Geo infra (Photon, OSRM car/foot, SearXNG, SoCal map tiles) | Done |
| 3 Ingestion fast path (TikTok, YouTube, maps links, web pages, text, screenshots; resolver; review API) | Done, improved by the daily import check (`improvements/`) |
| 4 Map UI (SvelteKit + MapLibre) | Live. Redesign (Filters drawer, floating details) merged 2026-10-31, not yet checked on a real phone |
| 5 Video slow path (Whisper, frame OCR, media archive, screenshots) | Deployed; Whisper runs in the shared AI hub. Never run on a captionless TikTok yet |
| 6 Caddy + Authentik at dates.zkocr.com, iPhone Shortcut | Live (group `dates`: Zaher and Kathy); Shortcut not yet set up on the phones |
| 7 Interests + discovery | Started. Ticketmaster, RA, Luma, Eventbrite and iCal adapters exist; dry run only. Nothing writes discovered events, schedules discovery or scores them; no inbox |
| 8 Date-night planner + calendar | Plan API live (suggest and plan CRUD); no Plan page, no `.ics` download or feed yet |
| 9 Lifecycle, backups, Homarr tile | Homarr tile, past-event Archive, standing-venue weekly scan and repeating events (RRULE) are live. Nightly backup and weekly yt-dlp update are written but not merged yet; NAS backup pull, monthly re-verify and the Homarr widget not started |

**Next step:** follow the **Now** list in [Roadmap.md](Roadmap.md) (Plan page, per-item `.ics`, the discovery writer). Things only Zaher can do are under "Waiting on Zaher" in [status.md](status.md) and the `[Z]` items in the roadmap.

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
| `backend/app/main.py` | FastAPI app (routers in `app/api/`: `add`, `health`, `review`, `meta`, `map`, `items`, `media`, `google`, `verified`, `plans`, `static`; `auth` holds the identity check). Routes are listed in [docs/API.md](docs/API.md) |
| `backend/app/worker.py`, `tasks.py`, `jobs.py` | Worker: Postgres job queue (SKIP LOCKED), one GPU lane + two CPU lanes, APScheduler |
| `backend/app/ingest/` | `urls` (normalize/classify), `tiktok`, `maps_links`, `event_page`, `pipeline` (the ingest job), `store` (upsert/merge) |
| `backend/app/llm/` | `ollama` client, `extract` (prompt + schema), `verify` (no invented numbers) |
| `backend/app/browser.py` | Drives the `browser` container (Playwright) for pages that block plain fetching or show prices only after a click; every request is checked against private addresses. CAPTCHAs are reported as blocked, never solved |
| `backend/app/resolve/` | `candidates` (Photon, Overpass, Nominatim, SearXNG), `scorer`, `resolver` |
| `backend/app/discover/` | Adapter framework; Ticketmaster, Resident Advisor, Luma, Eventbrite and iCal adapters; dry-run CLI |
| `backend/app/plan/`, `hours.py` | Date-night picker (OSRM travel times) and opening hours |
| `backend/app/watch.py`, `recurrence.py`, `occurrences.py` | Standing-venue weekly scan, RRULE from explicit patterns, occurrences 120 days ahead |
| `backend/app/llm/ollama.py`, `ingest/transcribe.py` | Clients for the AI hub (LLM and Whisper); they report where a call is in the hub's queue |
| `backend/app/eval.py` | Golden-set accuracy check (writes nothing) |
| `backend/migrations/` | Alembic migrations |
| `backend/tests/` | pytest, offline fixtures (real TikTok/page responses, trimmed) |
| `deploy/` | `compose.yaml`, Dockerfiles, SearXNG settings, `.env.example` |
| `.github/workflows/` | `ci.yml` (tests, frontend build, compose check, image build) and `cd.yml` (publish to GHCR, deploy to the Zephyrus) |
| `scripts/` | `deploy.bat`, `add-runner.sh`, `init-env.sh`, `photon_import.sh`, `fetch_tiles.sh`, `fetch_map_assets.sh`, `install-tiles-cron.sh`, `build_osrm.sh`, `add-date.ps1`, one-off cleanup SQL |
| `docs/` | `PLAN.md` (design + phases), `OPERATIONS.md` (running it), `API.md` (routes), `SHORTCUT.md` (phone Shortcut) |
| `Roadmap.md`, `status.md` | What to build next, and what is true now |
| `improvements/` | Daily import-check and roadmap-run reports |
| `import-tester/` | Local tool that runs the import on a link without saving anything |
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
