<script lang="ts" module>
  // Phone: a bottom sheet with three heights. Desktop: a plain side panel (CSS only).
  export type Snap = 'peek' | 'half' | 'full';
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    snap: Snap;
    desktop: boolean;
    header?: Snippet;
    children: Snippet;
    onsnap: (s: Snap) => void;
    onheight?: (px: number) => void;
  }

  let { snap, desktop, header, children, onsnap, onheight }: Props = $props();

  const PEEK = 112;
  let vh = $state(typeof window !== 'undefined' ? window.innerHeight : 800);
  let drag = $state<number | null>(null);
  let startY = 0;
  let startH = 0;
  let moved = false;

  const heights = $derived({ peek: PEEK, half: Math.round(vh * 0.5), full: Math.round(vh - 130) });
  const height = $derived(drag ?? heights[snap]);

  $effect(() => {
    onheight?.(desktop ? 0 : heights[snap]);
  });

  function down(e: PointerEvent) {
    if (desktop) return;
    startY = e.clientY;
    startH = heights[snap];
    moved = false;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag = startH;
  }

  function move(e: PointerEvent) {
    if (drag === null) return;
    const dy = startY - e.clientY;
    if (Math.abs(dy) > 4) moved = true;
    drag = Math.max(PEEK - 30, Math.min(heights.full + 20, startH + dy));
  }

  function up() {
    if (drag === null) return;
    const h = drag;
    drag = null;
    if (!moved) {
      // A tap on the handle steps up, or back to peek from the top
      onsnap(snap === 'peek' ? 'half' : snap === 'half' ? 'full' : 'peek');
      return;
    }
    const order: Snap[] = ['peek', 'half', 'full'];
    const nearest = order.reduce((a, b) => (Math.abs(heights[b] - h) < Math.abs(heights[a] - h) ? b : a));
    onsnap(nearest);
  }
</script>

<svelte:window bind:innerHeight={vh} />

<section class="sheet" class:dragging={drag !== null} style:height={desktop ? null : `${height}px`}>
  <div class="grab" role="slider" tabindex="0" aria-label="Resize the list" aria-valuenow={snap === 'peek' ? 0 : snap === 'half' ? 1 : 2} aria-valuemin={0} aria-valuemax={2}
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
    onkeydown={(e) => {
      if (e.key === 'ArrowUp') onsnap(snap === 'peek' ? 'half' : 'full');
      if (e.key === 'ArrowDown') onsnap(snap === 'full' ? 'half' : 'peek');
    }}
  >
    <span class="handle"></span>
    {#if header}{@render header()}{/if}
  </div>
  <div class="content">
    {@render children()}
  </div>
</section>

<style>
  .sheet {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-radius: 18px 18px 0 0;
    box-shadow: 0 -4px 24px rgb(0 0 0 / 0.16);
    transition: height 0.24s cubic-bezier(0.2, 0.8, 0.2, 1);
    padding-bottom: var(--safe-bottom);
    max-height: calc(100% - 20px);
  }
  .sheet.dragging {
    transition: none;
  }
  .grab {
    flex: none;
    touch-action: none;
    cursor: grab;
    padding: 8px 0 2px;
    user-select: none;
  }
  .handle {
    display: block;
    width: 38px;
    height: 5px;
    border-radius: 3px;
    background: var(--surface-3);
    margin: 0 auto 6px;
  }
  .content {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  @media (min-width: 768px) {
    .sheet {
      position: relative;
      height: auto;
      max-height: none;
      border-radius: 0;
      box-shadow: none;
      transition: none;
      flex: 1;
      min-height: 0;
      padding-bottom: 0;
    }
    .grab {
      cursor: default;
      padding-top: 0;
    }
    .handle {
      display: none;
    }
  }
</style>
