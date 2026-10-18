#!/usr/bin/env bash
# Run ON the Zephyrus. Installs scripts/fetch_tiles.sh as ~/bin/fetch-tiles.sh and schedules it for
# Sundays at 03:30 (the same region and Protomaps source as the first download), logging to ~/bin/tiles.log.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HOME/bin"
install -m 755 "$here/fetch_tiles.sh" "$HOME/bin/fetch-tiles.sh"
line='30 3 * * 0 flock -n /tmp/fetch-tiles.lock $HOME/bin/fetch-tiles.sh >> $HOME/bin/tiles.log 2>&1'
( crontab -l 2>/dev/null | grep -v 'fetch-tiles.sh' || true; echo "$line" ) | crontab -
crontab -l | grep fetch-tiles
