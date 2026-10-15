# Operations

## How it is deployed

Every push to `main` deploys itself: `.github/workflows/ci.yml` (backend tests, frontend check/tests/build, compose validation, image build) and then `cd.yml`, which publishes `ghcr.io/zaher503/date-planner` and `ghcr.io/zaher503/date-planner-db` and runs the update on the Zephyrus through a self-hosted runner (label `date-planner`, installed in `/opt/actions-runner-date-planner`). The runner copies `deploy/` to `/opt/date-planner/deploy`, links the real `.env`, pulls the images, runs `docker compose --profile dev up -d` (the api runs the migrations at start) and health-checks `http://127.0.0.1:8820/healthz`.

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

`import-tester/` (run `run.bat` on Windows) runs the same code on one link without the database, to see what an import would find.

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

`api-dev` and `worker-dev` (compose profile `dev`) run the same image against the database `dates_dev` (a copy of prod on the same Postgres server). `api-dev` signs every request in as `zaher` through `DEV_USER` and is published only on the Zephyrus loopback, port 8821. `worker-dev` processes adds made from the dev UI; it uses the same AI hub as the prod worker and runs its own scheduler against `dates_dev`. The deploy keeps them up to date.

```bash
ssh -L 8821:127.0.0.1:8821 zephyrus      # then open http://localhost:8821
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose --profile dev stop api-dev worker-dev'
```

**`DEV_USER` must never be set on the public `api` service** (nor in `~/dateplanner/.env`, which every service reads): it skips the Authentik check entirely. It is safe on `api-dev` only because that port is bound to 127.0.0.1.

Refresh `dates_dev` from prod (throws away dev changes):

```bash
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose --profile dev stop api-dev worker-dev && docker compose exec -T db sh -c "dropdb -U dates --if-exists dates_dev && createdb -U dates dates_dev && pg_dump -U dates dates | psql -q -U dates dates_dev" && docker compose --profile dev up -d'
```

## After any `.env` change

Recreate every app container, including the dev copies:

```bash
ssh zephyrus 'cd /opt/date-planner/deploy && docker compose --profile dev up -d --force-recreate api worker api-dev worker-dev'
```
