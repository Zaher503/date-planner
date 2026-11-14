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

- [~] `PL-02` Plan page: pick date, time window, budget, vibe tags and start point; show 2-3 itineraries with drive / walk times; save a plan. Deps: `PL-01` done.
  - Design agreed 2026-10-31 (prototype, not in the repo): a "Plan a night" button in the search bar (key `P`) opens a planner in the left pane with the route on the map; day strip, templates (dinner then a show, drinks then a party), stops with arrival times and travel time, Drive / Rideshare / Walk / Transit, a shortest-route suggestion, share. Add "Add to plan" to the quick actions on the detail card with it. Travel times must come from the OSRM service, not the prototype's formulas.
  - Split 2026-11-12 (too big for one run, and the backend is already done in `PL-01`):
  - [x] `PL-02.1` Frontend plan client and pure helpers (`frontend/src/lib/plan.ts`: types, `api.suggestPlans / savePlan / plans / deletePlan`, request and save bodies, clock / travel / price labels) with vitest tests. Done 2026-11-12.
  - [ ] `PL-02.2` "Plan a night" button (key `P`) and the planner panel in the left pane: date, time window, budget, vibe tags, start point, drive / walk; shows the 2-3 itineraries as cards with arrival times, travel time between stops, price and notes. Add the endpoints to the mock server (`frontend/mock/api.ts`).
  - [ ] `PL-02.3` Draw the chosen itinerary's route and numbered stops on the map; Save plan and a list of saved plans (open, delete). Deps: `PL-02.2`.
  - [ ] `PL-02.4` "Add to plan" in the detail card's quick actions (pins that item as the anchor for a new suggestion). Needs a small `anchor` option on `/api/plans/suggest`, so check the picker first. Deps: `PL-02.2`.
- [ ] `PL-03` Per-item `.ics` download (`GET /api/items/{id}.ics`) and an "Add to calendar" button on the detail card. Moved up from the Backlog 2026-11-09.
- [ ] `DS-03.1` Discovery writer and dedup with fixtures, no network (first sub task of `DS-03`). Moved up 2026-11-09.
- [ ] `QA-05` Migration test in CI: upgrade an empty database to head, downgrade one step, upgrade again. Moved up 2026-11-09.
- [ ] `IM-20` Price range: ignore a $0 tier when other tiers are paid ($7-14, not $0-14). Moved up 2026-11-09; small, no server needed.

## Needs Zaher

- [!] [Z] `LC-13` The deploy of 2026-11-07 never finished: the CD run for "List sort switch" was cancelled after 6 hours while the Zephyrus was hung (`LC-11`), but the version commit (v3.36) was already pushed. The live app still shows v3.26 (build 11-02), so the list sort switch is not live. The auto task never deploys. Recommendation: re-run the CD workflow from the Actions tab (it will bump the version once more, which is harmless), then check the version label on the site. Found 2026-11-11.
- [ ] [Z] `DOC-02` Git housekeeping: 8 stale `auto-improve/*` worktrees under Temp and about 10 fully merged local/remote branches (listed in `status.md`). Approve deleting them; the auto task never deletes branches.
- [ ] [Z] `LC-02` Check the live site after the 2026-10-23 deploys (Archive chip, 21+ line, pins, Settings > Pin colors) and try the video slow path once with a captionless TikTok. Report what is wrong and the auto task will turn it into `[!]` items.
- [ ] [Z] `UI-09` Try the redesign (PR for `UI-08`) on the live site on the phone and on desktop: Filters sheet and drawer, details card and expanding, floating details, dark and light. Report what is wrong and the auto task will turn it into `[!]` items. Not yet checked against the real backend or a real phone.
- [ ] [Z] `UI-01` Set up the "Save to Dates" Shortcut on both phones (`docs/SHORTCUT.md`); check the service worker and Add to Home Screen in real Chrome.
- [ ] [Z] `IM-02` Decision: how recurring shows are stored ("Every other Saturday, 8 PM"): real RRULE with occurrences (needs `LC-05`) or text only. Recommendation: RRULE, expanded 120 days ahead. Built that way in #19 for explicit patterns (vague words stay text); confirm it is what you want.
- [ ] [Z] `IM-03` Decision: when an article links the event's own website, prefer it over the venue's site and use it for the ticket link. Recommendation: yes for events, no for places.
- [ ] [Z] `IB-01` Decision: how much automatic push. Recommendation: one Home Assistant push per discovery run, named items only at match >= 0.85, at most 3.
- [ ] [Z] `DS-02` Decision: SeatGeek only if a free key can be obtained at signup; otherwise drop it from the plan.

## Backlog

### Import quality (IM)
Source of most items: the daily reports in `improvements/` ("Still not fixed"). Fix the general cause, add a test from a saved fixture.
- [ ] `IM-04` Show times like "8 PM" or "doors 7, show 8" in event text become a start time when the date is known; verified against the page text.
- [ ] `IM-05` Event titles: when a listing gives only a room or stage name (still true 2026-11-01: the Hollywood Roosevelt page gives four events named Cinegrill Theater, Cinegrill Theater, Library Bar, Spare Room, none with a date), take the show title from the line next to it. Check the $0 price on the magic show against its ticket page.
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
- [ ] `IM-25` Pages that carry JSON-LD events do not get the page footer (address, phone, venue name) yet; pass it to that path too, or copy a single footer address onto events that have none. Split off from `IM-01` on 2026-11-01 (the text-read path works live).
- [ ] `IM-26` A hotel's "Daily Destination Fee" ($49) was saved as the price tier of the Cinegrill and Library Bar events (Hollywood Roosevelt, 2026-11-01). Ignore resort / destination / service fees as ticket or entry prices, and do not read a venue's room-rate or fee text for an event inside a hotel.
- [ ] `IM-27` Price cards ("Original Course ... Starting at $99") reach the model now (2026-11-02) but gemma4:e4b still leaves the price empty (Skull Canyon). Build tiers from the card lines directly: item name from the lines above, number after "Starting at", checked against the page. Found 2026-11-02.
- [ ] `IM-28` When the site's structured hours and its page text disagree (Skull Canyon: Friday to Tuesday 9-5 vs fall list with Wed/Thu closed), prefer the page's day-by-day hours for the weekly-hours field. Found 2026-11-02.
- [ ] `IM-29` Municipal park pages (Oak Canyon Nature Center, 2026-11-04): with the City Hall footer gone the address stays empty. Find the park's own address, phone and "sunrise to sunset, seven days" hours by searching the name plus city, and prefer the page that was shared (www.anaheim.net/1096) over an old subdomain (local.anaheim.net) as the website. Also "suggested $5 donation" is free entry.
- [ ] `IM-30` Safety check: when the geocoded point is more than a few km from the place found by name search, or the address equals the address of a city office / unrelated organisation, mark the place "address unsure" instead of pinning it. Found 2026-11-04.
- [ ] `IM-31` Booking-widget businesses (Sunburst Railbikes, 2026-11-06): the price per bike and the trip calendar live inside a FareHarbor widget that the plain page read cannot render, so price and hours stay empty. Try the browser path for `fareharbor.com` embeds, or read the price from the page's "From $" text; never invent a number.
- [ ] `IM-32` A business home page should give one place for the business itself (the 2-hour railbike ride, 8 miles) plus dated events; today the ride is missing and only promotions came out. Ask the model for the main experience when the page lists seasonal banners.
- [x] `IM-33` Rerun of the City of Los Angeles video "Things To Do (for the weekend of November 6th)" done 2026-11-11: three events came out with the right titles, dates, venues and "Free"; the start time of "3–7 PM" and "2–4 PM" was dropped and is fixed; follow-ups `IM-34`, `IM-35`, `IM-36`.
- [ ] `IM-34` A "more info" link written next to an event in a caption or description ("🔗 lapl.org/events", "cd2.lacity.gov/calendar") is not kept: the event gets no link, and the website search can pick a third-party directory instead (West Los Angeles Library got `librarytechnology.org` on the live run, `culture.lacity.gov` or nothing on reruns). Keep the link from the text as the event's link, and prefer a search result on the same domain as that link for the venue's site. Touches `IM-03` / `IM-11` (which link wins); the "keep the link from the text" half needs no decision. Found 2026-11-11.
- [ ] `IM-35` An event on a stretch of street (a parade on "Laurel Canyon Blvd. between San Fernando Mission Blvd. & Paxton St.") gets no pin, the street as its venue name and the category "park". Geocode the cross streets (midpoint of the two intersections, marked approximate), keep the event title as what the list shows, and add or map a fitting category (parade / community). Found 2026-11-11.
- [ ] `IM-36` YouTube captions could not be downloaded from the server on 2026-11-08 and 2026-11-11 ("429 Too Many Requests"), so only the title and description are read; a video that only says its details out loud would lose them. Check after `LC-10` (yt-dlp update live) whether it still happens, then try a retry with a pause or the slow path (audio through Whisper) as the fallback. Found 2026-11-11.
- [x] `IM-37` Pages whose structured data links nodes by `@id` (Hollywood Bowl: the event's location and its dated instance are separate nodes) gave a "museum" named after the artist with no date; fixed 2026-11-14.
- [ ] `IM-38` Hollywood Bowl and similar ticketing pages (Tessitura) load the ticket price and the buy link by script, so price stays empty ("Individual tickets, on sale"); the page also says "Gate open 6:30pm" and the show time only in page text. Read the gate time into the description and try the browser path for the price; never invent a number. Found 2026-11-14.
- [ ] `IM-24` Single-business pages read only from structured data (Activate Culver City, 2026-10-31) get no description, minimum age or booking link; run the page text through the model for the missing fields, or use the page's own summary. Name fix done 2026-10-31.
- [ ] `IM-21` Drive-in / cinema pages: daily showtimes ("7:30pm, 10:40pm") and "box office opens an hour before" into hours text (found 2026-10-25). Related to `IM-04`.
- [ ] `IM-15` Import checks beyond TikTok and articles: Reddit threads, Google Maps lists, Yelp / Time Out roundups, a shared screenshot. One per daily check, record the result.

### Discovery (DS)
Goal: every 3 days find nearby events that match interests and land them in the Suggested inbox.
- [ ] `DS-03` Discovery runner that writes: normalise, geocode venues with local Photon, dedup against the DB (same place, start within 60 min, title similarity > 0.7), save as `origin=discovered`, `review_status=suggested`, record a `discovery_runs` row and `adapter_state`. Keep `--dry-run`.
  - [ ] `DS-03.1` Writer and dedup with fixtures, no network (listed in Now).
  - [ ] `DS-03.2` `adapter_state` backoff and health so a dead adapter never fails the run.
  - [ ] `DS-03.3` `discover` job type and a manual `POST /api/discover/run`.
- [ ] `DS-04` Schedule discovery every 3 days at 03:00 (jitter), low GPU priority. Deps: `DS-03`.
- [ ] `DS-05` Venue watch adapter: every saved place with a website gets its events page re-read each run.
- [ ] `DS-06` SearXNG queries adapter generated from top interest tags ("live jazz <city> this weekend"), linking into the event-page extractor. Deps: `IB-02`.
- [ ] `DS-07` Overpass new places in interest categories (cache 30 days, about 100 calls a day at most).
- [ ] `DS-08` Adapter health shown in Settings (dot per source, last ok, last error).
- [ ] `DS-09` Ticketmaster terms: purge Ticketmaster events 30 days after they end; link back to the ticket page; stay under 2 req/s. Deps: `DS-03`.
- [ ] `DS-10` Settings screen to add iCal/RSS feeds (the `GET/PUT /api/discover/feeds` API exists since `DS-01`). Deps: `DS-01` done.

### Inbox and interests (IB)
- [ ] `IB-02` Interests API (`GET/PUT /api/interests`) and a seed-tag picker in Settings; controlled tag vocabulary (category, vibe, setting, time of day, budget).
- [ ] `IB-03` Embeddings: pull `nomic-embed-text` into the hub, embed items at ingest and discovery (batched, one GPU slot), backfill job for existing items.
- [ ] `IB-04` Match score with "why" breakdown per `docs/PLAN.md` (taste vector, tag overlap, distance, time fit, source quality, penalties). Deps: `IB-02`, `IB-03`.
- [ ] `IB-05` Inbox API: list suggested, accept, dismiss; every action updates the taste profile (`taste_profiles`, negative centroid for dismissals). Deps: `DS-03`, `IB-04`.
- [ ] `IB-06` Inbox screen: suggestion cards, accept / dismiss, J/K/A/D keys on desktop, match "why" on the detail card. Deps: `IB-05`.
- [ ] `IB-07` Faded outlined pins for suggested items on the map and a Suggested option in the Filters panel that works (the redesign removed it from the panel until this exists). Deps: `IB-05`.
- [ ] `IB-08` Home Assistant push after a discovery run (`notify/ha.py`), deep link to the inbox. Deps: `IB-01` decided, `DS-04`, `IB-05`.

### Planner and calendar (PL)
- [ ] `PL-04` Subscribable feed `GET /cal/{token}.ics` of "Going" items (secret token, bypasses Authentik at Caddy, token rotation in Settings). Deps: `PL-03`.
- [ ] `PL-05` Plan export to calendar (one event per stop). Deps: `PL-02`, `PL-03`.
- [ ] `PL-08` The saved-plan JSON carries an `ics` link (`/api/plans/{id}.ics`) that no route serves yet. Serve it with `PL-05` or drop the field until then. Found while doing `PL-01`.
- [ ] `PL-06` Miles in the UI for distances and radius (the plan says HA uses miles).
- [ ] `PL-07` Homarr widget `GET /widget` ("This weekend: N plans, M suggestions", next 3 items). Deps: `IB-05`.

### Lifecycle and ops (LC)
- [ ] `LC-09` After the first deploy with `LC-01.1`, check `/srv/dateplanner/backups` has a `dates-*.dump` and that `pg_restore -l` reads it. Folds into the restore test of `LC-03`.
- [ ] `LC-10` After the first deploy with `LC-01.2`, check the worker log on a Sunday for "yt-dlp X -> Y" and that `/srv/dateplanner/data/ytdlp` exists (needs PyPI reachable from the worker container).
- [x] `LC-11` The Zephyrus GPU driver hang of 2026-11-08 (hundreds of stuck `nvidia-smi` processes, AI hub 502, imports failing). The server was rebooted on 2026-11-10 (up since about 07:40) and the tester, the app and the AI hub answer again (checked 2026-11-11). Why `nvidia-smi` hung is still unknown; `LC-12` is the guard.
- [ ] `LC-12` GPU watchdog: a small check (cron on the Zephyrus or a worker job) that runs `timeout 10 nvidia-smi` and asks the AI hub for `/api/tags`; on failure send one Home Assistant push ("Dates: AI hub down") instead of letting imports fail silently. Found 2026-11-08 (`LC-11`). Deps: `LC-11` done.
- [ ] `LC-03` NAS backup pull (`datespull` forced-command account, same shape as `recipebox-pull.sh`) plus a restore test of the latest dump into a scratch database. Deps: `LC-01`. Script only; Zaher runs the NAS side.
- [ ] `LC-04` Monthly re-verify of places in batches (closed venues, moved addresses); flag, never delete.
- [x] `LC-05` RRULE expansion into `occurrences` 120 days ahead, nightly, plus on save (done in #19: `recurrence.py`, `expand_occurrences` at 03:55).
- [ ] `LC-06` `~/.claude/skills/homelab/date-planner.md` doc and pointers (outside this repo; write the text into `docs/` and tell Zaher).
- [ ] `LC-07` Worker queue health: stuck / failed jobs visible in Settings with a retry button.
- [ ] `LC-08` Remove the dev services leftovers in docs once `dates_dev` is dropped.

### App and mobile (UI)
- [ ] `UI-02` Lighthouse performance on the phone profile with about 500 seeded items; fix the worst offender (virtualised list, pan debounce).
- [ ] `UI-03` Offline behaviour of the service worker: app shell and last map view; check it does not cache API responses wrongly.
- [ ] `UI-04` Accessibility pass: focus order, labels on icon buttons, contrast in both themes. The redesign's new parts (search bar, Filters panel, details actions) already have labels and the gray text was raised to 5:1; the rest of the app is still to check.
- [ ] `UI-10` Filters the redesign took out of the interface (Type, Price, Tags, Open now, Include past, Tomorrow, Next 31 days, Pick dates, Suggested). The URL and API still support them and an active one shows as a token in the search bar. Bring one back only if it is missed.
- [ ] `UI-05` Empty and error states: first run with no items, API down, import failed (clear message, retry).
- [ ] `UI-06` Share target (`/share`) tested end to end from an Android share sheet and iOS Shortcut.
- [ ] `UI-07` Settings: show the Ticketmaster key status and the AI backend (hub or OpenRouter) in use.

### Tests and CI (QA)
- [ ] `QA-02` Frontend component tests for the search bar, Filters panel, detail card and Add dialog (vitest + testing-library).
- [ ] `QA-03` Browser smoke test against the mock server (Playwright): map loads, pins show, add flow, filters in the URL.
- [ ] `QA-04` Golden set in CI against saved responses only (no network), failing on any wrong auto-accept.
- [ ] `QA-07` CI/CD tidy (reviewed 2026-10-30): skip CI and CD for changes that only touch `*.md`, `improvements/**` or `scripts/**` (today each daily report merge rebuilds, bumps the version and restarts the stack); drop the unused `workflow_call` trigger in `ci.yml`; build the frontend once instead of in the `frontend` job, the `docker` job and CD; remove the one-off `dates-*-dev-1` cleanup from the deploy step (`LC-08`). No ARM image is built and none is needed (the Zephyrus is x86_64).
- [ ] `QA-08` After the `QA-01` PR merges, the open daily PRs (#23-#32) that add imports may fail the wider lint (unsorted or unused imports). Run `ruff check --fix backend` on each branch before merging it. Found 2026-11-09.
- [x] `QA-01` CI lint widened to ruff's default rules plus import sorting (`backend/ruff.toml`, ruff pinned to 0.17.4); 25 findings fixed, no behaviour change (done 2026-11-09).
- [ ] `QA-06` Fixture refresh: replace fixtures whose live pages changed; list which adapters have no fixture.

### Docs and housekeeping (DOC)
- [ ] `DOC-03` `docs/API.md` completeness check against every registered route; add the missing ones.
- [ ] `DOC-04` One-page "how the daily task works" in `docs/OPERATIONS.md` (worktree, tester service, roadmap, reports) so the setup survives losing the prompt.
- [ ] `DOC-05` Prune `improvements/`: keep reports, move bulky raw JSON and old screenshots to a zipped archive folder once a month.

## Done

(newest first; format: `- 2026-10-23 (item) \`CODE\` what changed, PR #n`)

- 2026-11-14 (check) `IM-37` Hollywood Bowl Steve Lacy concert page: structured data that points to the venue and to the dated show by `@id` is now resolved, so it comes out as a Nov 21 event at Hollywood Bowl (2301 Highland Ave) instead of an undated "museum"; price and gate time still missed (`IM-38`), PR #37
- 2026-11-12 (item) `PL-02.1` Planner client for the app: types, API calls and helpers for the suggest / save / list / delete plan routes, 5 tests; no visible change yet, `PL-02` split into four sub tasks, PR #36
- 2026-11-11 (check) `IM-33` City of Los Angeles weekend video (YouTube, three free events): a start time written as a range with one am/pm ("3–7 PM", "2–4 PM") is no longer dropped as unverified; the Zephyrus is back (`LC-11` closed) but the 2026-11-07 deploy never finished (`LC-13`); info links, the parade's pin and captions still missed (`IM-34`, `IM-35`, `IM-36`), PR #35
- 2026-11-10 (item) `DOC-01` README status table, "Next step" and layout table, and the `docs/PLAN.md` header status rewritten from `status.md`; `docs/TODO-ZAHER.md` retired to a pointer; import check skipped again because the Zephyrus is still hung (`LC-11`), PR #34
- 2026-11-09 (item) `QA-01` CI lint widened to ruff's default rules plus import sorting; 25 findings fixed (import order, 7 unused imports, one unused variable, two test-style nits), tests 391 passed before and after; import check skipped because the Zephyrus is still hung (`LC-11`), PR #33
- 2026-11-07 (item) `LC-01.2` Weekly yt-dlp self-update job (Sunday 03:10, safe swap, downloads use the updated copy); `LC-01` complete
- 2026-11-06 (check) `IM-00` Sunburst Railbikes (home page): sale banners ("Save 15% on weekday rides", a 35% toy-drive discount window) are kept as offers on the venue instead of becoming events; the import tester now applies the same offer step as the real pipeline; price and trip calendar still missed (`IM-31`, `IM-32`), PR #30
- 2026-11-05 (item) `LC-01.1` Nightly database backup job (02:30, `pg_dump -Fc` into `/srv/dateplanner/backups`, newest 7 kept, hand-made dumps untouched); `pg_dump` 17 added to the app image; 6 tests
- 2026-11-04 (check) `IM-00` Oak Canyon Nature Center (Anaheim city page): a city or county site's footer (City Hall address) is no longer taken as the park's address; phone, hours, free entry and the right website still missed (`IM-29`, `IM-30`)
- 2026-11-03 (item) `DS-01` iCal feed adapter wired in: registered in `ADAPTERS`, feed list kept in `adapter_state` and edited with `GET/PUT /api/discover/feeds`, the dry run builds it from the stored list; `icalendar` and `recurring-ical-events` added to requirements (they were missing); 7 tests from the saved sample feed
- 2026-11-02 (check) `IM-00` Skull Canyon Ziplines: more site pages read (tours, packages, six instead of four, hours and price pages first), dropped price-card lines recovered, current-season hours preferred; card prices still missing (`IM-27`, `IM-28`)
- 2026-11-01 (item) `IM-01.2` Live recheck of the Hollywood Roosevelt link: the footer address and phone now reach all four events; two follow-ups added (`IM-25`, `IM-26`), no code change
- 2026-10-31 (check) `IM-00` Activate Culver City: a branch name in the page data ("Culver City") now takes the full name from the page title ("Activate Culver City"); description, age 6+ and booking link still missed (`IM-24`)
- 2026-10-31 (item) `UI-08` Redesign: new blue / Inter look with glass panels, a Filters drawer (phone: tall sheet) with Saved status, When, five category groups, Distance and Archive, filters shown as removable tokens in the search bar, details floating over the map on desktop, details card that expands on phones with Directions / Website / Call / Tickets / Share, PR #24
- 2026-10-30 (item) `IM-00` Exhibitions keep their start and end dates at import and age into the Archive by themselves; an event with only a closing date also archives; Archive / Restore button on the event card; prod data cleanup (56 places / 30 events to 43 / 22, nothing left to review) with its two SQL scripts, PR #22 (merged)
- 2026-10-26 (item) `IM-00` Standing venues: weekly page scan, repeating events with RRULE expansion (`LC-05`), events list on the place page, PR #19
- 2026-10-26 (item) `IM-00` Importer provenance (`import_info`) and flexible missing-field flags, PR #18
- 2026-10-26 (item) `IM-01.1` Footer address, phone and venue name now reach the event extractor and apply to every event on the page, PR #17
- 2026-10-25 (check) `IM-00` Paramount Drive-In: footer address now read, a toddler-free line no longer marks a paid place Free, PR #16
- 2026-10-24 (item) `PL-01` Planner API registered in `main.py` and reachable (suggest, save, list, get, patch, delete), 25 API tests, documented in `docs/API.md`, PR #15
- 2026-10-23 (item) `IM-00` Live-DB check fixes: dateless offerings on a home page become the venue's place; address with a name in front keeps its street; a real address replaces "Los Angeles"; the venue's own domain passes the site check; exact-house geocode beats a map embed; domain-as-name replaced by the site name
- 2026-10-23 (check) `IM-00` Dice event page: $0 ticket range and "free donuts" no longer read as free, PR #11
- 2026-10-23 (item) `IM-00` Archive for past events and minimum age on events, PR #12 (before this list existed)
