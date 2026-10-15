<script lang="ts">
  import '../app.css';
  import type { Snippet } from 'svelte';
  import { theme } from '$lib/theme.svelte';

  let { children }: { children: Snippet } = $props();

  $effect(() => {
    document.documentElement.dataset.theme = theme.resolved;
  });
</script>

{@render children()}
<div class="version" aria-hidden="true">{__APP_VERSION__}</div>

<style>
  .version {
    position: fixed;
    left: 8px;
    bottom: calc(4px + var(--safe-bottom));
    z-index: 1;
    font: 10.5px/1 var(--font-mono, ui-monospace, monospace);
    color: var(--text-3);
    opacity: 0.55;
    pointer-events: none;
    user-select: none;
  }
</style>
