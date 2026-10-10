#!/usr/bin/env bash
# Ship the committed HEAD to the Zephyrus and rebuild the stack.
# Usage: scripts/deploy.sh [service ...]   (no args = whole stack)
# Remote layout: ~/dateplanner/src (replaced each deploy), ~/dateplanner/.env (kept)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [ -n "$(git status --porcelain)" ]; then
  echo "note: uncommitted changes are NOT deployed (only HEAD)"
fi
rev=$(git rev-parse --short HEAD)
echo "deploying $rev"

git archive --format=tar HEAD | ssh zephyrus "set -e
  test -f ~/dateplanner/.env || { echo 'missing ~/dateplanner/.env, run scripts/init-env.sh first'; exit 1; }
  rm -rf ~/dateplanner/src.new && mkdir -p ~/dateplanner/src.new
  tar -xf - -C ~/dateplanner/src.new
  echo $rev > ~/dateplanner/src.new/REVISION
  ln -sf ~/dateplanner/.env ~/dateplanner/src.new/deploy/.env
  rm -rf ~/dateplanner/src.old
  [ -d ~/dateplanner/src ] && mv ~/dateplanner/src ~/dateplanner/src.old
  mv ~/dateplanner/src.new ~/dateplanner/src
  sudo -n mkdir -p /srv/dateplanner /srv/gpu
  sudo -n chown zaher:zaher /srv/dateplanner
  sudo -n chmod 1777 /srv/gpu
  cd ~/dateplanner/src/deploy
  docker compose up -d --build --remove-orphans $*
  docker compose ps --format '{{.Service}}: {{.Status}}'"
