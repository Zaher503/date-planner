#!/usr/bin/env bash
# Run ON the Zephyrus. Builds OSRM routing data (car and foot, MLD) for Southern California
# into /srv/dateplanner/osrm/{car,foot}. Re-run monthly to pick up new roads.
set -euo pipefail
OSRM_IMAGE=${OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:v26.10.0-debian}
PBF_URL=https://download.geofabrik.de/north-america/us/california/socal-latest.osm.pbf
DIR=/srv/dateplanner/osrm
# The laptop hard-powered-off during a full 16-thread build, so keep it gentle
THREADS=${THREADS:-4}
PROFILES=${PROFILES:-car foot}
mkdir -p "$DIR"

curl -fsSL --retry 5 -z "$DIR/socal.osm.pbf" -o "$DIR/socal.osm.pbf" "$PBF_URL"

for profile in $PROFILES; do
  out="$DIR/$profile.new"
  rm -rf "$out" && mkdir -p "$out"
  ln "$DIR/socal.osm.pbf" "$out/socal.osm.pbf"
  docker run --rm --cpus "$THREADS" -v "$out:/data" "$OSRM_IMAGE" osrm-extract -t "$THREADS" -p "/opt/$profile.lua" /data/socal.osm.pbf
  docker run --rm -v "$out:/data" --cpus "$THREADS" "$OSRM_IMAGE" osrm-partition -t "$THREADS" /data/socal.osrm
  docker run --rm -v "$out:/data" --cpus "$THREADS" "$OSRM_IMAGE" osrm-customize -t "$THREADS" /data/socal.osrm
  rm "$out/socal.osm.pbf"
  rm -rf "$DIR/$profile.old"
  [ -d "$DIR/$profile" ] && mv "$DIR/$profile" "$DIR/$profile.old"
  mv "$out" "$DIR/$profile"
done
rm -rf "$DIR"/*.old "$DIR"/*.new
du -sh "$DIR"/*/
