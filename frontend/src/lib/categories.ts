import { pinColors } from './pincolors.svelte';

// Category vocabulary (backend app/ingest/items.py) grouped into colour families for pins

export type Group = 'food' | 'drinks' | 'music' | 'arts' | 'outdoors' | 'shopping' | 'activity' | 'other';

export const GROUP_OF: Record<string, Group> = {
  restaurant: 'food',
  cafe: 'food',
  dessert: 'food',
  bar: 'drinks',
  nightlife: 'drinks',
  live_music: 'music',
  show: 'music',
  comedy: 'music',
  festival: 'music',
  arts: 'arts',
  museum: 'arts',
  class: 'arts',
  outdoors: 'outdoors',
  beach: 'outdoors',
  park: 'outdoors',
  hike: 'outdoors',
  viewpoint: 'outdoors',
  market: 'shopping',
  shopping: 'shopping',
  activity: 'activity',
  sports: 'activity',
  spa: 'activity',
  other: 'other'
};

// Pin colours, readable on both light and dark basemaps
export const GROUP_COLOR: Record<Group, string> = {
  food: '#e8590c',
  drinks: '#9c36b5',
  music: '#d6336c',
  arts: '#1c7ed6',
  outdoors: '#2b8a3e',
  shopping: '#c48a00',
  activity: '#0c8599',
  other: '#6c727f'
};

export const GROUPS = Object.keys(GROUP_COLOR) as Group[];

// Default pin colour for every category; people can change each one in Settings
export const DEFAULT_CATEGORY_COLOR: Record<string, string> = {
  restaurant: '#e8590c',
  cafe: '#a9622b',
  dessert: '#e64980',
  bar: '#9c36b5',
  nightlife: '#6741d9',
  live_music: '#d6336c',
  show: '#c2255c',
  comedy: '#f76707',
  festival: '#f08c00',
  arts: '#1c7ed6',
  museum: '#1864ab',
  class: '#4263eb',
  outdoors: '#2b8a3e',
  beach: '#15aabf',
  park: '#2f9e44',
  hike: '#5c940d',
  viewpoint: '#0b7285',
  market: '#c48a00',
  shopping: '#a8710a',
  activity: '#0c8599',
  sports: '#1098ad',
  spa: '#20c997',
  other: '#6c727f'
};

export const CATEGORY_LABEL: Record<string, string> = {
  restaurant: 'Restaurant',
  cafe: 'Cafe',
  dessert: 'Dessert',
  bar: 'Bar',
  nightlife: 'Nightlife',
  live_music: 'Live music',
  show: 'Show',
  comedy: 'Comedy',
  festival: 'Festival',
  arts: 'Arts',
  museum: 'Museum',
  class: 'Class',
  outdoors: 'Outdoors',
  beach: 'Beach',
  park: 'Park',
  hike: 'Hike',
  viewpoint: 'Viewpoint',
  market: 'Market',
  shopping: 'Shopping',
  activity: 'Activity',
  sports: 'Sports',
  spa: 'Spa',
  other: 'Other'
};

export const CATEGORIES = Object.keys(CATEGORY_LABEL);

export function groupOf(cat: string | null | undefined): Group {
  return GROUP_OF[cat ?? ''] ?? 'other';
}

// Unknown categories draw as 'other'
export function categoryKey(cat: string | null | undefined): string {
  return cat && cat in DEFAULT_CATEGORY_COLOR ? cat : 'other';
}

export function colorOf(cat: string | null | undefined): string {
  const key = categoryKey(cat);
  return pinColors.overrides[key] ?? DEFAULT_CATEGORY_COLOR[key];
}

export function labelOf(cat: string | null | undefined): string {
  if (!cat) return 'Other';
  return CATEGORY_LABEL[cat] ?? cat.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

// The category filters shown in the Filters panel: each one covers several categories
export const CATEGORY_FILTERS: { key: string; label: string; cats: string[] }[] = [
  { key: 'food', label: 'Food & drinks', cats: ['restaurant', 'cafe', 'dessert', 'bar', 'nightlife'] },
  { key: 'music', label: 'Music & shows', cats: ['live_music', 'show', 'comedy', 'festival'] },
  { key: 'arts', label: 'Arts & culture', cats: ['arts', 'museum', 'class'] },
  { key: 'outdoors', label: 'Outdoors', cats: ['outdoors', 'beach', 'park', 'hike', 'viewpoint'] },
  { key: 'shopping', label: 'Markets & shopping', cats: ['market', 'shopping'] }
];

/** A filter is on when every one of its categories is selected. */
export function categoryFilterOn(cats: string[], f: { cats: string[] }): boolean {
  return f.cats.length > 0 && cats.every((c) => f.cats.includes(c));
}

/** Turn a category filter on or off, leaving other categories as they are. */
export function toggleCategoryFilter(cats: string[], selected: string[]): string[] {
  return categoryFilterOn(cats, { cats: selected })
    ? selected.filter((c) => !cats.includes(c))
    : [...selected, ...cats.filter((c) => !selected.includes(c))];
}

/** Tokens for the selected categories: a whole group reads as its name, strays as their own. */
export function categoryTokens(selected: string[]): { key: string; label: string; remove: (cats: string[]) => string[] }[] {
  const out: { key: string; label: string; remove: (cats: string[]) => string[] }[] = [];
  const covered = new Set<string>();
  for (const g of CATEGORY_FILTERS) {
    if (!categoryFilterOn(g.cats, { cats: selected })) continue;
    g.cats.forEach((c) => covered.add(c));
    out.push({ key: `cat:${g.key}`, label: g.label, remove: (cats) => cats.filter((c) => !g.cats.includes(c)) });
  }
  for (const c of selected) if (!covered.has(c)) out.push({ key: `cat:${c}`, label: labelOf(c), remove: (cats) => cats.filter((x) => x !== c) });
  return out;
}
