#!/usr/bin/env bash
# Run ON the Zephyrus. Downloads the prebuilt Photon US database (about 10.5 GB) and
# the Photon jar into /srv/dateplanner/photon. Safe to re-run: it skips finished steps.
set -euo pipefail
PHOTON_VERSION=${PHOTON_VERSION:-1.3.0}
DB_URL=https://download1.graphhopper.com/public/north-america/usa/photon-db-usa-1.0-latest.tar.bz2
DIR=/srv/dateplanner/photon
mkdir -p "$DIR"
cd "$DIR"

command -v lbzip2 >/dev/null || sudo -n apt-get install -y -q lbzip2

if [ ! -f "photon-$PHOTON_VERSION.jar" ]; then
  curl -fsSL -o "photon-$PHOTON_VERSION.jar.part" \
    "https://github.com/komoot/photon/releases/download/$PHOTON_VERSION/photon-$PHOTON_VERSION.jar"
  mv "photon-$PHOTON_VERSION.jar.part" "photon-$PHOTON_VERSION.jar"
fi
ln -sf "photon-$PHOTON_VERSION.jar" photon.jar

if [ ! -f data/.complete ]; then
  rm -rf data.part && mkdir data.part
  # Stream: download, decompress on all cores, unpack. Nothing large hits disk twice.
  curl -fsSL --retry 5 "$DB_URL" | lbzip2 -d | tar -x -C data.part
  rm -rf data && mv data.part data && touch data/.complete
fi
du -sh "$DIR/data"
echo "photon ready"
