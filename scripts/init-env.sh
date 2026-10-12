#!/usr/bin/env bash
# One-time: create ~/dateplanner/.env on the Zephyrus with fresh random secrets.
# HA_TOKEN comes from the PC's ~/.claude/secrets/homelab.env. Refuses to overwrite.
# The new DATES_KEY is appended to homelab.env so the Shortcut and add-date.ps1 can use it.
set -euo pipefail
SECRETS=~/.claude/secrets/homelab.env
set -a; . "$SECRETS"; set +a

if ssh zephyrus 'test -f ~/dateplanner/.env'; then
  echo "~/dateplanner/.env already exists on the Zephyrus, not touching it"; exit 0
fi

pg=$(openssl rand -hex 24)
key=$(openssl rand -hex 24)

ssh zephyrus "umask 077; mkdir -p ~/dateplanner; cat > ~/dateplanner/.env" <<EOF
PG_PASSWORD=$pg
DATABASE_URL=postgresql+psycopg://dates:$pg@db:5432/dates
DATES_KEY=$key
TRUSTED_PROXY=192.168.0.70
OLLAMA_URL=http://ai-hub:11434
LLM_MODEL=gemma4:e4b
EMBED_MODEL=nomic-embed-text
HA_URL=http://192.168.0.108:8123
HA_TOKEN=${HA_TOKEN}
NOTIFY_TARGETS=mobile_app_zahers_17pm,mobile_app_katherines_phone
SEARXNG_SECRET=$(openssl rand -hex 32)
PHOTON_URL=http://photon:2322
OSRM_CAR_URL=http://osrm-car:5000
OSRM_FOOT_URL=http://osrm-foot:5000
SEARXNG_URL=http://searxng:8080
TICKETMASTER_KEY=
DATA_DIR=/data
EOF

grep -q '^DATES_KEY=' "$SECRETS" || printf '\nDATES_KEY=%s\n' "$key" >> "$SECRETS"
echo "created ~/dateplanner/.env (mode 600); DATES_KEY saved to $SECRETS"
