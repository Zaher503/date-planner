<script lang="ts">
  import X from '@lucide/svelte/icons/x';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Info from '@lucide/svelte/icons/info';
  import ListTodo from '@lucide/svelte/icons/list-todo';
  import type { ItemType } from '$lib/api';
  import { app } from '$lib/state.svelte';

  interface Props {
    onshow: (t: ItemType, id: string) => void;
  }

  let { onshow }: Props = $props();

  let open = $state(false);

  function stageText(s: string): string {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Waiting';
  }

  const jobToasts = $derived(app.toasts.filter((t) => t.jobId !== null));
  const activeCount = $derived(jobToasts.filter((t) => t.status === 'working').length);
  // One toast at a time: the newest finished one, else the first still working
  const current = $derived(
    [...app.toasts].reverse().find((t) => t.status !== 'working') ?? app.toasts.find((t) => t.status === 'working') ?? null
  );
</script>

{#snippet row(t: (typeof app.toasts)[number], inList: boolean)}
  <div class="toast {t.status}" class:inlist={inList}>
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
      <button class="btn small" onclick={() => t.target && (onshow(t.target.t, t.target.id), app.dismiss(t.key), (open = false))}>Show</button>
    {/if}
    <button class="x" aria-label="Dismiss" onclick={() => app.dismiss(t.key)}><X size={15} /></button>
  </div>
{/snippet}

{#if jobToasts.length}
  <button class="queue-btn" aria-label="Show the queue" title="Queue" onclick={() => (open = !open)}>
    <ListTodo size={16} />
    {#if activeCount}<span class="badge">{activeCount}</span>{/if}
  </button>
{/if}

{#if open && jobToasts.length}
  <div class="queue" role="dialog" aria-label="Queue">
    <div class="qhead">
      <strong>Queue</strong>
      <span class="muted">{activeCount} working, {jobToasts.length - activeCount} finished</span>
      <button class="x" aria-label="Close the queue" onclick={() => (open = false)}><X size={15} /></button>
    </div>
    <div class="qlist">
      {#each jobToasts as t (t.key)}{@render row(t, true)}{/each}
    </div>
  </div>
{/if}

<div class="toasts" aria-live="polite">
  {#if current && !open}
    {#key current.key}{@render row(current, false)}{/key}
    {#if activeCount > (current.status === 'working' ? 1 : 0)}
      <button class="more" onclick={() => (open = true)}>{activeCount - (current.status === 'working' ? 1 : 0)} more in the queue</button>
    {/if}
  {/if}
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
  .queue-btn {
    position: absolute;
    z-index: 41;
    top: calc(var(--safe-top) + 3px);
    right: 38px;
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border: none;
    border-radius: 8px;
    background: var(--surface-2);
    color: var(--text-2);
  }
  .badge {
    position: absolute;
    top: -5px;
    right: -5px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 8px;
    background: var(--accent);
    color: var(--on-accent);
    font-size: 10.5px;
    font-weight: 700;
    display: grid;
    place-items: center;
  }
  .more {
    pointer-events: auto;
    border: none;
    border-radius: 10px;
    padding: 4px 10px;
    background: var(--surface);
    color: var(--text-2);
    font-size: 12px;
    box-shadow: var(--shadow);
  }
  .queue {
    position: absolute;
    z-index: 42;
    top: calc(var(--safe-top) + 36px);
    right: 12px;
    width: min(400px, calc(100% - 24px));
    max-height: min(60vh, 520px);
    display: flex;
    flex-direction: column;
    border-radius: 14px;
    background: var(--surface);
    box-shadow: var(--shadow-lg);
    overflow: hidden;
  }
  .qhead {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 10px 8px 8px 14px;
    font-size: 13.5px;
  }
  .qhead .x {
    margin-left: auto;
    align-self: center;
  }
  .qlist {
    overflow-y: auto;
    padding: 0 8px 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .toast.inlist {
    box-shadow: none;
    background: var(--surface-2);
    animation: none;
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
