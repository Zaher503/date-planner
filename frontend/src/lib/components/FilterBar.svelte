<script lang="ts">
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import Plus from '@lucide/svelte/icons/plus';
  import type { Facets } from '$lib/api';
  import { labelOf } from '$lib/categories';
  import { EMPTY, PRICE_LABEL, STATUS_LABEL, WHEN_LABEL, toggle, type Filters, type When } from '$lib/filters';
  import { kmToMi, miToKm } from '$lib/format';

  interface Props {
    filters: Filters;
    facets: Facets;
    units: 'mi' | 'km';
    radiusKm: number;
    reviewCount: number;
    onchange: (f: Filters) => void;
    onnear: (near: 'home' | 'me') => void;
    onadd: () => void;
  }

  let { filters, facets, units, radiusKm, reviewCount, onchange, onnear, onadd }: Props = $props();

  type Panel = 'when' | 'price' | 'tags' | 'distance' | 'status' | 'type' | null;
  let open = $state<Panel>(null);
  let showFilters = $state(false);
  let query = $state('');
  let root: HTMLDivElement;
  let timer: ReturnType<typeof setTimeout> | null = null;

  // Keep the box in sync when the URL changes from elsewhere (back button, clear)
  $effect(() => {
    if (document.activeElement?.id !== 'search') query = filters.q;
  });

  function set(patch: Partial<Filters>) {
    onchange({ ...filters, ...patch });
  }

  function typed() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => set({ q: query }), 300);
  }

  function clearAll() {
    query = '';
    open = null;
    onchange({ ...EMPTY, near: filters.near });
  }

  function toggleFilters() {
    showFilters = !showFilters;
    if (!showFilters) open = null;
  }

  function toggleOpen(p: Panel) {
    open = open === p ? null : p;
  }

  function outside(e: PointerEvent) {
    if (open && root && !root.contains(e.target as Node)) open = null;
  }

  const whenLabel = $derived(
    filters.when === 'range' && filters.from
      ? `${filters.from.slice(5).replace('-', '/')}${filters.to && filters.to !== filters.from ? ' to ' + filters.to.slice(5).replace('-', '/') : ''}`
      : filters.when
        ? WHEN_LABEL[filters.when]
        : filters.open_now
          ? 'Open now'
          : 'When'
  );
  const priceLabel = $derived(filters.price.length ? filters.price.map((p) => PRICE_LABEL[p]).join(', ') : 'Price');
  const tagCount = $derived(filters.tags.length + filters.cats.length);
  const tagLabel = $derived(
    tagCount === 1 ? (filters.tags[0] ?? labelOf(filters.cats[0])) : tagCount ? `${tagCount} tags` : 'Tags'
  );
  const distLabel = $derived(
    filters.dist_km
      ? units === 'mi'
        ? `${Math.round(kmToMi(filters.dist_km))} mi`
        : `${Math.round(filters.dist_km)} km`
      : 'Distance'
  );
  const statusLabel = $derived(
    filters.status.length === 1 ? STATUS_LABEL[filters.status[0]] : filters.status.length ? `${filters.status.length} statuses` : 'Status'
  );
  const typeLabel = $derived(filters.types.length === 1 ? (filters.types[0] === 'place' ? 'Places' : 'Events') : 'Type');
  const anyActive = $derived(
    !!(filters.q || filters.when || filters.open_now || filters.past || filters.price.length || tagCount || filters.dist_km || filters.status.length || filters.types.length === 1)
  );

  const activeCount = $derived(
    [!!filters.when || filters.open_now || filters.past, filters.price.length > 0, tagCount > 0, !!filters.dist_km, filters.status.length > 0, filters.types.length === 1].filter(Boolean).length
  );

  // Distance slider works in the display unit
  const distMin = $derived(units === 'mi' ? 3 : 5);
  const distMax = $derived(units === 'mi' ? 95 : 150);
  const distValue = $derived(
    filters.dist_km ? (units === 'mi' ? Math.round(kmToMi(filters.dist_km)) : Math.round(filters.dist_km)) : units === 'mi' ? Math.round(kmToMi(radiusKm)) : Math.round(radiusKm)
  );

  function slide(e: Event) {
    const v = Number((e.target as HTMLInputElement).value);
    set({ dist_km: units === 'mi' ? miToKm(v) : v });
  }

  const whens: When[] = ['', 'today', 'weekend', 'week'];
  let tagFilter = $state('');
  const shownTags = $derived(
    facets.tags.filter((t) => !tagFilter || t.tag.includes(tagFilter.toLowerCase())).slice(0, 60)
  );
</script>

<svelte:window onpointerdown={outside} onkeydown={(e) => e.key === 'Escape' && (open = null)} />

<div class="bar" bind:this={root}>
  <div class="row">
    <label class="search">
      <Search size={18} />
      <span class="sr-only">Search</span>
      <input
        id="search"
        type="search"
        placeholder="Search places and events"
        autocomplete="off"
        bind:value={query}
        oninput={typed}
        onkeydown={(e) => e.key === 'Enter' && (timer && clearTimeout(timer), set({ q: query }))}
      />
      {#if query}
        <button class="clear" aria-label="Clear search" onclick={() => ((query = ''), set({ q: '' }))}><X size={16} /></button>
      {/if}
    </label>
    <button class="icon-btn add-desk" aria-label="Add a link" title="Add a link" onclick={onadd}><Plus size={20} /></button>
    {#if reviewCount}
      <button
        class="icon-btn review"
        class:on={filters.status.length === 1 && filters.status[0] === 'review'}
        aria-label="{reviewCount} pins need a check"
        title="{reviewCount} pins need a check"
        onclick={() => set({ status: filters.status.length === 1 && filters.status[0] === 'review' ? [] : ['review'] })}
      >
        <TriangleAlert size={19} />
        <span class="count">{reviewCount}</span>
      </button>
    {/if}
    <button
      class="icon-btn filter-btn"
      class:on={showFilters || activeCount > 0}
      aria-label="Filters"
      title="Filters"
      aria-expanded={showFilters}
      onclick={toggleFilters}
    >
      <SlidersHorizontal size={19} />
      {#if activeCount}<span class="count dot">{activeCount}</span>{/if}
    </button>
  </div>

  {#if showFilters}
  <div class="chips" role="toolbar" aria-label="Filters">
    <button class="chip" class:on={!!filters.when || filters.open_now || filters.past} onclick={() => toggleOpen('when')} aria-expanded={open === 'when'}>
      {whenLabel}<ChevronDown size={14} />
    </button>
    <button class="chip" class:on={filters.price.length > 0} onclick={() => toggleOpen('price')} aria-expanded={open === 'price'}>
      {priceLabel}<ChevronDown size={14} />
    </button>
    <button class="chip" class:on={tagCount > 0} onclick={() => toggleOpen('tags')} aria-expanded={open === 'tags'}>
      {tagLabel}<ChevronDown size={14} />
    </button>
    <button class="chip" class:on={!!filters.dist_km} onclick={() => toggleOpen('distance')} aria-expanded={open === 'distance'}>
      {distLabel}<ChevronDown size={14} />
    </button>
    <button class="chip" class:on={filters.status.length > 0} onclick={() => toggleOpen('status')} aria-expanded={open === 'status'}>
      {statusLabel}<ChevronDown size={14} />
    </button>
    <button class="chip" class:on={filters.types.length === 1} onclick={() => toggleOpen('type')} aria-expanded={open === 'type'}>
      {typeLabel}<ChevronDown size={14} />
    </button>
    {#if anyActive}
      <button class="chip clear-all" onclick={clearAll}><X size={14} />Clear</button>
    {/if}
  </div>
  {/if}

  {#if open}
    <div class="pop" role="dialog" aria-label="Filter options">
      {#if open === 'when'}
        <div class="opts">
          {#each whens as w (w)}
            <button class="chip" class:on={filters.when === w} onclick={() => set({ when: w })}>{WHEN_LABEL[w]}</button>
          {/each}
        </div>
        <label class="switch">
          <input type="checkbox" checked={filters.open_now} onchange={(e) => set({ open_now: e.currentTarget.checked })} />
          <span>Open now</span>
        </label>
      {:else if open === 'price'}
        <div class="opts">
          {#each Object.entries(PRICE_LABEL) as [k, label] (k)}
            <button class="chip" class:on={filters.price.includes(k)} onclick={() => set({ price: toggle(filters.price, k) })}>{label}</button>
          {/each}
        </div>
        <p class="hint">$ is under $20 a person, $$ is $20 to $50, $$$ is more. Items with no known price are hidden while a price is picked.</p>
      {:else if open === 'tags'}
        {#if facets.categories.length}
          <span class="label">Categories</span>
          <div class="opts">
            {#each facets.categories as c (c.cat)}
              <button class="chip" class:on={filters.cats.includes(c.cat)} onclick={() => set({ cats: toggle(filters.cats, c.cat) })}>
                {labelOf(c.cat)} <span class="n">{c.n}</span>
              </button>
            {/each}
          </div>
        {/if}
        <span class="label">Tags (all must match)</span>
        {#if facets.tags.length > 12}
          <input class="field tag-search" placeholder="Find a tag" bind:value={tagFilter} />
        {/if}
        <div class="opts scroll">
          {#each shownTags as t (t.tag)}
            <button class="chip" class:on={filters.tags.includes(t.tag)} onclick={() => set({ tags: toggle(filters.tags, t.tag) })}>
              {t.tag} <span class="n">{t.n}</span>
            </button>
          {:else}
            <span class="hint">No tags yet.</span>
          {/each}
        </div>
      {:else if open === 'distance'}
        <label class="switch">
          <input type="checkbox" checked={!!filters.dist_km} onchange={(e) => set({ dist_km: e.currentTarget.checked ? radiusKm : null })} />
          <span>Limit distance</span>
        </label>
        <div class="slider" class:off={!filters.dist_km}>
          <input type="range" min={distMin} max={distMax} step="1" value={distValue} disabled={!filters.dist_km} oninput={slide} aria-label="Maximum distance" />
          <span class="val">{distValue} {units}</span>
        </div>
        <span class="label">From</span>
        <div class="opts">
          <button class="chip" class:on={filters.near === 'home'} onclick={() => onnear('home')}>Home</button>
          <button class="chip" class:on={filters.near === 'me'} onclick={() => onnear('me')}>My location</button>
        </div>
      {:else if open === 'status'}
        <div class="opts">
          {#each Object.entries(STATUS_LABEL) as [k, label] (k)}
            <button class="chip" class:on={filters.status.includes(k)} onclick={() => set({ status: toggle(filters.status, k) })}>{label}</button>
          {/each}
        </div>
      {:else if open === 'type'}
        <div class="opts">
          <button class="chip" class:on={filters.types.length !== 1} onclick={() => set({ types: [] })}>Places and events</button>
          <button class="chip" class:on={filters.types.length === 1 && filters.types[0] === 'place'} onclick={() => set({ types: ['place'] })}>Places</button>
          <button class="chip" class:on={filters.types.length === 1 && filters.types[0] === 'event'} onclick={() => set({ types: ['event'] })}>Events</button>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .bar {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 4px;
    background: var(--surface);
    border-radius: 14px;
    padding: 3px 4px 3px 12px;
    box-shadow: var(--shadow);
  }
  .search {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: var(--text-3);
  }
  .search input {
    flex: 1;
    min-width: 0;
    height: 40px;
    border: none;
    background: transparent;
    outline: none;
    color: var(--text);
    font-size: 16px;
  }
  .search input::-webkit-search-cancel-button {
    display: none;
  }
  .clear {
    border: none;
    background: var(--surface-2);
    color: var(--text-2);
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: grid;
    place-items: center;
  }
  .review {
    color: var(--warn);
  }
  .review.on {
    background: var(--warn-soft);
  }
  .count {
    position: absolute;
    top: 3px;
    right: 2px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--warn);
    color: var(--surface);
    font-size: 10.5px;
    font-weight: 700;
    line-height: 16px;
  }
  .add-desk {
    display: none;
  }
  .filter-btn.on {
    color: var(--accent);
  }
  .count.dot {
    background: var(--accent);
    color: var(--on-accent);
  }
  .chips {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
    margin: 0 -16px;
    padding: 0 16px 2px;
  }
  .chips::-webkit-scrollbar {
    display: none;
  }
  .chips .chip {
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
  }
  .clear-all {
    color: var(--text-2);
  }
  .pop {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 8px;
    z-index: 30;
    background: var(--surface);
    border-radius: var(--radius);
    box-shadow: var(--shadow-lg);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: min(60vh, 480px);
    overflow: auto;
  }
  .opts {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .opts.scroll {
    max-height: 220px;
    overflow: auto;
  }
  .n {
    color: var(--text-3);
    font-weight: 500;
    font-size: 12px;
  }
  .chip.on .n {
    color: inherit;
    opacity: 0.7;
  }
  .switch {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }
  .switch input {
    width: 18px;
    height: 18px;
    accent-color: var(--accent);
  }
  .slider {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .slider.off {
    opacity: 0.5;
  }
  .slider input {
    flex: 1;
    accent-color: var(--accent);
  }
  .val {
    min-width: 56px;
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }
  .hint {
    margin: 0;
    font-size: 12.5px;
    color: var(--text-3);
  }
  .tag-search {
    min-height: 34px;
  }
  @media (min-width: 768px) {
    .row {
      box-shadow: none;
      border: 1px solid var(--line);
    }
    .add-desk {
      display: inline-grid;
    }
    .chips {
      flex-wrap: wrap;
      overflow: visible;
      margin: 0;
      padding: 0;
    }
    .chips .chip {
      box-shadow: none;
    }
  }
</style>
