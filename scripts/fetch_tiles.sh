#!/usr/bin/env bash
# Run ON the Zephyrus. Cuts a Southern California basemap out of the Protomaps daily
# build into /srv/dateplanner/tiles/region.pmtiles (only the needed byte ranges are read).
# Weekly refresh: scripts/install-tiles-cron.sh sets it up on the Zephyrus.
# Bbox: Santa Barbara to San Diego, coast to Palm Springs (covers the 150 km slider max).
set -euo pipefail
BUILD=${BUILD:-$(curl -fsS https://build-metadata.protomaps.dev/builds.json | python3 -c "import sys,json; print(json.load(sys.stdin)[-1]['key'])")}
BBOX=${BBOX:--120.3,32.5,-116.0,35.8}
PMTILES_VERSION=1.31.2
DIR=/srv/dateplanner/tiles
mkdir -p "$DIR" /srv/dateplanner/bin

if [ ! -x /srv/dateplanner/bin/pmtiles ]; then
  curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v$PMTILES_VERSION/go-pmtiles_${PMTILES_VERSION}_Linux_x86_64.tar.gz" \
    | tar -xz -C /srv/dateplanner/bin pmtiles
fi

# A failed or interrupted run leaves the current map untouched
trap 'rm -f "$DIR/region.pmtiles.part"' EXIT
/srv/dateplanner/bin/pmtiles extract "https://build.protomaps.com/$BUILD" "$DIR/region.pmtiles.part" --bbox="$BBOX"
mv "$DIR/region.pmtiles.part" "$DIR/region.pmtiles"
echo "$BUILD $BBOX" > "$DIR/SOURCE"
ls -lh "$DIR/region.pmtiles"
