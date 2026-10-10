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

export function colorOf(cat: string | null | undefined): string {
  return GROUP_COLOR[groupOf(cat)];
}

export function labelOf(cat: string | null | undefined): string {
  if (!cat) return 'Other';
  return CATEGORY_LABEL[cat] ?? cat.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}
