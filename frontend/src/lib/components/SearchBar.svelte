<script lang="ts">
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import Plus from '@lucide/svelte/icons/plus';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import Settings from '@lucide/svelte/icons/settings';
  import { categoryTokens } from '$lib/categories';
  import { activeCount, activeTokens, type Filters } from '$lib/filters';

  interface Props {
    filters: Filters;
    units: 'mi' | 'km';
    desktop: boolean;
    filtersOpen: boolean;
    onchange: (f: Filters) => void;
    onfilters: () => void;
    onadd: () => void;
    onsettings: () => void;
  }

  let { filters, units, desktop, filtersOpen, onchange, onfilters, onadd, onsettings }: Props = $props();

  let query = $state('');
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

  const tokens = $derived([
    ...activeTokens(filters, units).map((t) => ({ key: t.key, label: t.label, remove: () => onchange(t.remove(filters)) })),
    ...categoryTokens(filters.cats).map((t) => ({ key: t.key, label: t.label, remove: () => set({ cats: t.remove(filters.cats) }) }))
  ]);
  const count = $derived(activeCount(filters));
</script>

<div class="bar glass" role="search">
  <label class="search">
    <Search size={17} />
    <span class="sr-only">Search</span>
    <span class="tokens">
      {#each tokens as t (t.key)}
        <span class="tok">{t.label}<button aria-label="Remove {t.label}" onclick={(e) => (e.preventDefault(), t.remove())}><X size={12} strokeWidth={2.6} /></button></span>
      {/each}
    </span>
    <input
      id="search"
      type="search"
      placeholder={tokens.length ? 'Search' : 'Search places and events'}
      autocomplete="off"
      bind:value={query}
      oninput={typed}
      onkeydown={(e) => e.key === 'Enter' && (timer && clearTimeout(timer), set({ q: query }))}
    />
    {#if query}
      <button class="clear" aria-label="Clear search" onclick={(e) => (e.preventDefault(), (query = ''), set({ q: '' }))}><X size={14} /></button>
    {:else if desktop}
      <kbd aria-hidden="true">/</kbd>
    {/if}
  </label>
  {#if !desktop}
    <button class="fbtn" class:on={count > 0} aria-expanded={filtersOpen} onclick={onfilters}>
      <SlidersHorizontal size={15} />Filters{#if count}<span class="bd">{count}</span>{/if}
    </button>
  {/if}
  <button class="add" aria-label="Add a link" title="Add a link (n)" onclick={onadd}><Plus size={desktop ? 17 : 20} strokeWidth={2.2} />{#if desktop}<span>Add</span>{/if}</button>
  {#if desktop}
    <button class="icon-btn gear" aria-label="Settings" title="Settings" onclick={onsettings}><Settings size={17} /></button>
  {/if}
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 6px;
    height: 48px;
    padding: 0 6px 0 14px;
    border-radius: 16px;
  }
  .search {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-3);
  }
  .tokens {
    display: flex;
    gap: 5px;
    flex: none;
    max-width: 62%;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .tokens::-webkit-scrollbar {
    display: none;
  }
  .tok {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    height: 26px;
    padding: 0 4px 0 10px;
    border-radius: 13px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 12.5px;
    font-weight: 600;
    white-space: nowrap;
  }
  .tok button {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    padding: 0;
  }
  .tok button:hover {
    background: color-mix(in srgb, var(--accent) 20%, transparent);
  }
  input {
    flex: 1;
    min-width: 40px;
    height: 40px;
    border: none;
    background: transparent;
    outline: none;
    color: var(--text);
    font-size: 16px;
  }
  input::-webkit-search-cancel-button {
    display: none;
  }
  kbd {
    font: inherit;
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 5px;
    border: 1px solid var(--line);
    color: var(--text-3);
  }
  .clear {
    border: none;
    background: var(--surface-2);
    color: var(--text-2);
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    padding: 0;
  }
  .fbtn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 36px;
    padding: 0 12px;
    border: none;
    border-radius: 11px;
    background: var(--surface-2);
    color: var(--text);
    font-weight: 600;
    font-size: 14px;
    flex: none;
  }
  .fbtn.on {
    background: var(--accent);
    color: var(--on-accent);
  }
  .bd {
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    border-radius: 9px;
    display: inline-grid;
    place-items: center;
    font-size: 11px;
    background: var(--accent);
    color: var(--on-accent);
  }
  .fbtn.on .bd {
    background: var(--on-accent);
    color: var(--accent);
  }
  .add {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    height: 36px;
    min-width: 36px;
    padding: 0 10px;
    border: none;
    border-radius: 11px;
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 600;
    flex: none;
  }
  .add:hover {
    filter: brightness(1.08);
  }
  .gear {
    width: 36px;
    height: 36px;
    flex: none;
  }
  @media (min-width: 768px) and (pointer: fine) {
    .bar {
      height: 44px;
      border-radius: 14px;
    }
    input {
      height: 36px;
      font-size: 13px;
    }
    .add,
    .gear {
      height: 30px;
    }
    .gear {
      width: 30px;
    }
  }
</style>
