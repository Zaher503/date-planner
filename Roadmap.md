# Roadmap

The single list of what to build next. The daily auto task reads it to decide what to do, and edits it as it works: it may mark items done, split or expand them, reorder, drop stale ones and add newly found work. Zaher edits it too. Facts about the current state are in [status.md](status.md); the design is in [docs/PLAN.md](docs/PLAN.md).

## How to use (auto task)

1. **Alternate.** Look at the newest entry in **Done**. If it is tagged `(check)`, do a roadmap item today; otherwise do the daily real-link import check (the routine in the task prompt). An import check that finds a gap adds a new `IM-` item here; a small fix is done in the same run, a bigger one stays on the list.
2. **Pick the item.** Read **Now** top to bottom. Take the first item that is not `[Z]` and whose `Deps` are all `[x]`. If **Now** is empty, take the first such item from the Backlog, top of the track that has been waiting longest. A `[!]` item (something broken in production or in tests) always goes first.
3. **One run = one item or one sub task.** If an item is bigger than one run, do its first unchecked sub task, tick it, and leave the item `[~]`. Write the code, add or update tests (backend `pytest`, frontend `npm test` and `npm run check`), run them, then mark the item.
4. **Mark it.** Change the marker, and when an item is fully finished move a one-line entry to **Done** (newest first: date, tag `(item)` or `(check)`, the code tag, what changed, PR number).
5. **Refill Now** to about 6 items when it drops below 3, mixing tracks. Add new work to the Backlog with the next free number in its track. Never reuse or renumber a code tag.
6. **Expand when needed.** An item that turns out vague or large gets sub tasks (`IM-07.1`, `IM-07.2`, ...). Say why in one line under the item.
7. **`[Z]` items need Zaher.** Do not build them. Write the question and your recommendation under the item, and do something else.
8. **Report the roadmap changes** in the PR description under "Roadmap changes" (marked, added, split, dropped, reordered) and in the day's file in `improvements/`. Update the touched sections of `status.md` and its date.
9. **Every 5th roadmap run** re-read the whole list: stale items, wrong order, track balance, items the code already did.
10. The rules in the task prompt still apply: work in a worktree, never push to `main`, never edit `frontend/VERSION`, no `Co-Authored-By`. Roadmap and status edits ride in the day's PR. If an earlier `auto-improve/*` PR is still open, start from the newest one's `Roadmap.md` and `status.md` so marks accumulate, and say so.

Markers: `[ ]` todo, `[~]` in progress, `[x]` done, `[-]` dropped (say why), `[Z]` needs Zaher, `[!]` broken.
Tracks: `IM` import quality, `DS` discovery, `IB` inbox and interests, `PL` planner and calendar, `LC` lifecycle and ops, `UI` app and mobile, `QA` tests and CI, `DOC` docs and housekeeping.
Rules that never bend: no paid services, no invented numbers in imports, user edits survive reprocess, nothing in the app breaks the shared map for Zaher and Katherine.

## Now

- [~] `IM-01` Page-wide address, hotel name and phone from a listing page's footer apply to every event on it (report 2026-10-17). Test with the saved fixture.
  - [x] `IM-01.1` Footer is passed to the extractor for pages read as text, with a rule that it applies to every event without its own address (2026-10-26, unit tests only).
  - [ ] `IM-01.2` Rerun the Hollywood Roosevelt link on the live tester after the PR is deployed; if the model still ignores the footer, copy a single footer address onto events that have none in code. Pages that carry JSON-LD events do not get the footer yet.
- [ ] `DS-01` Wire the iCal adapter: add `ical_feeds` to `ADAPTERS`, feed list kept in settings (API only), tests from a saved feed.
- [ ] `LC-01` Scheduler basics: nightly `pg_dump -Fc` into `/srv/dateplanner/backups` (keep 7) as a worker job, plus a weekly `yt-dlp` self-update.
  - [ ] `LC-01.1` Backup job and its test (command built correctly, retention).
  - [ ] `LC-01.2` Weekly yt-dlp update job.
- [ ] `QA-01` Widen the CI lint from `E9,F63,F7,F82` to the default ruff rules plus `I` (imports); fix what it finds without changing behaviour.
- [ ] `DOC-01` Rewrite the `README.md` status table and "Next step", and the `docs/PLAN.md` header status, from `status.md`. Retire `docs/TODO-ZAHER.md` (point it at `status.md`).
- [ ] `PL-02` Plan page: pick date, time window, budget, vibe tags and start point; show 2-3 itineraries with drive / walk times; save a plan. Deps: `PL-01` done.

## Needs Zaher

- [ ] [Z] `DOC-02` Git housekeeping: 8 stale `auto-improve/*` worktrees under Temp and about 10 fully merged local/remote branches (listed in `status.md`). Approve deleting them; the auto task never deletes branches.
- [ ] [Z] `LC-02` Check the live site after the 2026-10-23 deploys (Archive chip, 21+ line, pins, Settings > Pin colors) and try the video slow path once with a captionless TikTok. Report what is wrong and the auto task will turn it into `[!]` items.
- [ ] [Z] `UI-01` Set up the "Save to Dates" Shortcut on both phones (`docs/SHORTCUT.md`); check the service worker and Add to Home Screen in real Chrome.
- [ ] [Z] `IM-02` Decision: how recurring shows are stored ("Every other Saturday, 8 PM"): real RRULE with occurrences (needs `LC-05`) or text only. Recommendation: RRULE, expanded 120 days ahead. Built that way in #19 for explicit patterns (vague words stay text); confirm it is what you want.
- [ ] [Z] `IM-03` Decision: when an article links the event's own website, prefer it over the venue's site and use it for the ticket link. Recommendation: yes for events, no for places.
- [ ] [Z] `IB-01` Decision: how much automatic push. Recommendation: one Home Assistant push per discovery run, named items only at match >= 0.85, at most 3.
- [ ] [Z] `DS-02` Decision: SeatGeek only if a free key can be obtained at signup; otherwise drop it from the plan.

## Backlog

### Import quality (IM)
Source of most items: the daily reports in `improvements/` ("Still not fixed"). Fix the general cause, add a test from a saved fixture.
- [ ] `IM-04` Show times like "8 PM" or "doors 7, show 8" in event text become a start time when the date is known; verified against the page text.
- [ ] `IM-05` Event titles: when a listing gives only a room or stage name, take the show title from the line next to it. Check the $0 price on the magic show against its ticket page.
- [ ] `IM-06` Opening hours only found on third-party pages: store them flagged "from another site, please check" instead of dropping them.
- [ ] `IM-07` Read a venue's tours / experiences pages (day rides, evening rides, private rides) and fill durations and price tiers. Deps: `IM-06`.
- [ ] `IM-08` "Free" only from the event's own text, never from a site's menus or "create your event page for free" footers (finish what #11 started, with a regression fixture).
- [ ] `IM-09` Side attractions in an article become separate items only when the article gives each its own address; otherwise they stay in the description.
- [ ] `IM-10` Off-sale or sold-out events: do not show the old ticket price as current; mark it ("was $13.65, off sale").
- [ ] `IM-11` Event website and ticket link preferred over the venue's site for events. Deps: `IM-03` decided.
- [~] `IM-12` Recurring events stored as an RRULE. Deps: `IM-02` decided, `LC-05`. Explicit patterns are done in #19; what is left is the vague words ("weekly", "monthly") and checking the importer fills `rrule` on a real link.
- [ ] `IM-13` Run the golden set (`python -m app.eval`) after import changes and add every checked daily link with a confirmed answer to `backend/tests/golden.json`.
- [ ] `IM-14` Instagram: decide whether a link can be read from its public oEmbed / caption without login; otherwise keep the review stub and make the stub item show the pasted text. Small experiment only.
- [ ] `IM-16` Price reading from the 2026-10-23 live-DB check: use the regular price, not promo (WeFly $183/$343 vs $229/$429) or parking prices (Academy Museum); do not add the Fever booking fee to the ticket price.
- [ ] `IM-17` Strip tracking parameters (`srsltid`, `utm_*`) from venue websites; save ticket links found on the venue site into the ticket field.
- [ ] `IM-18` Replay the 10 links of the 2026-10-23 check on the fixed code (The Broad, Museum of Love, Academy Museum, Tutu Fun, Lumee, Puppy Yoga, Aquarium, Fever, WeFly, TikTok) and record before/after in `improvements/`.
- [ ] [Z] `IM-19` Decisions from the live-DB check: multi-location businesses (Lumee: one item per store?), undated workshops/classes (an "offerings" concept or place-with-note?), minimum age on places. Stopgap used on 2026-10-30: each Sender One gym stays its own place; the Tutu Fun workshops are events on the place, with prices and "Book online for a time slot" instead of a date. Confirm or change.
- [ ] `IM-22` Addresses: do not accept a street without a house number as final (look the number up on the venue's own page or by web search), and reject a Photon match whose name or street does not fit the venue. Seven live places had street-only addresses and three got a wrong Photon match (an AM radio station, a ranger station, a law firm). Found 2026-10-30.
- [ ] `IM-23` A room, exhibit, show or workshop inside a bigger venue becomes an event on that venue, not a place (Cinegrill and Library Bar inside the Hollywood Roosevelt, exhibits at the Academy Museum, Tutu Fun workshops, a touring show geocoded to another state). Check the host-venue field (`inside`) and the address overlap with an existing place before creating a place. Found 2026-10-30; the live rows were fixed by hand.
- [ ] `IM-24` Single-business pages read only from structured data (Activate Culver City, 2026-10-31) get no description, minimum age or booking link; run the page text through the model for the missing fields, or use the page's own summary. Name fix done 2026-10-31.
- [ ] `IM-20` Price range: ignore a $0 tier when other tiers are paid, so a place with free toddlers shows $7-14 instead of $0-14 (found 2026-10-25; the Free flag itself is fixed).
- [ ] `IM-21` Drive-in / cinema pages: daily showtimes ("7:30pm, 10:40pm") and "box office opens an hour before" into hours text (found 2026-10-25). Related to `IM-04`.
- [ ] `IM-15` Import checks beyond TikTok and articles: Reddit threads, Google Maps lists, Yelp / Time Out roundups, a shared screenshot. One per daily check, record the result.

### Discovery (DS)
Goal: every 3 days find nearby events that match interests and land them in the Suggested inbox.
- [ ] `DS-03` Discovery runner that writes: normalise, geocode venues with local Photon, dedup against the DB (same place, start within 60 min, title similarity > 0.7), save as `origin=discovered`, `review_status=suggested`, record a `discovery_runs` row and `adapter_state`. Keep `--dry-run`.
  - [ ] `DS-03.1` Writer and dedup with fixtures, no network.
  - [ ] `DS-03.2` `adapter_state` backoff and health so a dead adapter never fails the run.
  - [ ] `DS-03.3` `discover` job type and a manual `POST /api/discover/run`.
- [ ] `DS-04` Schedule discovery every 3 days at 03:00 (jitter), low GPU priority. Deps: `DS-03`.
- [ ] `DS-05` Venue watch adapter: every saved place with a website gets its events page re-read each run.
- [ ] `DS-06` SearXNG queries adapter generated from top interest tags ("live jazz <city> this weekend"), linking into the event-page extractor. Deps: `IB-02`.
- [ ] `DS-07` Overpass new places in interest categories (cache 30 days, about 100 calls a day at most).
- [ ] `DS-08` Adapter health shown in Settings (dot per source, last ok, last error).
- [ ] `DS-09` Ticketmaster terms: purge Ticketmaster events 30 days after they end; link back to the ticket page; stay under 2 req/s. Deps: `DS-03`.
- [ ] `DS-10` Settings screen to add iCal/RSS feeds. Deps: `DS-01`.

### Inbox and interests (IB)
- [ ] `IB-02` Interests API (`GET/PUT /api/interests`) and a seed-tag picker in Settings; controlled tag vocabulary (category, vibe, setting, time of day, budget).
- [ ] `IB-03` Embeddings: pull `nomic-embed-text` into the hub, embed items at ingest and discovery (batched, one GPU slot), backfill job for existing items.
- [ ] `IB-04` Match score with "why" breakdown per `docs/PLAN.md` (taste vector, tag overlap, distance, time fit, source quality, penalties). Deps: `IB-02`, `IB-03`.
- [ ] `IB-05` Inbox API: list suggested, accept, dismiss; every action updates the taste profile (`taste_profiles`, negative centroid for dismissals). Deps: `DS-03`, `IB-04`.
- [ ] `IB-06` Inbox screen: suggestion cards, accept / dismiss, J/K/A/D keys on desktop, match "why" on the detail card. Deps: `IB-05`.
- [ ] `IB-07` Faded outlined pins for suggested items on the map and a Suggested filter chip that works. Deps: `IB-05`.
- [ ] `IB-08` Home Assistant push after a discovery run (`notify/ha.py`), deep link to the inbox. Deps: `IB-01` decided, `DS-04`, `IB-05`.

### Planner and calendar (PL)
- [ ] `PL-03` Per-item `.ics` download (`GET /api/items/{id}.ics`) and an "Add to calendar" button on the detail card.
- [ ] `PL-04` Subscribable feed `GET /cal/{token}.ics` of "Going" items (secret token, bypasses Authentik at Caddy, token rotation in Settings). Deps: `PL-03`.
- [ ] `PL-05` Plan export to calendar (one event per stop). Deps: `PL-02`, `PL-03`.
- [ ] `PL-08` The saved-plan JSON carries an `ics` link (`/api/plans/{id}.ics`) that no route serves yet. Serve it with `PL-05` or drop the field until then. Found while doing `PL-01`.
- [ ] `PL-06` Miles in the UI for distances and radius (the plan says HA uses miles).
- [ ] `PL-07` Homarr widget `GET /widget` ("This weekend: N plans, M suggestions", next 3 items). Deps: `IB-05`.

### Lifecycle and ops (LC)
- [ ] `LC-03` NAS backup pull (`datespull` forced-command account, same shape as `recipebox-pull.sh`) plus a restore test of the latest dump into a scratch database. Deps: `LC-01`. Script only; Zaher runs the NAS side.
- [ ] `LC-04` Monthly re-verify of places in batches (closed venues, moved addresses); flag, never delete.
- [x] `LC-05` RRULE expansion into `occurrences` 120 days ahead, nightly, plus on save (done in #19: `recurrence.py`, `expand_occurrences` at 03:55).
- [ ] `LC-06` `~/.claude/skills/homelab/date-planner.md` doc and pointers (outside this repo; write the text into `docs/` and tell Zaher).
- [ ] `LC-07` Worker queue health: stuck / failed jobs visible in Settings with a retry button.
- [ ] `LC-08` Remove the dev services leftovers in docs once `dates_dev` is dropped.

### App and mobile (UI)
- [ ] `UI-02` Lighthouse performance on the phone profile with about 500 seeded items; fix the worst offender (virtualised list, pan debounce).
- [ ] `UI-03` Offline behaviour of the service worker: app shell and last map view; check it does not cache API responses wrongly.
- [ ] `UI-04` Accessibility pass: focus order, labels on icon buttons, contrast in both themes.
- [ ] `UI-05` Empty and error states: first run with no items, API down, import failed (clear message, retry).
- [ ] `UI-06` Share target (`/share`) tested end to end from an Android share sheet and iOS Shortcut.
- [ ] `UI-07` Settings: show the Ticketmaster key status and the AI backend (hub or OpenRouter) in use.

### Tests and CI (QA)
- [ ] `QA-02` Frontend component tests for the filter bar, detail card and Add dialog (vitest + testing-library).
- [ ] `QA-03` Browser smoke test against the mock server (Playwright): map loads, pins show, add flow, filters in the URL.
- [ ] `QA-04` Golden set in CI against saved responses only (no network), failing on any wrong auto-accept.
- [ ] `QA-05` Migration test in CI: upgrade an empty database to head, downgrade one step, upgrade again.
- [ ] `QA-07` CI/CD tidy (reviewed 2026-10-30): skip CI and CD for changes that only touch `*.md`, `improvements/**` or `scripts/**` (today each daily report merge rebuilds, bumps the version and restarts the stack); drop the unused `workflow_call` trigger in `ci.yml`; build the frontend once instead of in the `frontend` job, the `docker` job and CD; remove the one-off `dates-*-dev-1` cleanup from the deploy step (`LC-08`). No ARM image is built and none is needed (the Zephyrus is x86_64).
- [ ] `QA-06` Fixture refresh: replace fixtures whose live pages changed; list which adapters have no fixture.

### Docs and housekeeping (DOC)
- [ ] `DOC-03` `docs/API.md` completeness check against every registered route; add the missing ones.
- [ ] `DOC-04` One-page "how the daily task works" in `docs/OPERATIONS.md` (worktree, tester service, roadmap, reports) so the setup survives losing the prompt.
- [ ] `DOC-05` Prune `improvements/`: keep reports, move bulky raw JSON and old screenshots to a zipped archive folder once a month.

## Done

(newest first; format: `- 2026-10-23 (item) \`CODE\` what changed, PR #n`)

- 2026-10-31 (check) `IM-00` Activate Culver City: a branch name in the page data ("Culver City") now takes the full name from the page title ("Activate Culver City"); description, age 6+ and booking link still missed (`IM-24`)
- 2026-10-30 (item) `IM-00` Exhibitions keep their start and end dates at import and age into the Archive by themselves; an event with only a closing date also archives; Archive / Restore button on the event card; prod data cleanup (56 places / 30 events to 43 / 22, nothing left to review) with its two SQL scripts, PR #22 (open)
- 2026-10-26 (item) `IM-00` Standing venues: weekly page scan, repeating events with RRULE expansion (`LC-05`), events list on the place page, PR #19
- 2026-10-26 (item) `IM-00` Importer provenance (`import_info`) and flexible missing-field flags, PR #18
- 2026-10-26 (item) `IM-01.1` Footer address, phone and venue name now reach the event extractor and apply to every event on the page, PR #17
- 2026-10-25 (check) `IM-00` Paramount Drive-In: footer address now read, a toddler-free line no longer marks a paid place Free, PR #16
- 2026-10-24 (item) `PL-01` Planner API registered in `main.py` and reachable (suggest, save, list, get, patch, delete), 25 API tests, documented in `docs/API.md`, PR #15
- 2026-10-23 (item) `IM-00` Live-DB check fixes: dateless offerings on a home page become the venue's place; address with a name in front keeps its street; a real address replaces "Los Angeles"; the venue's own domain passes the site check; exact-house geocode beats a map embed; domain-as-name replaced by the site name
- 2026-10-23 (check) `IM-00` Dice event page: $0 ticket range and "free donuts" no longer read as free, PR #11
- 2026-10-23 (item) `IM-00` Archive for past events and minimum age on events, PR #12 (before this list existed)
