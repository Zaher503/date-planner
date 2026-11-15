<script lang="ts">
  import X from '@lucide/svelte/icons/x';
  import { CATEGORY_FILTERS, categoryFilterOn, toggleCategoryFilter } from '$lib/categories';
  import { EMPTY, STATUS_LABEL, WHEN_LABEL, activeCount, toggle, type Filters, type When } from '$lib/filters';
  import { kmToMi, miToKm } from '$lib/format';

  interface Props {
    filters: Filters;
    units: 'mi' | 'km';
    radiusKm: number;
    reviewCount: number;
    /** Text for the button that closes the panel on a phone, e.g. "Show 12 results". */
    resultLabel: string;
    onchange: (f: Filters) => void;
    onnear: (near: 'home' | 'me') => void;
    onclose: () => void;
  }

  let { filters, units, radiusKm, reviewCount, resultLabel, onchange, onnear, onclose }: Props = $props();

  const STATUSES = ['want', 'going', 'been', 'review'];
  const WHENS: When[] = ['today', 'weekend', 'week'];
  const active = $derived(activeCount(filters));

  function set(patch: Partial<Filters>) {
    onchange({ ...filters, ...patch });
  }

  const distMin = $derived(units === 'mi' ? 3 : 5);
  const distMax = $derived(units === 'mi' ? 95 : 150);
  const distValue = $derived(
    filters.dist_km ? (units === 'mi' ? Math.round(kmToMi(filters.dist_km)) : Math.round(filters.dist_km)) : units === 'mi' ? Math.round(kmToMi(radiusKm)) : Math.round(radiusKm)
  );

  function slide(e: Event) {
    const v = Number((e.target as HTMLInputElement).value);
    set({ dist_km: units === 'mi' ? miToKm(v) : v });
  }
</script>

<div class="panel">
  <div class="head">
    <h2>Filters</h2>
    {#if active}<button class="link" onclick={() => onchange({ ...EMPTY, near: filters.near })}>Clear all</button>{/if}
    <button class="icon-btn close" aria-label="Close filters" onclick={onclose}><X size={18} /></button>
  </div>

  <div class="body">
    <h3>Saved status</h3>
    <div class="chips">
      {#each STATUSES as s (s)}
        <button class="fchip" aria-pressed={filters.status.includes(s)} onclick={() => set({ status: toggle(filters.status, s) })}>
          {STATUS_LABEL[s]}{#if s === 'review' && reviewCount}<span class="n">{reviewCount}</span>{/if}
        </button>
      {/each}
    </div>

    <h3>When</h3>
    <div class="chips">
      {#each WHENS as w (w)}
        <button class="fchip" aria-pressed={filters.when === w} onclick={() => set({ when: filters.when === w ? '' : w })}>{WHEN_LABEL[w]}</button>
      {/each}
    </div>

    <h3>Categories</h3>
    <div class="chips">
      {#each CATEGORY_FILTERS as g (g.key)}
        <button class="fchip" aria-pressed={categoryFilterOn(g.cats, filters)} onclick={() => set({ cats: toggleCategoryFilter(g.cats, filters.cats) })}>{g.label}</button>
      {/each}
    </div>

    <h3>Distance</h3>
    <label class="switch">
      <span>Limit distance</span>
      <input type="checkbox" role="switch" checked={!!filters.dist_km} onchange={(e) => set({ dist_km: e.currentTarget.checked ? radiusKm : null })} />
      <i aria-hidden="true"></i>
    </label>
    <div class="slider" class:off={!filters.dist_km}>
      <input type="range" min={distMin} max={distMax} step="1" value={distValue} disabled={!filters.dist_km} oninput={slide} aria-label="Maximum distance" />
      <b>{distValue} {units}</b>
    </div>
    <div class="chips">
      <button class="fchip" aria-pressed={filters.near === 'home'} onclick={() => onnear('home')}>From home</button>
      <button class="fchip" aria-pressed={filters.near === 'me'} onclick={() => onnear('me')}>From my location</button>
    </div>

    <h3>Archive</h3>
    <label class="switch">
      <span>Past events only</span>
      <input type="checkbox" role="switch" checked={filters.archive} onchange={(e) => set({ archive: e.currentTarget.checked })} />
      <i aria-hidden="true"></i>
    </label>
  </div>

  <button class="btn primary done" onclick={onclose}>{resultLabel}</button>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 10px 6px 16px;
    flex: none;
  }
  h2 {
    flex: 1;
    margin: 0;
    font-size: 17px;
    letter-spacing: -0.01em;
  }
  .link {
    border: none;
    background: none;
    color: var(--accent);
    font-weight: 600;
    min-height: 32px;
    padding: 0 8px;
    border-radius: 8px;
  }
  .link:hover {
    background: var(--surface-2);
  }
  .body {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 0 16px 20px;
  }
  h3 {
    margin: 18px 0 8px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-3);
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .fchip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 14px;
    border-radius: 18px;
    border: none;
    background: var(--surface-2);
    color: var(--text);
    font-weight: 550;
  }
  .fchip:hover {
    background: var(--surface-3);
  }
  .fchip[aria-pressed='true'] {
    background: var(--accent-soft);
    color: var(--accent);
    box-shadow: inset 0 0 0 1.5px var(--accent);
  }
  .n {
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    background: var(--warn);
    color: var(--surface);
    font-size: 11px;
    display: inline-grid;
    place-items: center;
  }
  .switch {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 44px;
    font-weight: 550;
  }
  .switch input {
    position: absolute;
    inset: 0;
    opacity: 0;
    margin: 0;
    cursor: pointer;
  }
  .switch i {
    width: 46px;
    height: 28px;
    border-radius: 14px;
    background: var(--surface-3);
    position: relative;
    transition: background 0.2s;
    flex: none;
  }
  .switch i::after {
    content: '';
    position: absolute;
    left: 3px;
    top: 3px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.3);
    transition: left 0.2s;
  }
  .switch input:checked + i {
    background: var(--accent);
  }
  .switch input:checked + i::after {
    left: 21px;
  }
  .switch input:focus-visible + i {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .slider {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 40px;
    margin-bottom: 4px;
  }
  .slider.off {
    opacity: 0.45;
  }
  .slider input {
    flex: 1;
    accent-color: var(--accent);
  }
  .slider b {
    min-width: 56px;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .done {
    display: none;
    margin: 0 16px calc(16px + var(--safe-bottom));
    min-height: 46px;
    border-radius: 13px;
    font-weight: 650;
    flex: none;
  }
  @media (max-width: 767px) {
    .done {
      display: inline-flex;
    }
  }
  @media (min-width: 768px) and (pointer: fine) {
    .fchip {
      min-height: 28px;
      padding: 0 12px;
      border-radius: 14px;
    }
    .switch {
      min-height: 36px;
    }
  }
</style>
