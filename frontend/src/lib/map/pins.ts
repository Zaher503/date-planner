// Teardrop map pins drawn as SVG and rasterised for MapLibre: one per category, a blank one per category
// (cluster of a single category) and a rainbow one (cluster of mixed categories)
import { GLYPH } from './glyphs';

export const PIN_W = 32;
export const PIN_H = 42;
// The head circle's centre, measured from the pin's top
const HEAD_Y = 15.5;
const TEARDROP = 'M16 40C9 31 3.5 24 3.5 15.5a12.5 12.5 0 0 1 25 0C28.5 24 23 31 16 40Z';
const RAINBOW = ['#e03131', '#f76707', '#fab005', '#40c057', '#228be6', '#7048e8'];

// Distance from the pin tip (where it is anchored) up to the head centre, in px
export const HEAD_FROM_TIP_PX = PIN_H - HEAD_Y;

function wrap(body: string, edge: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${PIN_W}" height="${PIN_H}" viewBox="0 0 ${PIN_W} ${PIN_H}">` +
    `<defs><clipPath id="t"><path d="${TEARDROP}"/></clipPath></defs>${body}` +
    `<path d="${TEARDROP}" fill="none" stroke="${edge}" stroke-width="2"/></svg>`
  );
}

export function pinSvg(color: string, glyph: string | null, edge = '#ffffff'): string {
  // Lucide is a 24px grid; 15px keeps the glyph inside the head with room around it
  const s = 16 / 24;
  const g = glyph
    ? `<g transform="translate(${16 - 12 * s} ${HEAD_Y - 12 * s}) scale(${s})" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${GLYPH[glyph] ?? GLYPH.other}</g>`
    : '';
  return wrap(`<path d="${TEARDROP}" fill="${color}"/>${g}`, edge);
}

export function rainbowSvg(edge = '#ffffff'): string {
  const cx = 16;
  const cy = HEAD_Y;
  const R = 40;
  const wedges = RAINBOW.map((c, i) => {
    const a0 = (i * 60 - 90) * (Math.PI / 180);
    const a1 = ((i + 1) * 60 - 90) * (Math.PI / 180);
    const p = (a: number) => `${(cx + R * Math.cos(a)).toFixed(2)} ${(cy + R * Math.sin(a)).toFixed(2)}`;
    return `<path d="M${cx} ${cy}L${p(a0)}L${p(a1)}Z" fill="${c}"/>`;
  }).join('');
  return wrap(`<g clip-path="url(#t)">${wedges}</g>`, edge);
}

export function rasterise(svg: string, ratio: number): Promise<ImageData> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = PIN_W * ratio;
      c.height = PIN_H * ratio;
      const g = c.getContext('2d')!;
      g.drawImage(img, 0, 0, c.width, c.height);
      resolve(g.getImageData(0, 0, c.width, c.height));
    };
    img.onerror = () => reject(new Error('pin image failed'));
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  });
}

// Thick outline that follows the pin's shape, drawn under the selected pin
export function outlineSvg(color: string): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${PIN_W}" height="${PIN_H}" viewBox="0 0 ${PIN_W} ${PIN_H}">` +
    `<path d="${TEARDROP}" fill="${color}" stroke="${color}" stroke-width="6" stroke-linejoin="round"/></svg>`
  );
}
