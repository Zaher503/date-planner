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
