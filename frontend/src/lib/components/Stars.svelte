<script lang="ts">
  import Star from '@lucide/svelte/icons/star';

  interface Props {
    value: number | null;
    readonly?: boolean;
    size?: number;
    onchange?: (v: number | null) => void;
  }

  let { value, readonly = false, size = 22, onchange }: Props = $props();
  let hover = $state<number | null>(null);
  const shown = $derived(hover ?? value ?? 0);
</script>

<div class="stars" role={readonly ? 'img' : 'radiogroup'} aria-label={value ? `${value} out of 5` : 'Not rated'}>
  {#each [1, 2, 3, 4, 5] as n (n)}
    {#if readonly}
      <span class="star" class:on={n <= shown}><Star {size} /></span>
    {:else}
      <button
        class="star"
        class:on={n <= shown}
        role="radio"
        aria-checked={value === n}
        aria-label="{n} star{n > 1 ? 's' : ''}"
        onpointerenter={() => (hover = n)}
        onpointerleave={() => (hover = null)}
        onclick={() => onchange?.(value === n ? null : n)}
      >
        <Star {size} />
      </button>
    {/if}
  {/each}
</div>

<style>
  .stars {
    display: inline-flex;
    gap: 2px;
  }
  .star {
    display: inline-grid;
    place-items: center;
    padding: 2px;
    border: none;
    background: none;
    color: var(--text-3);
  }
  .star.on {
    color: #f59f00;
  }
  .star.on :global(svg) {
    fill: currentColor;
  }
</style>
