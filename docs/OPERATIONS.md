# Operations

## Where things live (Zephyrus)

| Path | What |
|---|---|
| `~/dateplanner/src/` | Deployed code (replaced on every deploy; previous copy in `src.old`) |
| `~/dateplanner/src/REVISION` | Git commit that is running |
| `~/dateplanner/.env` | Secrets (mode 600). Symlinked into `src/deploy/.env` |
| `/srv/dateplanner/` | Data: media, tiles, OSRM, Photon, backups |
| `/srv/gpu/gpu.lock` | GPU lock shared with Recipe Box and the Transcriber |
| volume `dates_dates-pg` | Postgres data |

## First deploy

```bash
scripts/init-env.sh
scripts/deploy.sh
```

## Everyday

```bash
scripts/deploy.sh                 # ship HEAD, rebuild, restart changed services
scripts/deploy.sh worker          # only the worker
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose logs -f --tail 50 worker'
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose exec db psql -U dates dates'
curl -s http://192.168.0.172:8820/healthz
```

## Rollback

```bash
ssh zephyrus 'cd ~/dateplanner && mv src src.bad && mv src.old src && cd src/deploy && docker compose up -d --build'
```

Migrations only go forward on deploy. To undo one: `docker compose exec api alembic downgrade -1` before rolling back the code.

## Dev instance (UI testing)

`api-dev` and `worker-dev` (compose profile `dev`) run the same `dates-app:local` image against the database `dates_dev` (a copy of prod on the same Postgres server). `api-dev` signs every request in as `zaher` through `DEV_USER` and is published only on the Zephyrus loopback, port 8821. `worker-dev` processes adds made from the dev UI; it shares Ollama and the GPU lock with the prod worker and runs its own scheduler against `dates_dev`.

```bash
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose --profile dev up -d api-dev worker-dev'
ssh -L 8821:127.0.0.1:8821 zephyrus      # then open http://localhost:8821
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose --profile dev stop api-dev worker-dev'
```

The image is whatever `scripts/deploy.sh` last built, so new code reaches the dev instance after a deploy plus the `up -d` above. `api-dev` runs `alembic upgrade head` on `dates_dev` when it starts. Thumbnails and tiles come from the shared `/srv/dateplanner`.

**`DEV_USER` must never be set on the public `api` service** (nor in `~/dateplanner/.env`, which every service reads): it skips the Authentik check entirely. It is safe on `api-dev` only because that port is bound to 127.0.0.1.

Refresh `dates_dev` from prod (throws away dev changes):

```bash
ssh zephyrus 'cd ~/dateplanner/src/deploy && docker compose --profile dev stop api-dev worker-dev && docker compose exec -T db sh -c "dropdb -U dates --if-exists dates_dev && createdb -U dates dates_dev && pg_dump -U dates dates | psql -q -U dates dates_dev"'
```
