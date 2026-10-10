<script lang="ts">
  import X from '@lucide/svelte/icons/x';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Info from '@lucide/svelte/icons/info';
  import type { ItemType } from '$lib/api';
  import { app } from '$lib/state.svelte';

  interface Props {
    onshow: (t: ItemType, id: string) => void;
  }

  let { onshow }: Props = $props();

  function stageText(s: string): string {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Waiting';
  }
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as t (t.key)}
    <div class="toast {t.status}">
      <span class="ic">
        {#if t.status === 'working'}
          <LoaderCircle size={18} class="spin" />
        {:else if t.status === 'done'}
          <CircleCheck size={18} />
        {:else if t.status === 'failed'}
          <CircleAlert size={18} />
        {:else}
          <Info size={18} />
        {/if}
      </span>
      <div class="text">
        <div class="title">{t.title}</div>
        {#if t.status === 'working'}
          <div class="sub">{stageText(t.stage)}</div>
          <div class="bar"><span style="width: {t.pct}%"></span></div>
        {:else if t.detail}
          <div class="sub">{t.detail}</div>
        {/if}
      </div>
      {#if t.target}
        <button class="btn small" onclick={() => t.target && (onshow(t.target.t, t.target.id), app.dismiss(t.key))}>Show</button>
      {/if}
      <button class="x" aria-label="Dismiss" onclick={() => app.dismiss(t.key)}><X size={15} /></button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: absolute;
    z-index: 40;
    left: 12px;
    right: 12px;
    top: calc(var(--safe-top) + 112px);
    display: flex;
    flex-direction: column;
    gap: 8px;
    pointer-events: none;
    align-items: center;
  }
  .toast {
    pointer-events: auto;
    width: min(420px, 100%);
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 10px 10px 12px;
    border-radius: 14px;
    background: var(--surface);
    box-shadow: var(--shadow-lg);
    animation: drop 0.2s ease-out;
  }
  @keyframes drop {
    from {
      transform: translateY(-8px);
      opacity: 0;
    }
  }
  .ic {
    display: inline-grid;
    color: var(--accent);
  }
  .done .ic {
    color: var(--ok);
  }
  .failed .ic {
    color: var(--danger);
  }
  .text {
    flex: 1;
    min-width: 0;
  }
  .title {
    font-weight: 650;
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sub {
    font-size: 12.5px;
    color: var(--text-2);
  }
  .bar {
    height: 3px;
    border-radius: 2px;
    background: var(--surface-3);
    margin-top: 6px;
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
    background: var(--accent);
    transition: width 0.4s ease;
  }
  .x {
    border: none;
    background: none;
    color: var(--text-3);
    padding: 4px;
    display: grid;
  }
  @media (min-width: 768px) {
    .toasts {
      left: auto;
      right: 16px;
      top: 16px;
      width: 380px;
    }
  }
</style>
