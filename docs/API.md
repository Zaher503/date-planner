# API (Phase 4 contract)

Every route needs an Authentik identity (`current_user`) unless marked **open**. JSON in and out. Times are ISO 8601 with offset (UTC from the database). Distances in metres. Item ids are UUID strings; `type` in paths is `place` or `event`.

## Already built

| Route | What |
|---|---|
| `GET /healthz` (open) | `{"ok": true}` |
| `POST /api/add` (key) | Shortcut add |
| `POST /api/ui/add` | `{url?, text?}` -> `{status: queued|exists|stub, source_id, job_id, kind}` |
| `GET /api/jobs` | Queued/running jobs plus those finished in the last 5 min: `[{id, type, status, stage, pct, error, result, source_id, created_at, finished_at, url, title, kind}]` |
| `GET /api/review` | Places needing review with `candidates` |
| `POST /api/places/{id}/resolve` | `{candidate_id: int|null}` (null confirms the current pin) |
| `GET /api/me` | `{id, username, display_name}` |
| `GET /api/health/services` | `[{name, ok, ms, detail}]` |

## Settings and facets

`GET /api/settings`

```json
{
  "home": {"lat": 34.0461, "lon": -118.3265, "source": "ha"},
  "radius_km": 40, "units": "mi", "tz": "America/Los_Angeles",
  "user": {"id": 1, "username": "zaher", "display_name": "Zaher"},
  "users": [{"id": 1, "username": "zaher", "display_name": "Zaher"}],
  "map": {"tiles": "/tiles/region.pmtiles", "assets": "/tiles/assets", "bounds": [-120.3, 32.5, -116.0, 35.8]}
}
```

`GET /api/facets` -> `{"tags": [{"tag": "rooftop", "n": 4}], "categories": [{"cat": "food", "n": 9}]}` counted over items that are not dismissed (top 100 tags).

## Filters (shared by `/api/map` and `/api/list`)

All optional. Lists are comma separated.

| Param | Meaning |
|---|---|
| `bbox=w,s,e,n` | Only items inside (required for `/api/map`) |
| `types=place,event` | Default both |
| `when=today|tomorrow|weekend|week|month|range` | Events with an occurrence overlapping the window (in `settings.tz`). `weekend` is the coming (or current) Fri 17:00 to Sun 23:59; `week` is now + 7 days; `month` now + 31 days; `range` uses `from=YYYY-MM-DD&to=YYYY-MM-DD` (inclusive days). Recurring events (`rrule` or `recurrence_text` set) always pass. Undated one-off events are dropped when `when` is set. Places are not affected by `when` |
| `open_now=1` | Drops places whose `opening_hours` say closed right now (unknown hours pass). Events: only ones happening now |
| `price=free,1,2,3` | Any of: `free` (event `is_free` or place `price_level` 0), `1` (event `price_min` < 20 or place level 1), `2` (20 to 50, level 2), `3` (above 50, level 3 or 4). Unknown price fails when `price` is set |
| `tags=a,b` | Item has all of them |
| `cats=food,live_music` | Category is any of them |
| `status=want,going,been,suggested,review` | Any of: my status is want/going/been, `suggested` (review_status suggested), `review` (needs_review). Without `status`, everything except dismissed is returned (review_status `dismissed` or my status `dismissed`) |
| `near=lat,lon` | Distance origin, default home |
| `dist_km=40` | Within this distance of `near` (no limit when absent) |
| `q=text` | Full text (`search` tsvector, `websearch_to_tsquery`) or name/title trigram similarity > 0.3 |
| `past=1` | Include events that already ended and `status=archived` (default: hidden; an event has ended when `coalesce(ends_at, starts_at + duration, starts_at + 3h) < now`) |

## Map and list

`GET /api/map?bbox=...&filters` -> GeoJSON, at most 2000 features, single SQL query per item type.

```json
{"type": "FeatureCollection", "features": [{
  "type": "Feature",
  "geometry": {"type": "Point", "coordinates": [-118.39, 34.05]},
  "properties": {
    "id": "uuid", "t": "place", "title": "Perch", "cat": "food",
    "start": null, "end": null, "all_day": false, "rec": null,
    "price": "$$", "free": false,
    "rs": "ok", "my": "want", "rating": 4,
    "addr": "448 S Hill St, Los Angeles", "venue": null,
    "dist_m": 5120, "thumb": true, "tags": ["rooftop", "views"]
  }
}]}
```

`rs` is review_status, `my` my status (null if none), `rating` my rating, `venue` the event's venue name, `thumb` whether `/api/thumb/{source_id}` exists for one of its sources (then `thumb_src` holds that source id), `price` a short label (`Free`, `$15`, `$15-30`, `$$`) or null, `tags` at most 5.

`GET /api/list?filters&sort=date|distance|recent|name&limit=50&offset=0` -> `{"items": [ {same properties, plus "lat", "lon"} ], "total": 123}`. Default sort: `date` (dated events by next start first, then places by name). `limit` max 200.

## Items

`GET /api/items/{type}/{id}`

```json
{
  "id": "uuid", "type": "place", "title": "Perch", "category": "food",
  "description": "...", "tags": ["rooftop"], "lat": 34.05, "lon": -118.25,
  "address_text": "448 S Hill St, Los Angeles, CA 90013",
  "review_status": "ok", "confidence": 0.93, "origin": "manual",
  "created_at": "...", "updated_at": "...", "edited": ["name", "geom"],
  "price_label": "$$",

  "website": "...", "phone": "...", "opening_hours": "Mo-Su 16:00-01:00", "open_now": true,
  "price_level": 2, "closed": false,
  "events": [{"id": "uuid", "title": "...", "starts_at": "...", "recurrence_text": null}],

  "starts_at": null, "ends_at": null, "duration_min": null, "duration_estimated": false,
  "all_day": false, "recurrence_text": null, "tz": "America/Los_Angeles",
  "price_min": null, "price_max": null, "currency": "USD", "is_free": null,
  "price_text": null, "ticket_url": null, "status": "scheduled", "venue_name": null,
  "place": {"id": "uuid", "title": "..."},

  "sources": [{"id": "uuid", "kind": "tiktok", "url": "...", "title": "...", "caption": "first 500 chars",
               "thumb": "/api/thumb/<source_id>", "created_at": "...", "submitted_by": "Zaher"}],
  "me": {"status": "want", "rating": 4, "notes": "...", "visited_at": null},
  "others": [{"user": "Katherine", "status": "been", "rating": 5, "notes": null}],
  "candidates": [{"id": 12, "name": "...", "address": "...", "score": 0.7, "provider": "photon",
                  "chosen": false, "lat": 34.0, "lon": -118.0}]
}
```

Place-only keys (`website` ... `events`) are present for places, event-only keys (`starts_at` ... `place`) for events. `me` is null when I have no state. `candidates` is filled for a place that needs review, and for an event whose place needs review (then they are the place's candidates; resolve through `/api/places/{place.id}/resolve`). `edited` lists `user_overrides` keys.

`PATCH /api/items/{type}/{id}` with any subset of:
- place: `title` (stored as `name`), `category`, `description`, `tags`, `address_text`, `website`, `phone`, `opening_hours`, `price_level`, `lat` + `lon` (together), `closed`, `review_status` (`ok` or `dismissed`)
- event: `title`, `category`, `description`, `tags`, `starts_at`, `ends_at`, `all_day`, `recurrence_text`, `price_min`, `price_max`, `is_free`, `price_text`, `ticket_url`, `status`, `review_status`, `lat` + `lon`

Each changed field is written and its key set in `user_overrides` (`lat`/`lon` -> `geom`, place `title` -> `name`). Moving or renaming a place updates `geom`/`venue_name` of its events. Returns the item as in GET.

`DELETE /api/items/{type}/{id}` -> 204. Deleting a place deletes its events. Sources left with no linked items are deleted too, so the same link can be added again.

`PUT /api/items/{type}/{id}/me` with any subset of `{status: want|going|been|dismissed|null, rating: 1-5|null, notes: str|null, visited_at: date|null}`; only the keys sent change. Setting `been` without `visited_at` sets it to today. Returns `me`.

`POST /api/items/{type}/{id}/reprocess` -> `{"jobs": [ids]}`. Queues an ingest job for every linked source (not Instagram stubs), like a fresh add. User edits survive because of `user_overrides`.

## Media and map files

- `GET /api/thumb/{source_id}` -> image. Cached at `/data/media/thumbs/<source_id>.<ext>` after the first fetch (TikTok oEmbed thumbnail, refreshed through oEmbed if the stored URL expired; page `og:image`). `Cache-Control: private, max-age=604800`. 404 when the source has no image.
- `GET /tiles/region.pmtiles` (open) with HTTP Range support (206), `Cache-Control: public, max-age=86400`.
- `GET /tiles/assets/{path}` (open): glyphs and sprites from `/data/tiles/assets` (`fonts/{fontstack}/{range}.pbf`, `sprites/v4/light.json` etc.), `Cache-Control: public, max-age=2592000`.

## The app shell

Everything else that is not `/api/*`, `/tiles/*`, `/healthz` or `/cal/*` serves the built SvelteKit app from `/app/static` (open; the data behind it needs identity). Unknown paths fall back to `index.html` (client-side routes). Files under `/_app/immutable/` get `Cache-Control: public, max-age=31536000, immutable`; `index.html` and `service-worker.js` get `no-cache`.
