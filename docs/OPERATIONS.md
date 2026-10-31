# Operations

## How it is deployed

Every push to `main` deploys itself: `.github/workflows/ci.yml` (backend tests, frontend check/tests/build, compose validation, image build) and then `cd.yml`, which publishes `ghcr.io/zaher503/date-planner` and `ghcr.io/zaher503/date-planner-db` and runs the update on the Zephyrus through a self-hosted runner (label `date-planner`, installed in `/opt/actions-runner-date-planner`). The runner copies `deploy/` to `/opt/date-planner/deploy`, links the real `.env`, pulls the images, runs `docker compose up -d --remove-orphans` (the api runs the migrations at start) and health-checks `http://127.0.0.1:8820/healthz`.

## Where things live (Zephyrus)

| Path | What |
|---|---|
| `/opt/date-planner/deploy/` | Deployed compose file and SearXNG settings (replaced on every deploy; previous copy in `deploy.old`) |
| `/opt/date-planner/REVISION` | Git commit that is running |
| `~/dateplanner/.env` | Secrets (mode 600). Symlinked into `/opt/date-planner/deploy/.env` |
| `/srv/dateplanner/` | Data: media, tiles, OSRM, Photon, backups |
| volume `dates_dates-pg` | Postgres data |
| network `ai` | Shared with the AI hub (Ollama, Whisper, queue). `OLLAMA_URL` in `.env` must be `http://ai-hub:11434` |

## The AI hub

Dates has no models and no GPU of its own. The worker calls the hub ([ai-hub](https://github.com/Zaher503/ai-hub), `http://ai-hub:11434`) for the LLM and for Whisper. The hub queues all GPU work from every app (Dates, Foodbox, Transcriber), swaps what is loaded on the card and says how long the wait is, which the ingest job shows as its stage ("waiting for the AI (2 ahead, about 40 s)"). Dates sends its calls with low priority, so a recipe or transcript someone is waiting on goes first.

```bash
ssh zephyrus 'curl -s localhost:11434/queue'       # who is running, who is waiting, estimates
```

## Website lookup (import)

After a link is placed on the map, the ingest job reads each venue's own website: SearXNG finds it, the model picks the official site, and the home page, contact/hours pages and up to two ticket-vendor pages are read. Hours, phone, price tiers (`places.price_tiers`), the hours as worded (`hours_text`) and photos are filled in only where empty, and every value must appear in the page text. If the site gives a map pin within 1.5 km of the map match, the pin moves to it; farther away it only adds a review flag. A venue already stored with a website and hours or prices is not read again. It needs SearXNG (`SEARXNG_URL`); the real browser (`BROWSER_URL`) is used for JavaScript pages when configured.

`import-tester/` (run `run.bat` on Windows) runs the same code on one link without the database, to see what an import would find. The "Show prod UI" button there loads the running app (`PROD_URL`, default `http://192.168.0.103:8820`) for the UI and map tiles, with a fake read-only API fed by the import, so it always matches prod; it falls back to `frontend/build` if prod is unreachable.

The same tool also runs as a service on the Zephyrus (compose service `tester`, `import-tester/service.py`), reachable at `https://dates.zkocr.com/tester/api/import` with header `X-Tester-Key: <TESTER_KEY>` instead of an Authentik login - the one route on this domain meant to be called from outside the LAN unauthenticated-by-Authentik. It never mounts `/srv/dateplanner` and gets none of the other services' secrets (see `deploy/compose.yaml`), so a leaked `TESTER_KEY` can only run test imports. Rotate it in `~/dateplanner/.env` and `docker compose up -d --force-recreate tester` if it ever leaks.

## First deploy (new machine)

```bash
scripts/init-env.sh                     # writes ~/dateplanner/.env on the Zephyrus
scripts/add-runner.sh date-planner      # registers the runner (copy from the ai-hub repo)
git push                                # CI/CD does the rest
```

The ai-hub stack must be running first (it creates the `ai` network).

## Everyday

```bash
git push                                      # deploys itself
scripts/deploy.bat                            # re-run the deploy of what is on main without a new commit
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose logs -f --tail 50 worker'
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose exec db psql -U dates dates'
curl -s http://192.168.0.169:8820/healthz
```

## Rollback

Re-run an older deploy: in GitHub Actions, run the CD workflow on the commit you want (or `git revert` and push). Images are also kept by commit hash: `DATES_TAG=<sha> docker compose up -d` in `/opt/date-planner/deploy` runs that build.

Migrations only go forward on deploy. To undo one: `docker compose exec api alembic downgrade -1` before rolling back the code.

## Dev instance (UI testing)

The dev copy runs on the desktop, not on the Zephyrus, and the deploy does not touch it. `dev/compose.yaml` builds the app from this checkout and runs `db`, `api-dev` and `worker-dev` against their own empty local database. `api-dev` signs every request in as `zaher` through `DEV_USER` and is published only on `127.0.0.1:8821`.

```bash
docker compose -f dev/compose.yaml up -d --build      # then open http://localhost:8821
docker compose -f dev/compose.yaml down               # add -v to throw the dev data away
```

The prod stack no longer has dev services. The first deploy after they were dropped removed the `api-dev` and `worker-dev` containers; the `dates_dev` database is still inside the prod Postgres and can be dropped with `docker compose exec db dropdb -U dates dates_dev`.

**`DEV_USER` must never be set on the public `api` service** (nor in `~/dateplanner/.env`, which every service reads): it skips the Authentik check entirely.

## After any `.env` change

Recreate every app container:

```bash
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose up -d --force-recreate api worker'
```

## Standing venues

A standing place is re-read on its own schedule (weekly by default). The worker runs `watch_scan` at 03:40 every day; it queues an ingest of each standing venue whose interval is up, and `expand_occurrences` at 03:55 extends repeating events 120 days ahead. Check a venue: `select name, last_scanned_at, last_scan_status, last_scan_note from places where standing`. Turn one on in the app (Edit > Standing venue) or with `PATCH /api/items/place/{id}`.

## Which importer read an item

`import_info` on places and events holds the importer version, engine and model of the last read (see `app/ingest/provenance.py`; bump `IMPORTER_VERSION` when extraction rules or prompts change). Items from before it existed say `legacy`. Items read by an older importer:

```sql
select name, import_info->>'importer_version' v, import_info->>'engine' e, import_info->>'model' m, import_info->>'at' at
from places where import_info->>'importer_version' is distinct from '2026.10.26-1' order by at;
```
