<script lang="ts">
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Repeat from '@lucide/svelte/icons/repeat';
  import type { ItemType, ListItem as Row } from '$lib/api';
  import { colorOf, labelOf } from '$lib/categories';
  import { distance, when } from '$lib/format';

  interface Props {
    items: Row[];
    units: 'mi' | 'km';
    tz: string;
    selected: string | null;
    onselect: (t: ItemType, id: string) => void;
    onhover?: (id: string | null) => void;
  }

  let { items, units, tz, selected, onselect, onhover }: Props = $props();

  const ROW = 68;
  const OVERSCAN = 6;
  let scroller: HTMLDivElement;
  let scrollTop = $state(0);
  let height = $state(600);

  const start = $derived(Math.max(0, Math.floor(scrollTop / ROW) - OVERSCAN));
  const end = $derived(Math.min(items.length, Math.ceil((scrollTop + height) / ROW) + OVERSCAN));
  const visible = $derived(items.slice(start, end));
  const now = new Date();

  function subline(p: Row): string {
    const bits: string[] = [];
    if (p.t === 'event') {
      if (p.start) bits.push(when(p.start, { allDay: p.all_day, tz, now }));
      else if (p.rec) bits.push(p.rec.replace(/^\w/, (c) => c.toUpperCase()));
      if (p.venue && p.venue !== p.title) bits.push(p.venue);
    } else {
      bits.push(labelOf(p.cat));
    }
    if (p.price) bits.push(p.price);
    return bits.join(' · ');
  }

  // Keep the selected row in view when it is picked on the map
  $effect(() => {
    if (!selected || !scroller) return;
    const i = items.findIndex((x) => x.id === selected);
    if (i < 0) return;
    const top = i * ROW;
    if (top < scroller.scrollTop || top + ROW > scroller.scrollTop + scroller.clientHeight) {
      scroller.scrollTo({ top: Math.max(0, top - ROW), behavior: 'smooth' });
    }
  });
</script>

<div class="scroller" bind:this={scroller} bind:clientHeight={height} onscroll={() => (scrollTop = scroller.scrollTop)}>
  <div class="inner" style="height: {items.length * ROW}px">
    {#each visible as p, i (p.id)}
      <button
        class="row"
        class:sel={p.id === selected}
        class:faded={p.rs === 'suggested'}
        style="top: {(start + i) * ROW}px"
        onclick={() => onselect(p.t, p.id)}
        onpointerenter={() => onhover?.(p.id)}
        onpointerleave={() => onhover?.(null)}
      >
        {#if p.thumb && p.thumb_src}
          <img class="thumb" src="/api/thumb/{p.thumb_src}" alt="" loading="lazy" decoding="async" />
        {:else}
          <span class="thumb dot" class:event={p.t === 'event'} style="--c: {colorOf(p.cat)}"></span>
        {/if}
        <span class="text">
          <span class="title">{p.title}</span>
          <span class="sub">
            {#if p.rec && !p.start}<Repeat size={12} />{/if}
            {subline(p)}
          </span>
        </span>
        <span class="meta">
          {#if p.rs === 'needs_review'}
            <span class="flag" title="Needs a check"><TriangleAlert size={15} /></span>
          {/if}
          {#if p.my === 'want'}
            <span class="st" title="Want to go"><Bookmark size={15} /></span>
          {:else if p.my === 'going'}
            <span class="st" title="Going"><CalendarCheck size={15} /></span>
          {:else if p.my === 'been'}
            <span class="st been" title="Been"><CircleCheck size={15} /></span>
          {/if}
          {#if p.dist_m != null}
            <span class="dist">{distance(p.dist_m, units)}</span>
          {/if}
        </span>
      </button>
    {/each}
  </div>
</div>

<style>
  .scroller {
    height: 100%;
    overflow-y: auto;
    overscroll-behavior: contain;
    -webkit-overflow-scrolling: touch;
  }
  .inner {
    position: relative;
  }
  .row {
    position: absolute;
    left: 0;
    right: 0;
    height: 68px;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 0 16px;
    border: none;
    background: transparent;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }
  .row:hover {
    background: var(--surface-2);
  }
  .row.sel {
    background: var(--accent-soft);
  }
  .row.faded .text {
    opacity: 0.7;
  }
  .thumb {
    width: 46px;
    height: 46px;
    border-radius: 10px;
    object-fit: cover;
    flex: none;
    background: var(--surface-2);
  }
  .thumb.dot {
    display: grid;
    place-items: center;
    background: color-mix(in srgb, var(--c) 16%, transparent);
    position: relative;
  }
  .thumb.dot::after {
    content: '';
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--c);
    border: 2px solid var(--surface);
  }
  .thumb.dot.event::after {
    border-radius: 4px;
  }
  .text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .title {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: var(--text-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: none;
  }
  .meta > span:not(.dist) {
    display: inline-flex;
  }
  .flag {
    color: var(--warn);
  }
  .st {
    color: var(--accent);
  }
  .st.been {
    color: var(--ok);
  }
  .dist {
    font-size: 12px;
    color: var(--text-3);
    font-variant-numeric: tabular-nums;
    min-width: 42px;
    text-align: right;
  }
</style>
