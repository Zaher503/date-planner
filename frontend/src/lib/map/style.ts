// Basemap style: Protomaps layers over the self-hosted SoCal PMTiles, local glyphs and sprites

import { layers, namedFlavor } from '@protomaps/basemaps';
import type { StyleSpecification } from 'maplibre-gl';

export type Theme = 'light' | 'dark';

export const FONT = ['Noto Sans Medium'];
export const FONT_REGULAR = ['Noto Sans Regular'];

export function baseStyle(theme: Theme, tilesPath: string, assetsPath: string): StyleSpecification {
  const origin = location.origin;
  // Basemap POI icons would compete with our pins, so the flavor drops them
  const flavor = { ...namedFlavor(theme), pois: undefined };
  return {
    version: 8,
    glyphs: `${origin}${assetsPath}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${origin}${assetsPath}/sprites/v4/${theme}`,
    sources: {
      protomaps: {
        type: 'vector',
        url: `pmtiles://${origin}${tilesPath}`,
        attribution: '<a href="https://protomaps.com">Protomaps</a> &copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>'
      }
    },
    layers: layers('protomaps', flavor as ReturnType<typeof namedFlavor>, { lang: 'en' })
  };
}

// Free live basemap (OpenFreeMap, no key) for areas outside the downloaded region
const LIVE_URL = 'https://tiles.openfreemap.org/styles/positron';
export const LIVE_FONT = ['Noto Sans Bold'];
let liveRaw: StyleSpecification | null = null;

export async function liveStyle(theme: Theme): Promise<StyleSpecification> {
  if (!liveRaw) {
    const r = await fetch(LIVE_URL);
    if (!r.ok) throw new Error(`live map style: HTTP ${r.status}`);
    liveRaw = (await r.json()) as StyleSpecification;
  }
  const style = structuredClone(liveRaw);
  if (theme === 'dark') {
    // The live style only ships a light look, so recolour it to match the dark flavour
    for (const l of style.layers) {
      const id = l.id;
      const paint = (l.paint ??= {}) as Record<string, unknown>;
      if (l.type === 'background') paint['background-color'] = '#1d1f23';
      else if (l.type === 'fill') {
        const green = /park|wood|grass|forest|green/.test(id);
        const water = /water/.test(id);
        paint['fill-color'] = water ? '#0f1216' : green ? '#1c2a22' : '#25272c';
        delete paint['fill-outline-color'];
      } else if (l.type === 'line') {
        paint['line-color'] = /water/.test(id) ? '#0f1216' : /boundary/.test(id) ? '#4a4d55' : '#3a3d44';
      } else if (l.type === 'symbol') {
        paint['text-color'] = '#b3b5bc';
        paint['text-halo-color'] = '#16171a';
      } else if (l.type === 'raster') paint['raster-opacity'] = 0;
    }
  }
  return style;
}
