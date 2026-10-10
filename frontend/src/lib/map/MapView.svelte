<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import type { GeoJSONSource, Map as MlMap, MapGeoJSONFeature, Marker } from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
  import type { Candidate, ItemType, MapData } from '$lib/api';
  import { GROUP_COLOR, GROUPS, groupOf } from '$lib/categories';
  import { badge } from '$lib/format';
  import { baseStyle, FONT, type Theme } from './style';

  interface Props {
    data: MapData | null;
    theme: Theme;
    tiles: string;
    assets: string;
    bounds: [number, number, number, number];
    home: { lat: number; lon: number } | null;
    center?: { lat: number; lon: number; zoom: number } | null;
    tz: string;
    selected: string | null;
    candidates?: Candidate[];
    circle?: { lat: number; lon: number; km: number } | null;
    padding?: { top: number; bottom: number; left: number; right: number };
    picking?: boolean;
    onpick?: (pos: { lat: number; lon: number }) => void;
    onview?: (bbox: [number, number, number, number], center: { lat: number; lon: number; zoom: number }) => void;
    onselect?: (t: ItemType, id: string) => void;
    oncandidate?: (id: number) => void;
    onlocate?: (pos: { lat: number; lon: number }) => void;
  }

  let {
    data,
    theme,
    tiles,
    assets,
    bounds,
    home,
    center = null,
    tz,
    selected,
    candidates = [],
    circle = null,
    padding = { top: 0, bottom: 0, left: 0, right: 0 },
    picking = false,
    onpick,
    onview,
    onselect,
    oncandidate,
    onlocate
  }: Props = $props();

  let container: HTMLDivElement;
  let map: MlMap | null = null;
  let ml: typeof import('maplibre-gl') | null = null;
  let homeMarker: Marker | null = null;
  let ready = $state(false);
  let failed = $state('');
  let styleTheme: Theme | null = null;

  const EMPTY_FC = { type: 'FeatureCollection' as const, features: [] };

  // Event pins: a rounded square per colour group, drawn once on a canvas
  function eventIcon(color: string, ratio: number): ImageData {
    const size = 26 * ratio;
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const g = c.getContext('2d')!;
    const r = 7 * ratio;
    const pad = 2 * ratio;
    g.beginPath();
    g.roundRect(pad, pad, size - 2 * pad, size - 2 * pad, r);
    g.fillStyle = color;
    g.fill();
    g.lineWidth = 2 * ratio;
    g.strokeStyle = '#ffffff';
    g.stroke();
    return g.getImageData(0, 0, size, size);
  }

  function addOverlays() {
    if (!map) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 3);
    for (const grp of GROUPS) {
      const id = `ev-${grp}`;
      if (!map.hasImage(id)) map.addImage(id, eventIcon(GROUP_COLOR[grp], ratio), { pixelRatio: ratio });
    }
    const dark = theme === 'dark';
    const ring = dark ? '#16171a' : '#ffffff';
    const groupColor: unknown[] = ['match', ['get', 'g']];
    for (const grp of GROUPS) groupColor.push(grp, GROUP_COLOR[grp]);
    groupColor.push(GROUP_COLOR.other);

    map.addSource('circle', { type: 'geojson', data: EMPTY_FC });
    map.addLayer({
      id: 'circle-fill',
      type: 'fill',
      source: 'circle',
      paint: { 'fill-color': dark ? '#7aa2ff' : '#3b5bdb', 'fill-opacity': 0.05 }
    });
    map.addLayer({
      id: 'circle-line',
      type: 'line',
      source: 'circle',
      paint: { 'line-color': dark ? '#7aa2ff' : '#3b5bdb', 'line-width': 1.5, 'line-dasharray': [3, 2], 'line-opacity': 0.7 }
    });

    map.addSource('items', {
      type: 'geojson',
      data: EMPTY_FC,
      cluster: true,
      clusterMaxZoom: 13,
      clusterRadius: 36,
      promoteId: 'id'
    });
    map.addLayer({
      id: 'clusters',
      type: 'circle',
      source: 'items',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': dark ? '#e9e6e1' : '#24262b',
        'circle-radius': ['step', ['get', 'point_count'], 14, 10, 17, 50, 21],
        'circle-stroke-width': 2,
        'circle-stroke-color': ring
      }
    });
    map.addLayer({
      id: 'cluster-count',
      type: 'symbol',
      source: 'items',
      filter: ['has', 'point_count'],
      layout: {
        'text-field': ['get', 'point_count_abbreviated'],
        'text-font': FONT,
        'text-size': 12,
        'text-allow-overlap': true
      },
      paint: { 'text-color': dark ? '#16171a' : '#ffffff' }
    });
    map.addLayer({
      id: 'selected-ring',
      type: 'circle',
      source: 'items',
      filter: ['==', ['get', 'id'], ''],
      paint: {
        'circle-radius': 17,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-width': 3,
        'circle-stroke-color': dark ? '#ffffff' : '#111111'
      }
    });
    map.addLayer({
      id: 'places',
      type: 'circle',
      source: 'items',
      filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 't'], 'place']],
      paint: {
        'circle-color': groupColor as never,
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 5, 13, 7, 16, 9],
        'circle-stroke-width': 2,
        'circle-stroke-color': ring,
        'circle-opacity': ['case', ['==', ['get', 'rs'], 'suggested'], 0.45, 1],
        'circle-stroke-opacity': ['case', ['==', ['get', 'rs'], 'suggested'], 0.6, 1]
      }
    });
    map.addLayer({
      id: 'events',
      type: 'symbol',
      source: 'items',
      filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 't'], 'event']],
      layout: {
        'icon-image': ['concat', 'ev-', ['get', 'g']],
        'icon-allow-overlap': true,
        'icon-size': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 13, 1, 16, 1.15],
        'text-field': ['get', 'b'],
        'text-font': FONT,
        'text-size': 10.5,
        'text-allow-overlap': true,
        'text-ignore-placement': true
      },
      paint: {
        'text-color': '#ffffff',
        'icon-opacity': ['case', ['==', ['get', 'rs'], 'suggested'], 0.5, 1],
        'text-opacity': ['case', ['==', ['get', 'rs'], 'suggested'], 0.7, 1]
      }
    });
    // Needs review: a small amber dot on the pin's shoulder
    map.addLayer({
      id: 'review-dot',
      type: 'circle',
      source: 'items',
      filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'rs'], 'needs_review']],
      paint: {
        'circle-radius': 4,
        'circle-color': '#f59f00',
        'circle-stroke-width': 1.5,
        'circle-stroke-color': ring,
        'circle-translate': [8, -8]
      }
    });
    map.addLayer({
      id: 'labels',
      type: 'symbol',
      source: 'items',
      minzoom: 13,
      filter: ['!', ['has', 'point_count']],
      layout: {
        'text-field': ['get', 'title'],
        'text-font': FONT,
        'text-size': 12,
        'text-anchor': 'left',
        'text-offset': [1.1, 0],
        'text-max-width': 10,
        'text-optional': true
      },
      paint: {
        'text-color': dark ? '#f1efe9' : '#1d1f24',
        'text-halo-color': dark ? 'rgba(22,23,26,0.9)' : 'rgba(255,255,255,0.95)',
        'text-halo-width': 1.5
      }
    });

    map.addSource('candidates', { type: 'geojson', data: EMPTY_FC });
    map.addLayer({
      id: 'candidates',
      type: 'circle',
      source: 'candidates',
      paint: {
        'circle-radius': 11,
        'circle-color': ['case', ['get', 'chosen'], '#2f9e44', dark ? '#e9e6e1' : '#24262b'],
        'circle-stroke-width': 2,
        'circle-stroke-color': ring
      }
    });
    map.addLayer({
      id: 'candidate-letters',
      type: 'symbol',
      source: 'candidates',
      layout: { 'text-field': ['get', 'letter'], 'text-font': FONT, 'text-size': 12, 'text-allow-overlap': true },
      paint: { 'text-color': ['case', ['get', 'chosen'], '#ffffff', dark ? '#16171a' : '#ffffff'] }
    });
  }

  function decorate(d: MapData | null) {
    if (!d) return EMPTY_FC;
    return {
      type: 'FeatureCollection' as const,
      features: d.features.map((f) => ({
        ...f,
        properties: { ...f.properties, g: groupOf(f.properties.cat), b: f.properties.t === 'event' ? badge(f.properties, tz) : '' }
      }))
    };
  }

  function circlePolygon(c: { lat: number; lon: number; km: number }) {
    const pts: [number, number][] = [];
    const R = 6371;
    const lat1 = (c.lat * Math.PI) / 180;
    const lon1 = (c.lon * Math.PI) / 180;
    const d = c.km / R;
    for (let i = 0; i <= 96; i++) {
      const brng = (i / 96) * 2 * Math.PI;
      const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
      const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));
      pts.push([(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI]);
    }
    return { type: 'FeatureCollection' as const, features: [{ type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [pts] } }] };
  }

  function syncData() {
    if (!map || !ready) return;
    (map.getSource('items') as GeoJSONSource | undefined)?.setData(decorate(data) as never);
  }

  function syncSelected() {
    if (!map || !ready) return;
    map.setFilter('selected-ring', ['all', ['!', ['has', 'point_count']], ['==', ['get', 'id'], selected ?? '']]);
  }

  function syncCandidates() {
    if (!map || !ready) return;
    const fc = {
      type: 'FeatureCollection' as const,
      features: candidates.map((c, i) => ({
        type: 'Feature' as const,
        properties: { id: c.id, letter: String.fromCharCode(65 + i), chosen: c.chosen },
        geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] }
      }))
    };
    (map.getSource('candidates') as GeoJSONSource | undefined)?.setData(fc as never);
  }

  function syncCircle() {
    if (!map || !ready) return;
    (map.getSource('circle') as GeoJSONSource | undefined)?.setData((circle ? circlePolygon(circle) : EMPTY_FC) as never);
  }

  function emitView() {
    if (!map) return;
    const b = map.getBounds();
    const c = map.getCenter();
    onview?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], { lat: c.lat, lon: c.lng, zoom: map.getZoom() });
  }

  function placeHome() {
    if (!map || !ml || !home) return;
    if (!homeMarker) {
      const el = document.createElement('div');
      el.className = 'home-marker';
      el.title = 'Home';
      el.innerHTML =
        '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>';
      homeMarker = new ml.Marker({ element: el }).setLngLat([home.lon, home.lat]).addTo(map);
    } else {
      homeMarker.setLngLat([home.lon, home.lat]);
    }
  }

  export function flyTo(lon: number, lat: number, zoom?: number) {
    if (!map) return;
    map.flyTo({ center: [lon, lat], zoom: Math.max(zoom ?? map.getZoom(), 14), padding, speed: 1.6 });
  }

  export function fitPoints(points: { lat: number; lon: number }[]) {
    if (!map || !ml || !points.length) return;
    if (points.length === 1) return flyTo(points[0].lon, points[0].lat, 15);
    const b = new ml.LngLatBounds();
    for (const p of points) b.extend([p.lon, p.lat]);
    map.fitBounds(b, { padding: { top: padding.top + 60, bottom: padding.bottom + 60, left: padding.left + 60, right: padding.right + 60 }, maxZoom: 16 });
  }

  export function resize() {
    map?.resize();
  }

  onMount(() => {
    let cancelled = false;
    (async () => {
      try {
        const [maplibre, { Protocol }] = await Promise.all([import('maplibre-gl'), import('pmtiles')]);
        if (cancelled) return;
        ml = maplibre;
        maplibre.setWorkerUrl(workerUrl);
        const protocol = new Protocol();
        maplibre.addProtocol('pmtiles', protocol.tile);
        styleTheme = theme;
        const start = center ?? (home ? { ...home, zoom: 11 } : { lat: 34.05, lon: -118.25, zoom: 10 });
        const [w, s, e, n] = bounds;
        map = new maplibre.Map({
          container,
          style: baseStyle(theme, tiles, assets),
          center: [start.lon, start.lat],
          zoom: start.zoom,
          minZoom: 6,
          maxZoom: 18,
          maxBounds: [
            [w - 1.5, s - 1.5],
            [e + 1.5, n + 1.5]
          ],
          attributionControl: { compact: true },
          dragRotate: false,
          pitchWithRotate: false,
          localIdeographFontFamily: 'sans-serif'
        });
        map.touchZoomRotate.disableRotation();
        map.addControl(new maplibre.NavigationControl({ showCompass: false }), 'bottom-right');
        const geo = new maplibre.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false });
        geo.on('geolocate', (e: { coords: GeolocationCoordinates }) => onlocate?.({ lat: e.coords.latitude, lon: e.coords.longitude }));
        map.addControl(geo, 'bottom-right');

        map.on('style.load', () => {
          addOverlays();
          ready = true;
          syncData();
          syncSelected();
          syncCandidates();
          syncCircle();
        });
        map.on('load', () => {
          placeHome();
          emitView();
        });
        map.on('moveend', emitView);
        map.on('error', (e) => console.warn('map', e.error?.message ?? e));

        // While moving a pin, any click places it; feature clicks are ignored
        map.on('click', (e) => {
          if (picking) onpick?.({ lat: e.lngLat.lat, lon: e.lngLat.lng });
        });
        const pick = (e: { features?: MapGeoJSONFeature[] }) => {
          if (picking) return;
          const f = e.features?.[0];
          if (f) onselect?.(f.properties.t, f.properties.id);
        };
        map.on('click', 'places', pick);
        map.on('click', 'events', pick);
        map.on('click', 'clusters', async (e) => {
          const f = e.features?.[0];
          if (!f || !map || picking) return;
          const src = map.getSource('items') as GeoJSONSource;
          const zoom = await src.getClusterExpansionZoom(f.properties.cluster_id);
          map.easeTo({ center: (f.geometry as unknown as { coordinates: [number, number] }).coordinates, zoom: zoom + 0.3, padding });
        });
        map.on('click', 'candidates', (e) => {
          if (picking) return;
          const f = e.features?.[0];
          if (f) oncandidate?.(Number(f.properties.id));
        });
        for (const layer of ['places', 'events', 'clusters', 'candidates']) {
          map.on('mouseenter', layer, () => map && (map.getCanvas().style.cursor = 'pointer'));
          map.on('mouseleave', layer, () => map && (map.getCanvas().style.cursor = picking ? 'crosshair' : ''));
        }
      } catch (err) {
        failed = err instanceof Error ? err.message : String(err);
      }
    })();
    return () => {
      cancelled = true;
    };
  });

  onDestroy(() => {
    map?.remove();
    map = null;
  });

  $effect(() => {
    void data;
    syncData();
  });
  $effect(() => {
    void selected;
    syncSelected();
  });
  $effect(() => {
    void candidates;
    syncCandidates();
  });
  $effect(() => {
    void circle;
    syncCircle();
  });
  $effect(() => {
    void home;
    placeHome();
  });
  $effect(() => {
    if (map) map.getCanvas().style.cursor = picking ? 'crosshair' : '';
  });
  $effect(() => {
    // Swap the basemap flavour; overlays are re-added on style.load
    if (map && theme !== styleTheme) {
      styleTheme = theme;
      ready = false;
      map.setStyle(baseStyle(theme, tiles, assets), { diff: false });
    }
  });
</script>

<div class="map" bind:this={container}></div>
{#if failed}
  <div class="map-error">The map could not load: {failed}</div>
{/if}

<style>
  .map {
    position: absolute;
    inset: 0;
  }
  .map-error {
    position: absolute;
    inset: auto 16px 50% 16px;
    padding: 12px 14px;
    border-radius: 12px;
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow);
    text-align: center;
  }
  :global(.home-marker) {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--accent);
    color: var(--on-accent);
    border: 2px solid var(--surface);
    box-shadow: 0 1px 4px rgb(0 0 0 / 0.35);
  }
  :global(.maplibregl-ctrl-group) {
    background: var(--surface) !important;
    border-radius: 10px !important;
    box-shadow: var(--shadow) !important;
  }
  :global(.maplibregl-ctrl-group button + button) {
    border-top-color: var(--line) !important;
  }
  :global([data-theme='dark'] .maplibregl-ctrl-icon) {
    filter: invert(1);
  }
  :global(.maplibregl-ctrl-attrib) {
    font-size: 11px;
  }
</style>
