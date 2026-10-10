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
