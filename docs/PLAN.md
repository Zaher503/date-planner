# Date Planner: links -> places/events on a map, plus interest-matched discovery

## Context

Zaher saves date ideas as TikToks, event pages and map links, and they get lost in camera rolls and chats. This service takes any of those links (or plain text or a screenshot), works out the place or event (name, address, coordinates, price, dates, duration), and pins it on a fast map that he and his partner share. Every 3 days it also crawls free sources for nearby events, scores them against their interests (seed tags plus a learned embedding profile), and puts good matches in a "Suggested" inbox with a Home Assistant push.

Constraints: everything runs on the **Zephyrus** (RTX 3070 8 GB, 16 GB RAM, Debian 13), only free services (no trials, nothing that needs a card), it lives behind Caddy and Authentik at **dates.zkocr.com**, and it shows up in **Homarr**. Recipe Box (`~/recipebox` on the Zephyrus, documented in `~/.claude/skills/homelab/recipe-box.md`) already solves video download, Whisper, the Ollama vision model and the Cloudflare browser fallback, so this app reuses those patterns and shares its Ollama container.

## Status (updated 2026-10-10, end of session 1)

**Phases 1, 2 and 3 are done and deployed on the Zephyrus. Next: Phase 4 (UI).** This file (`docs/PLAN.md` in the repo `C:\Users\z503\Desktop\Date planner`, local git only, one commit per task) is the main copy of the plan; keep it updated as phases finish. The README has the current layout, commands and what works.

| Phase | State |
|---|---|
| 1 Foundation | Done. Compose project `dates` (db, api, worker), Alembic, `/healthz`, keyed `/api/add`, identity header trusted only from the NAS, `scripts/deploy.sh` |
| 2 Geo infra | Done. Photon US db (14 GB), SoCal PMTiles (487 MB, `/srv/dateplanner/tiles/region.pmtiles`), OSRM car + foot (SoCal), SearXNG. `/api/health/services` all green |
| 3 Ingestion fast path | Done. TikTok, maps links, JSON-LD pages, free text; resolver; dedup/merge; review API. Golden set 28/28, 0 wrong auto-accepts |
| Ticketmaster adapter | Built and tested, **off until Zaher adds a free key** (`TICKETMASTER_KEY` in `~/dateplanner/.env`) |
| 4 to 9 | Not started |

**Answers given after the quiz:** partner is **Katherine** (HA `mobile_app_katherines_phone`, already in NOTIFY_TARGETS; add her to the Authentik `dates` group in Phase 6). Radius is **40 km** (HA uses miles, so show miles in the UI). Home = HA `zone.home` = Los Angeles (34.0461, -118.3265). Big downloads were approved and are done.

### Changes made during the build (the sections below are the original plan; these override them)
- **DB image:** `pgvector/pgvector:pg17` + `postgresql-17-postgis-3` (postgis/postgis:17-3.5 is bullseye, which PGDG no longer serves).
- **Schema additions:** `item_sources` link table (a list video pins many places; `sources.place_id/event_id` were dropped), `candidates.place_id` + `item_index`, `events.recurrence_text`. Migrations: `2c0040aef50e` initial, `7b1e2c9d4a10`, `c3d4e5f6a7b8`.
- **TikTok fast path is richer than planned:** the public page JSON has `stickersOnItem` (on-screen text, list items), `poi`, mentions, `suggestedWords`, and TikTok's own auto-caption WebVTT. Most TikToks need no download and no Whisper. Phase 5 slow path is only for videos without captions/stickers.
- **Address geocoding:** Photon has few US house numbers, so stated addresses fall back to **public Nominatim** (1 req/s, cached 90 days, interactive adds only, never discovery). House number must match and the street name must match; same-numbered addresses in several cities are disambiguated by distance to the stated area or home.
- **Resolver rules learned from the golden set:** strict name similarity (distinctive words, repeated words counted once, short names exact); auto-accept needs name >= 0.8 or an exact address/pin; candidates more than 300 m from an exact stated address lose 0.3; namesakes beyond 200 km capped; venue websites and search-snippet addresses (only snippets that name the venue) as fallback; "inside" field pins a venue inside another at its host; whole-city pins are refused; vague extras dropped from single-place posts; account handles turned into readable names.
- **No invented numbers now also covers street addresses** (the model sometimes recalled an address the text did not contain).
- **Ingest jobs** run one at a time in the worker's GPU lane; unrecoverable links fail without retry.
- **Ops lessons:** the Zephyrus hard-powered-off during a 16-thread OSRM build (likely thermal), so `build_osrm.sh` uses 4 threads and long jobs run under `setsid nohup`. Docker's embedded DNS went stale after the reboot, so compose pins DNS to 192.168.0.70 and 1.1.1.1.
- **Embeddings** (nomic-embed-text) are deferred to Phase 7; the model is not pulled yet. Recipe Box's Ollama has `OLLAMA_MAX_LOADED_MODELS=1`, so the embed model swaps with gemma4.
- The DB holds about 20 real places from the Phase 3 tests (5 in review), kept as sample data for the Phase 4 UI.

### Decisions from the quiz
| Topic | Choice |
|---|---|
| Codebase | New app (this folder, local git only). Copies Recipe Box fetch/transcribe ideas and shares `recipebox-ollama` plus a GPU lock |
| Inputs | TikTok/Shorts, event pages, Google/Apple Maps links, plain text and screenshots. **Instagram is a review stub only** |
| Model | **Places** (permanent) and **Events** (dated, usually at a place) |
| Users | Zaher and Katherine. Access through an Authentik group `dates`. Shared map, per-person status, rating and notes |
| Paid APIs | None. Free keys only if free forever (checked below) |
| Place lookup | Local Photon + Overpass + self-hosted SearXNG + patchright browser; the LLM arbitrates |
| Ambiguity | Auto-pick the best candidate, flag "Needs review" with alternatives when confidence is low |
| Area | Home from HA `zone.home`, 40 km default, slider to expand |
| Interests | Seed tags plus learning from saves, ratings and dismissals |
| Discovery | Every 3 days, results go to a Suggested inbox and a faded map layer, HA push for top matches |
| Stack | Postgres + PostGIS + pgvector, FastAPI, SvelteKit + MapLibre, self-hosted PMTiles, self-hosted OSRM, Docker Compose |
| Extras v1 | Calendar export, date-night picker, been/rating/notes, archive source video |
| Lifecycle | Past events auto-archive, places re-verified monthly, recurring events as RRULEs |
| Phone | Separate "Save to Dates" Shortcut with its own key |

## Free-source audit (checked 2026-10-10)

| Source | Verdict | Notes |
|---|---|---|
| TikTok oEmbed (`tiktok.com/oembed?url=`) | **Use** | No key. Returns caption (`title`), author and thumbnail in under a second. Fast path |
| TikTok page JSON | **Use** | The video page's rehydration JSON often has a **POI anchor** (place name, address, city). Best single signal when present. Plain GET, patchright fallback |
| yt-dlp | **Use** | Same as Recipe Box. Add a weekly auto-update (Recipe Box lacks one) |
| Ticketmaster Discovery API | **Use** | Free key, 5000 calls/day, plan for 2 req/s (docs disagree, 2 vs 5). ToS: no revenue, cache only "for reasonable periods", 24 h removal on request, may throttle calls not driven by users. One discovery run is about 10-30 calls. Purge Ticketmaster events 30 days after they end and link back to the ticket page |
| Resident Advisor | **Use** | Public first-party GraphQL, no key, keyed by area id. Undocumented, so the adapter must handle breakage |
| Luma (lu.ma) | **Use** | Public city "discover" JSON / `__NEXT_DATA__`. About a third of events hide the address |
| Eventbrite | **Scrape only** | The public search API was removed in 2020. City browse pages and event pages ship schema.org JSON-LD |
| Meetup | **Scrape only** | The API needs Meetup Pro (paid). Event pages have JSON-LD; groups have public iCal feeds |
| Any iCal/RSS feed | **Use** | City, library, parks and venue calendars, added in Settings |
| Saved venues ("venue watch") | **Use** | Every saved place with a website gets its events page re-scraped each run |
| OSM Nominatim (public) | **Interactive fallback only** | Max 1 req/s, no bulk or recurring use, no autocomplete |
| Photon (self-hosted) | **Use (primary geocoder)** | Apache-2.0, GraphHopper's weekly country dumps. Avoids public fair-use limits |
| Overpass (public) | **Use, cached** | Guideline is about 10k/day, about 100/day for recurring jobs. Cache 30 days |
| SearXNG (self-hosted) | **Use** | Private metasearch for finding venue websites. Limiter off, JSON output on, internal network only |
| Protomaps PMTiles | **Use** | Free daily build (ODbL, OSM attribution required). `pmtiles extract --bbox` for the region |
| OSRM (self-hosted) | **Use** | Geofabrik state extract, car + foot profiles |
| SeatGeek | **Pending** | Historically a free client_id, but the developer portal would not load during research. Adapter is built only if a key can be obtained at signup |
| PredictHQ | **Reject** | The API is only available during a 14-day trial; the free plan has no API |
| Yelp Fusion | **Reject** | Paid since 2024; the trial is evaluation-only |
| Google Places / Maps API | **Reject** | Needs a billing account |
| Foursquare Places | **Reject** | Only 500 free calls/month, then billed |
| Bandsintown / Songkick | **Reject** | Artist-only or closed to new apps |
| Instagram, Facebook events | **Reject** | Login walls (Instagram skipped by choice) |

## Architecture

```
iPhone "Save to Dates" Shortcut / web Add box / add-date.ps1
  -> Cloudflare -> NAS Caddy dates.zkocr.com
       POST /api/add (X-Dates-Key, 16 KB cap) -> app
       everything else -> Authentik forward_auth (group "dates") -> app
  -> Zephyrus :8820 (lb_policy first: .103 then .172, health /healthz)

Zephyrus compose stack ~/dateplanner (project "dates")
  api       FastAPI: JSON API + built SvelteKit + PMTiles (HTTP range) + ICS feeds
  worker    same image, nvidia runtime: job queue, Whisper, browser, scheduler
  db        postgis/postgis:17 + pgvector (named volume)
  searxng   + valkey (internal network only)
  photon    country dump (internal, heap capped)
  osrm-car, osrm-foot   region extract (internal)
  external network recipebox_default -> recipebox-ollama:11434 (gemma4:e4b, nomic-embed-text)
  HA REST (192.168.0.108:8123): zone.home, notify.mobile_app_*
```

- **Trusting identity:** the API reads `X-Authentik-Username` only when the request comes from the NAS (192.168.0.70). Other LAN clients get 403 except `/healthz` and key-checked `/api/add`. This is stricter than Recipe Box, which is open on the LAN.
- **GPU sharing:** a host flock at `/srv/gpu/gpu.lock`, mounted into the worker, is held around every GPU step. Until Recipe Box and the Transcriber also take that lock, the worker also polls `localhost:8800/api/jobs` and `:8810/api/status` and waits while they are busy (the Transcriber already does this). It unloads Ollama (`keep_alive: 0`) before Whisper, the same rule as Recipe Box.
- **Models:** `gemma4:e4b` (text + vision, JSON via the Ollama `format` schema, `think: false`), `nomic-embed-text` (768-dim embeddings), faster-whisper `large-v3-turbo` int8_float16.
- **Queue:** a Postgres `jobs` table with `SELECT ... FOR UPDATE SKIP LOCKED`. Running jobs are re-queued at startup. One GPU job at a time; CPU-only jobs (geocoding, scraping) run 2 at a time.
- **Scheduler:** APScheduler in the worker. Discovery every 3 days at 03:00 (+ jitter), past-event archive nightly, place re-verify monthly (batches), yt-dlp update weekly, home location refresh daily, `pg_dump` nightly.

## Ingestion pipeline (one link)

Stages are written to `jobs.stage` for live UI progress, as in Recipe Box.

1. **Normalize and route** (`ingest/router.py`): take the first URL from the shared text, follow redirects (every hop checked against private/LAN ranges, as Recipe Box `fetch.py` does), dedup by normalized URL, then classify: `tiktok | youtube | gmaps | applemaps | event_page | instagram(stub) | text | image`.
2. **Fast path, no download:**
   - TikTok: oEmbed caption + author, then page JSON for the POI anchor and location.
   - Maps links: expand `maps.app.goo.gl`, parse the name and `@lat,lng` / `!3d!4d` (Google) or `q=`/`ll=` (Apple) from the URL. No page load needed.
   - Event pages: schema.org JSON-LD `Event` / `LocalBusiness` (Eventbrite, Meetup, Luma, most venues), so no LLM is needed. Fallback: trafilatura text, then the LLM.
   - Text: the LLM goes straight to extraction. Image: gemma4 vision OCR, then extraction.
3. **LLM extraction A** on whatever text exists. A strict JSON schema: `kind`, `place_name`, `place_hints` (city, neighborhood, street), `event_title`, `start/end`, `recurrence_text`, `price_text`, `tags`, `confidence`. **Number rule from Recipe Box:** every price, date and time must appear in the source text, otherwise it is dropped and flagged.
4. **Resolve the place** (`resolve/`):
   - Photon search with a location bias at home (`lat/lon`), plus the hint city.
   - Overpass by `name~` within the radius for OSM tags (opening_hours, website, cuisine, price).
   - SearXNG `"<name> <city>"` to find the official site / Maps / Yelp URLs, then fetch the site (plain, patchright fallback) for JSON-LD address, geo, hours, priceRange and an events page.
   - **Scorer** (`resolve/scorer.py`): rapidfuzz name similarity, distance decay from home, category agreement with the LLM kind, number of agreeing sources, and a hint-city match. Above 0.75 it auto-pins; below that it pins with `needs_review` and stores the top 5 alternatives in `candidates`.
5. **Slow path, only if steps 2-4 did not reach the threshold:** yt-dlp download, then Whisper, then frame OCR (one frame every 2 s, at most 20 frames), then extraction B with everything, then resolve again. Target: fast path under 15 s, slow path 40-90 s.
6. **Event details:** duration from start/end; else the LLM reads it from the text; else a category default (concert 3 h, market 4 h, class 2 h) with `duration_estimated=true`. Price from `offers.price/lowPrice/highPrice`, the word "free", or `priceRange` ($-$$$$) for places.
7. **Tag + embed:** tags are chosen from a controlled vocabulary (category, vibe, setting, time of day, budget) plus up to 3 free tags. Embed a short canonical text ("title. category. tags. description").
8. **Dedup and merge:** places match on the same `osm_id`, or name trigram > 0.8 within 75 m. Events match on the same place, start within 60 min and title similarity > 0.7. A new source attaches to the existing item instead of making a duplicate.
9. **Archive media** (TikTok/YouTube): mp4 + thumbnail under `/srv/dateplanner/media/`.

User edits go into `user_overrides` (jsonb) and are re-applied after any reprocess. Recipe Box loses edits on reprocess; this avoids that.

## Discovery (every 3 days)

`discover/adapters/*` share one interface: `fetch(area, window) -> list[RawEvent]`. Each adapter has its own rate limit, backoff and health record (`adapter_state`), and a dead adapter never fails the whole run.

Adapters in v1: `ticketmaster`, `resident_advisor`, `luma`, `eventbrite_web`, `ical_feeds`, `venue_watch`, `searx_queries` (generated from top interest tags, e.g. "live jazz <city> this weekend", links into the event-page extractor), and `overpass_places` (new places in interest categories). `seatgeek` is added only if a key is obtained.

The run: fetch a 21-day window, normalize, geocode the venue (local Photon), dedup against the DB, then tag + embed in batches (one GPU lock), then score. Items scoring >= 0.6 become `suggested`. One HA push per run: "6 new matches. Top: Rooftop jazz, Sat 8pm, $15", with a deep link to the inbox. Items >= 0.85 are named individually (at most 3).

**Match score** (`match/score.py`), returned with a "why" breakdown:
`0.45 * cos(item, taste_vec) + 0.25 * weighted tag overlap + 0.15 * distance decay + 0.10 * time fit (learned weekday/evening preference) + 0.05 * source quality - penalty(disliked tags, dismissed-centroid similarity)`.
`taste_vec` per user plus a combined "us" profile: the weighted mean of saved items (+1), accepted suggestions (+1), ratings ((rating-3) * 0.5) and the seed-tag embeddings for cold start. Dismissals feed a separate negative centroid.

## Data model (Postgres 17, PostGIS, pgvector, pg_trgm)

SQLAlchemy 2 + GeoAlchemy2 + pgvector-python, with **Alembic** migrations from day one. All times are `timestamptz` (UTC) plus an IANA `tz` column.

| Table | Key columns | Indexes |
|---|---|---|
| `users` | id, authentik_username (unique), display_name | |
| `settings` | singleton: home geom, home_source (ha/manual), radius_km=40, thresholds, discovery cadence, notify targets | |
| `places` | id uuid, name, category, geom geography(Point), address jsonb, address_text, osm_type+osm_id (unique), website, phone, opening_hours (OSM syntax), price_level 0-4, description, tags text[], embedding vector(768), origin (manual/discovered), review_status (ok/needs_review/suggested/dismissed), confidence, closed bool, last_verified_at, user_overrides jsonb, search tsvector (generated) | GIST(geom), GIN(tags), GIN(search), GIN trgm(name), HNSW(embedding cosine) |
| `events` | id, place_id fk null, geom (denormalized for speed), title, description, starts_at, ends_at, duration_min, duration_estimated, all_day, rrule, tz, price_min, price_max, currency, is_free, price_text, ticket_url, tags, embedding, origin, review_status, status (scheduled/cancelled/archived), user_overrides, search | GIST(geom), btree(starts_at), GIN(tags), HNSW(embedding) |
| `occurrences` | event_id, starts_at, ends_at (RRULEs expanded 120 days ahead, nightly) | btree(starts_at), GIST via a join to events |
| `sources` | id, url_norm (unique), kind, adapter, external_id, raw jsonb (oEmbed/yt-dlp/JSON-LD), caption, transcript, ocr_text, submitted_by, place_id, event_id, fetched_at | |
| `media` | id, source_id, kind (video/thumb/photo), path, bytes, sha256 | |
| `candidates` | source_id, provider, payload jsonb, score, chosen | |
| `jobs` | id, type (ingest/discover/refresh/embed/backfill), payload, status, stage, pct, attempts, error, run_after, locked_at | partial index on status in (queued,running) |
| `user_item_state` | user_id, item_type, item_id, status (want/going/been/dismissed), rating 1-5, notes, visited_at | PK(user_id,item_type,item_id) |
| `tags` | slug, label, group, embedding | |
| `interests` | user_id null = shared, tag slug, weight, kind (seed/learned) | |
| `taste_profiles` | user_id null = "us", vec, neg_vec, n_signals, updated_at | |
| `plans` | id, title, date, window, budget, vibe tags, stops jsonb (item, arrive, leave, travel_min, mode), created_by | |
| `discovery_runs`, `adapter_state` | per-run stats, per-adapter cursor/backoff/last_ok/last_error | |
| `http_cache` | key hash, body, fetched_at, ttl (Photon 30 d, Overpass 30 d, SearXNG 7 d, oEmbed 1 d) | |

Map reads go through one endpoint, `GET /api/map?bbox&filters`. It returns compact GeoJSON (id, type, category, title, start, price, score, status) from a single SQL query (`ST_Intersects` with the bbox, a date filter through `occurrences`, and `ST_DWithin` from home). Target: under 50 ms DB time.

**Backup:** nightly `pg_dump -Fc` into `/srv/dateplanner/backups` (keep 7). The NAS pulls `/srv/dateplanner` (dumps + media, excluding tiles/osrm/photon) through a forced-command `rrsync -ro` account `datespull`, keeping 5 snapshots. Same pattern and script shape as `recipebox-pull.sh`. `appdata-add dateplanner /srv/dateplanner` exposes it on the SMB share.

## API (FastAPI, :8820)

`POST /api/add` (key) and `POST /api/ui/add` (Authentik); `GET /api/jobs` (live progress); `GET /api/map`; `GET /api/list` (same filters, sorted by date/score/distance); `GET/PATCH/DELETE /api/items/{type}/{id}`; `POST /api/items/{type}/{id}/reprocess`; `POST /api/items/{id}/resolve` (pick a candidate); `PUT /api/items/{type}/{id}/me` (status, rating, notes); `GET /api/inbox`; `POST /api/inbox/{id}/accept|dismiss`; `GET/PUT /api/interests`; `GET/PUT /api/settings`; `GET /api/sources/health`; `POST /api/discover/run`; `POST /api/plans/suggest` and CRUD; `GET /api/items/{id}.ics`; `GET /cal/{token}.ics` (subscribable feed of "Going" items, secret token, bypasses Authentik); `GET /widget` (compact page for Homarr); `GET /tiles/region.pmtiles` (range); `GET /healthz`.

## UI (SvelteKit static adapter, MapLibre GL + pmtiles protocol)

Phone-first, light and dark themes, **no emojis** (lucide icons), installable PWA.

- **Map screen:** full-bleed map. Pins are colored by category and shaped by type (place = circle; event = rounded square with a date badge). Clustering is on. Suggested items are outlined and faded, needs-review items get a small marker.
- **Top bar:** search plus a horizontal filter-chip row: **When** (Today, This weekend, Date range, Open now), **Price** (Free, $, $$, $$$, max slider), **Tags** (multi-select, AND), **Match >= X%**, **Distance** (slider 5-150 km, default 40, from home or the current location), **Status** (Want, Going, Been, Suggested). Filters live in the URL so views can be shared and bookmarked.
- **Bottom sheet (phone) / left panel (desktop):** a list synced to the map viewport. Tap to fly to the pin.
- **Detail card:** title, when + duration (marked "estimated" when it is), price, address with Apple/Google Maps deep links, hours and open-now state, embedded source video or thumbnail, tags, match score with "why", Want/Going/Been, star rating, notes, Add to calendar, Edit, Reprocess, Delete. Needs-review items show the alternative candidates on a mini map, one tap to choose.
- **Inbox:** suggestion cards, swipe or tap Accept/Dismiss (keyboard J/K/A/D on desktop). Every action trains the profile.
- **Add:** paste box plus live job toasts (Reading caption, Finding place, Transcribing, Pinned). A placeholder pin drops as soon as coordinates exist.
- **Plan (date-night picker):** pick date, time window, budget, vibe tags and a start point. It returns 2-3 itineraries (an anchor event or place, plus food that is open at that time near it, plus an optional drinks/dessert stop) with OSRM drive/walk times. Save the plan, export it to the calendar.
- **Settings:** seed interest chips, default radius, notification threshold and target phones, source toggles with health dots, custom iCal/RSS feeds, Ticketmaster key status.
- **Speed budget:** app shell under 80 KB gz; MapLibre loaded once and cached by the service worker; tiles served locally with HTTP range; the map query is debounced at 150 ms on pan; the list is virtualized.

## Homelab integration

- **Caddy (NAS):** a `dates.zkocr.com` block modeled on `food.zkocr.com` (`handle @add` for POST `/api/add` + `/cal/*` passthrough, then `import authentik_auth`, `reverse_proxy` .103 then .172, health check `/healthz` every 10 s). Back up the Caddyfile first (heredoc rewrite, no `sed -i`). Cloudflare CNAME `dates` -> `zkocr.com`, proxied.
- **Authentik:** proxy provider "Dates Proxy" (forward_single, cookie domain `zkocr.com`), application `dates`, bound to a new group **`dates`** (Zaher; the partner is added when chosen), attached to the `external-proxy` outpost.
- **Homarr:** app tile "Dates" on the `dashboard` and `family` boards (DB insert pattern from `homarr.md`, with a `db.sqlite` backup first), ping `http://192.168.0.172:8820/healthz`. Widget: an iframe of `https://dates.zkocr.com/widget` ("This weekend: N plans, M suggestions", next 3 items). This works because the Authentik cookie is shared on `zkocr.com`. Check the v2.4 widget list for a native JSON widget first. Family-board members outside the `dates` group see the tile but are refused by Authentik.
- **Home Assistant:** `$HA_TOKEN` in `~/dateplanner/.env` (mode 600). `GET /api/states/zone.home` for home; `notify.mobile_app_<device>` for pushes (device names looked up at build time).
- **Docs:** a new `~/.claude/skills/homelab/date-planner.md` in the same shape as `recipe-box.md`, plus pointers in `zephyrus.md` and the skill index.

## Repo layout (this folder, local git only)

```
backend/app/
  main.py config.py gpu.py worker.py scheduler.py browser_fetch.py
  db/ (models.py, session.py)   migrations/ (alembic)
  api/ (add, map, items, inbox, interests, plans, ics, widget, settings)
  ingest/ (router, tiktok, youtube, maps_links, event_page, text_image, media, transcribe, ocr)
  resolve/ (photon, overpass, searxng, website_jsonld, scorer)
  llm/ (ollama.py, schemas.py, prompts/, verify_numbers.py)
  discover/ (runner.py, adapters/*.py)
  match/ (embed, profile, score)   plan/ (osrm, picker)   notify/ha.py
backend/tests/ (unit + fixtures/ with saved oEmbed, JSON-LD, TikTok JSON, RA/Luma payloads)
frontend/ (SvelteKit: routes map, inbox, plan, settings; lib/map, lib/filters)
deploy/ compose.yaml, Dockerfile.app, Dockerfile.db, searxng/settings.yml, caddy-snippet.txt, .env.example
scripts/ deploy.sh (git archive HEAD | ssh zephyrus tar -x, then compose up -d --build),
         fetch_tiles.sh, build_osrm.sh, photon_import.sh, datespull-backup.sh, add-date.ps1
docs/ SHORTCUT.md, OPERATIONS.md
```

Data on the Zephyrus: `/srv/dateplanner/{media,tiles,osrm,photon,backups}`, Postgres in the named volume `dates-pg`.

## Build phases (one commit per task)

1. **[DONE] Foundation:** git init, compose skeleton (db, api, worker), Alembic schema above, `/healthz`, deploy script, `.env.example`, port 8820 on the Zephyrus.
2. **[DONE] Geo infra:** PMTiles regional extract, Photon country dump, OSRM car + foot builds, SearXNG config. Measured RAM: whole stack about 4.4 GB (Photon 0.7, OSRM car 1.5, foot 1.7).
3. **[DONE] Ingestion fast path:** router, TikTok page JSON + stickers + auto-captions, maps links, JSON-LD event pages, extraction with number and address verification, resolver + scorer, candidates and review API, dedup/merge. Golden set `backend/tests/golden.json` (22 links, 28 places): 28/28, 0 wrong auto-accepts. Run `docker compose exec worker python -m app.eval` after any extraction/resolver change.
4. **[NEXT] UI v1:** map, filters, list, detail card, add box with live progress, review picker, per-user status/rating/notes.
   - Already in place: `/api/ui/add`, `/api/jobs` (live stages), `/api/review` + `/api/places/{id}/resolve`, `/api/me`, `/api/health/services`, tiles file at `/srv/dateplanner/tiles/region.pmtiles` (mounted at `/data/tiles` in the containers).
   - Still to build in the backend: `GET /api/map?bbox&filters` (compact GeoJSON), `GET /api/list`, `GET/PATCH/DELETE /api/items/...` (PATCH writes keys into `user_overrides`), `PUT /api/items/.../me` (user_item_state), `POST .../reprocess`, a range-capable route serving `region.pmtiles`, and serving the built SvelteKit app from the API image (multi-stage Dockerfile with Node). Thumbnails: TikTok thumbnail URLs expire, so either proxy/cache them or wait for Phase 5 media archive.
   - Testing the UI before Phase 6: the API only trusts identity from the NAS, so use `DEV_USER=zaher` in `.env` temporarily, or reach it through the NAS (`ssh` + curl with `X-Authentik-Username`). Never leave `DEV_USER` set once it is public.
5. **Slow path + inputs:** yt-dlp, Whisper turbo, frame OCR, media archive, screenshot input, Instagram stub (done in Phase 1). GPU lock + Recipe Box/Transcriber polling already exists in `app/gpu.py` (lock not yet adopted by Recipe Box/Transcriber themselves). Worker needs `runtime: nvidia` added for Whisper. Free text input already works.
6. **Edge wiring:** Caddy block, Cloudflare, Authentik provider/app/group (add Katherine), the "Save to Dates" Shortcut + `add-date.ps1`. Header trust check is done (Phase 1).
7. **Interests + discovery:** tag vocabulary, seed picker, embeddings, profiles, score with "why", adapters (Ticketmaster adapter + dry-run CLI done, waiting on key; then RA, Luma, Eventbrite web, iCal, venue watch, SearXNG queries, Overpass places), scheduler, inbox, HA push (`app/notify/ha.py` exists).
8. **Planner + calendar:** OSRM client, itinerary picker, plan CRUD, per-item ICS, subscribable feed.
9. **Lifecycle + ops:** RRULE occurrences, nightly archive, monthly re-verify (closed places), Ticketmaster 30-day purge, weekly yt-dlp update, pg_dump + NAS pull backup, SMB appdata, Homarr tile + widget, homelab skill doc.

## Verification

- **Unit (pytest):** scorer ranking, number verification, URL normalize/dedup, maps-link parsing, duration defaults, RRULE expansion, match score, picker constraints (open hours, budget, travel time). Fixtures are saved responses, so tests never hit the network.
- **Golden set:** `python -m app.eval golden.yaml` reports correct place %, address, coordinates within 100 m, price and date accuracy, and fast vs slow path timing. The target is at least 85% correct place on TikToks before moving on.
- **End to end:** `curl -X POST https://dates.zkocr.com/api/add -H "X-Dates-Key: ..."` with a TikTok, then watch `/api/jobs` stages and confirm the pin in `/api/map`. Repeat with a Maps link, an Eventbrite page and a screenshot.
- **Access checks (same as Recipe Box):** no login redirects to Authentik for UI/API/media; `/api/add` with no or a wrong key gives 401; a body over 16 KB gives 413; a direct LAN hit on :8820 from a non-NAS IP gets 403 on the API.
- **Discovery:** `python -m app.discover --dry-run` prints counts per adapter and the top 10 scored items with "why", without writing. Then one real run, checking the inbox and that exactly one HA push arrives.
- **GPU coexistence:** start a Recipe Box job and a Dates slow-path job together; there should be no CUDA OOM, and the Dates job waits for the lock.
- **UI:** Browser pane at mobile and desktop sizes. Pan and filter stay responsive with 500 seeded items; check Lighthouse performance on the phone profile.
- **Backup restore:** restore the latest dump into a scratch database and compare row counts; restore one media folder.

## Risks and mitigations

- **TikTok or site changes break scraping:** fast path and slow path are independent, yt-dlp updates weekly, adapter health is shown in Settings, and failures become review stubs, never silent drops.
- **Ticketmaster ToS:** personal, non-commercial use, about 30 calls per run, link back to the ticket page, purge after the event.
- **16 GB RAM:** cap the Photon heap, use a state-sized OSRM extract, run discovery at 03:00 when Recipe Box is idle.
- **Ambiguous place names:** location bias + review queue + alternatives, and every manual choice is stored, so a repeat link resolves instantly.
- **Partner account:** the design is group-based (`dates`), so adding the partner is one Authentik group membership.
