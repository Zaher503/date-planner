# Status

Facts about the project as of **2026-11-09** (v3.36 on `main`), from a sweep of the code, docs, branches and import reports. What to build next is in [Roadmap.md](Roadmap.md); this file is only what is true now. The auto task refreshes the sections it touched at the end of each run and changes the date above.

Where this file disagrees with `README.md` or `docs/PLAN.md`, this file wins (they are stale, see Docs).

## What works (deployed, live at dates.zkocr.com)

- **Import:** TikTok, YouTube, Google/Apple Maps links, event pages (JSON-LD, embedded descriptions, Eventbrite), plain text and screenshots become place/event items. Local model (gemma4:e4b through the AI hub; an OpenRouter text-only option exists in config), strict "no invented numbers" check, resolver with Photon, Nominatim and SearXNG, website lookup for hours, phone, prices and photos. Golden set: 28/28.
- **Import fixes from the daily check:** sale banners on a venue page ("Save 15%...") become part of the venue's offers instead of events (PR #30, open), footer address and phone of a venue's site, `Sept.` dates, $0 ticket ranges and "free donuts", Eventbrite embedded description, already-past events flagged on import, own ticket link per event, `POST` endpoint that saves hand-checked import items.
- **Archive and age (PR #12, merged 2026-10-23):** past one-off events move to an Archive view (computed per request); `events.min_age` (18/21) read from page text and editable. Migration `c9d0e1f2a3b4` runs on deploy. **Not yet checked on the live site.**
- **Exhibitions and the Archive button (PR #22, open 2026-10-30):** a long-running event (an exhibition) keeps its start and end dates at import instead of becoming an "ongoing until" series, and an event with only a closing date also ages into the Archive. Event detail has an Archive / Restore button (sets `status`). Not deployed until #22 merges.
- **Importer provenance and flexible flags (PR #18, merged 2026-10-26):** `import_info` on places and events (importer version, engine, model, earlier reads), shown only with `?debug=true`. `ingest/completeness.py` splits gaps into needed / check / optional; an event is marked for review only for its own problems (no date or repeat pattern, untrusted date, already past).
- **Standing venues and repeating events (PR #19, merged 2026-10-26):** places can be marked standing and their page is re-read weekly (`watch_scan`, 03:40); events the page drops are archived, never deleted. `recurrence.py` turns explicit patterns ("every Tuesday at 6pm", "every other Saturday", "third Friday") into an RRULE; `occurrences` is expanded 120 days ahead on save and nightly (03:55). The place page lists its events. Nothing is marked standing yet, so no scan has run.
- **Live data cleanup (2026-10-30, done by hand on prod):** 56 places / 30 events became 43 / 22 (`scripts/cleanup-2026-10-30.sql` and `cleanup-2026-10-30-review.sql`). Rooms and exhibits that were saved as places (Cinegrill, Library Bar, Spare Room, Marilyn Monroe, The Horror Show, the Tutu Fun workshops, Sender City) are events on their parent venue; shows saved as places (The Empire Strips Back, Creep LA) are an event or deleted; wrong cities and websites fixed; 7 street-only addresses given street numbers; Academy exhibits have real dates; nothing is marked needs_review. Backups: `/srv/dateplanner/backups/pre-cleanup-2026-10-30.dump` and `pre-review-fixes-2026-10-30.dump`.
- **Date-night planner API (PR #15, merged 2026-10-26):** `/api/plans/suggest` and plan CRUD are registered and tested (25 API tests, documented in `docs/API.md`). Not yet checked against the live database; there is no Plan page in the UI, and the `ics` link in a plan is a placeholder.
- **Map UI:** SvelteKit + MapLibre, self-hosted PMTiles with a fallback to the live basemap, teardrop pins with category icons, rainbow cluster pins, per-category pin colours, list, detail/edit, Add box with live job toasts, review picker, per-user status/rating/notes, occurrence calendar, settings, PWA shell, version label.
- **Redesign (`UI-08`, PR #24, 2026-10-31):** list and map with the search bar floating over the map. A Filters drawer over the list (phone: a tall sheet) holds Saved status (Want to go, Going, Been, Needs review), When (Today, This weekend, Next 7 days), five category groups, Distance (home or my location) and Archive; active filters show as removable tokens. Details float over the map on desktop; on phones the card expands upward. Type, Price, Tags and the other When options are no longer in the interface (URL and API still accept them, `UI-10`). **Not yet checked on the live site or a real phone** (`UI-09`).
- **Platform:** Compose stack on the Zephyrus (db, api, worker, photon, osrm-car, osrm-foot, searxng, browser, tester), CI + CD on push to `main` with a self-hosted runner, Caddy + Cloudflare + Authentik (group `dates`: Zaher and Kathy), Homarr tile, weekly map-tile refresh (cron on the Zephyrus), keyed import-tester service for the daily check.
- **Tests:** backend 391 passed (2026-11-09), frontend 33 passed and svelte-check clean (as of PR #24). CI runs ruff with its default rules plus import sorting (`backend/ruff.toml`, ruff 0.17.4) once the `QA-01` PR merges; until then only the minimal error rules (`E9,F63,F7,F82`).

## Half-built (code exists, not wired up)

| Area | State |
|---|---|
| iCal feeds | Adapter is in `ADAPTERS` and the feed list is read and written with `GET/PUT /api/discover/feeds` (PR of 2026-11-03, open). Settings has no screen for it yet (`DS-10`), and nothing runs it on a schedule (`DS-03`). |
| Discovery | Ticketmaster, Resident Advisor, Luma, Eventbrite web adapters merged. `discover/run.py` only has `--dry-run`: nothing writes events to the database, nothing schedules it. |
| HA push | `notify/ha.py` has `push()`; nothing calls it. |
| Interests and taste | Tables exist (`tags`, `interests`, `taste_profiles`, `discovery_runs`, `adapter_state`, `http_cache`); no code reads or writes them. `nomic-embed-text` is not pulled. |
| Standing venues | Built (#19) but nothing is marked standing, so no scan has run on prod. Venue-specific parsers (`watch_parser`, "step D") are not written. |
| Recurring events | Explicit patterns become an RRULE and are expanded nightly (#19). Vague words ("weekly", "monthly") stay as text only. |

## Not started

- Inbox (Suggested) API and UI, interests picker, match score with "why".
- Adapters: SearXNG queries, Overpass new places (the venue watch is the standing-venue scan above). SeatGeek only if a key can be had.
- ICS: per-item `.ics`, subscribable `/cal/{token}.ics` feed.
- Lifecycle: monthly re-verify of places (closed venues), Ticketmaster 30-day purge, weekly yt-dlp update is written (worker job `ytdlp_update`, Sundays 03:10, PR of 2026-11-07, not deployed yet; the image still pins `yt-dlp>=2025.1.1` as the fallback).
- Ops: nightly `pg_dump` is written (worker job `backup`, 02:30, keeps 7 `dates-*.dump`, PR of 2026-11-05, not deployed or checked on prod yet); NAS pull backup is not (earlier dumps are manual, in `/srv/dateplanner/backups`), SMB appdata share, Homarr widget, `homelab/date-planner.md` skill doc. The scheduler runs `backup` (02:30, once deployed), `refresh_home` (04:10), `watch_scan` (03:40) and `expand_occurrences` (03:55).

## Open import-quality gaps (from the daily reports, plain words)

- Page-wide address and phone in a listing page's footer now reach every event on text-read pages (checked live 2026-11-01, `IM-01`); pages with JSON-LD events do not get the footer yet (`IM-25`). The same page shows a hotel's $49 destination fee as an event price (`IM-26`) and has four events with room names as titles and no dates (`IM-05`).
- Recurring shows with an explicit pattern now become an RRULE (#19); show times written as "8 PM" or "doors 7, show 8" are still not turned into a start time (2026-10-17, `IM-04`).
- A street without a number is accepted as an address, and the local Photon can return a wrong match for a full street address (an AM radio station, a ranger station, a law firm); 7 live places needed fixing by hand (2026-10-30, `IM-22`).
- Rooms, exhibits and workshops inside a bigger venue were saved as separate places, some geocoded to other states (2026-10-30, `IM-23`).
- Event titles missing when only a room name is given; a $0 price on a magic show not checked (2026-10-17).
- Opening hours that exist only on third-party pages and conflict are left empty; no "from another site, please check" label (2026-10-19).
- Tour pages (day rides, evening rides, durations) are not read (2026-10-19).
- "Free" can still be read from a site's menus when a page has no price (2026-10-20; partly fixed by #11).
- An article that links an event's own website: the venue's site is used instead, and the ticket link is lost (2026-10-21).
- Side attractions in an article become extra items, one on the wrong street (2026-10-21).
- The price shown is the original ticket price while the page says the event is off sale (2026-10-23).
- A free line in a price list ("toddlers free") no longer marks a paid place Free; the range still starts at $0 (2026-10-25, `IM-20`).
- Drive-in showtimes and "box office opens an hour before" are not read (2026-10-25, `IM-21`).
- Single-business pages read only from structured data get no description, minimum age or booking link; the branch-name-only title is fixed (2026-10-31, `IM-24`).
- City and county park pages: the City Hall footer address was saved as the park's address (Oak Canyon Nature Center); footers that name a city or county are now ignored (PR of 2026-11-04, not yet live), but phone, hours and free entry are still not found (`IM-29`, `IM-30`).
- Venue sites: tour and package pages are now opened and price-card lines recovered (PR for 2026-11-02, not yet live), but the model still leaves "Starting at $99" prices empty (`IM-27`); structured hours can override the page's fall hours (`IM-28`).
- Instagram is a review stub only (by choice).

## Waiting on Zaher

- **Urgent (2026-11-08):** the Zephyrus GPU driver is hung (hundreds of stuck `nvidia-smi` processes, load about 563); the AI hub answers 502, so imports that need the model fail. Reboot the Zephyrus (`LC-11`). Still down on 2026-11-09: it answers ping but SSH, the tester and the AI hub time out, and the public tester gives 503.
- Check the live site after the 2026-10-23 deploys: Archive chip, 21+ line, teardrop pins, rainbow pin, Settings > Pin colors.
- Set up the "Save to Dates" Shortcut on both phones (`docs/SHORTCUT.md`).
- Try the video slow path once with a TikTok that has no captions (Whisper through the hub has never run on a real video).
- Service worker does not register in the Claude browser pane; check in real Chrome on the phone before relying on Add to Home Screen.
- Drop the leftover `dates_dev` database in the prod Postgres.
- Clean up git: 8 stale `auto-improve/*` worktrees in the Temp folder, plus local and remote branches that are fully merged (`consolidate-pending-work`, `import-website-lookup`, `verified-import-endpoint`, `openrouter-nemotron-test`, `feature/keyed-import-tester-service`, the merged `auto-improve/*`).

## Docs that are out of date

- `README.md` status table and "Next step" (says phases 4-5 not checked, Phase 7/8 mostly to do; layout table lists only some routers).
- `docs/PLAN.md` header status (says phases 4-5 undeployed, "local git only", two unmerged worktree branches). The phase list at the bottom is still the best design reference.
- `docs/TODO-ZAHER.md` (dated 2026-10-12): replaced by "Waiting on Zaher" above and the `[Z]` items in the Roadmap.

## Risks to keep in mind

- Migrations (PRs #12, #18, #19) went to production with tests only; the CD health check is the only live check.
- The cleanup scripts are one-off edits to prod rows; a reread of an affected link on old importer code could overwrite them until #22 is deployed.
- The public `/tester` route is key-protected only (`TESTER_KEY`); rotate on any leak.
- `DEV_USER` must never be set in prod (skips Authentik).
- Photon, OSRM and tiles cover Southern California only; items outside it will not resolve well.
- One GPU lane shared with Foodbox and the Transcriber: discovery and re-verify jobs must run at low priority.
- A hung GPU driver takes every model-based import down with no alert (2026-11-08); nothing watches the hub yet (`LC-12`).
