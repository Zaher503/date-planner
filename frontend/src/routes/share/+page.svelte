<script lang="ts">
  // Android share target: /share?title=&text=&url= -> the map with the Add box filled in
  import { goto } from '$app/navigation';
  import { page } from '$app/state';

  $effect(() => {
    const sp = page.url.searchParams;
    const vals = [sp.get('url'), sp.get('text'), sp.get('title')].map((v) => (v ?? '').trim());
    const shared = vals.find((v) => /https?:\/\//.test(v)) ?? vals.find(Boolean) ?? '';
    goto(`/?add=${encodeURIComponent(shared)}`, { replaceState: true });
  });
</script>
