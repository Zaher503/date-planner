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
