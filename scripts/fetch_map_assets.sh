#!/usr/bin/env bash
# Run ON the Zephyrus. Downloads the Protomaps basemap glyphs (fonts/) and sprites
# (sprites/) into /srv/dateplanner/tiles/assets, served by the API at /tiles/assets.
# The new copy is unpacked next to the old one and swapped in with a rename.
set -euo pipefail
URL=${URL:-https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz}
DIR=/srv/dateplanner/tiles
NEW="$DIR/assets.new"
OLD="$DIR/assets.old"
mkdir -p "$DIR"
rm -rf "$NEW" "$OLD"
mkdir -p "$NEW"

# The tarball's top folder is basemaps-assets-main/
curl -fsSL "$URL" | tar -xz -C "$NEW" --strip-components=1 --wildcards '*/fonts/*' '*/sprites/*'
test -d "$NEW/fonts" && test -d "$NEW/sprites" || { echo "download had no fonts/ or sprites/"; rm -rf "$NEW"; exit 1; }

[ -d "$DIR/assets" ] && mv "$DIR/assets" "$OLD"
mv "$NEW" "$DIR/assets"
rm -rf "$OLD"
echo "$URL $(date -u +%FT%TZ)" > "$DIR/assets/SOURCE"
du -sh "$DIR/assets/fonts" "$DIR/assets/sprites"
ls "$DIR/assets/fonts" | head -20
