<script lang="ts">
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import RefreshCw from '@lucide/svelte/icons/refresh-cw';
  import { api, type ServiceHealth } from '$lib/api';
  import { kmToMi } from '$lib/format';
  import { app } from '$lib/state.svelte';
  import { theme, type ThemeChoice } from '$lib/theme.svelte';

  interface Props {
    onclose: () => void;
  }

  let { onclose }: Props = $props();
  let services = $state<ServiceHealth[] | null>(null);
  let checking = $state(false);
  let serviceError = $state('');

  const SERVICE_LABEL: Record<string, string> = {
    photon: 'Geocoder (Photon)',
    'osrm-car': 'Driving routes',
    'osrm-foot': 'Walking routes',
    searxng: 'Web search (SearXNG)',
    ollama: 'Local AI (Ollama)'
  };

  async function check() {
    checking = true;
    serviceError = '';
    try {
      services = await api.services();
    } catch (e) {
      serviceError = e instanceof Error ? e.message : String(e);
    } finally {
      checking = false;
    }
  }

  $effect(() => {
    check();
  });

  const s = $derived(app.settings);
  const choices: { v: ThemeChoice; label: string }[] = [
    { v: 'system', label: 'Match the phone' },
    { v: 'light', label: 'Light' },
    { v: 'dark', label: 'Dark' }
  ];
</script>

<div class="settings">
  <header>
    <button class="icon-btn" aria-label="Back to the list" onclick={onclose}><ChevronLeft size={22} /></button>
    <h2>Settings</h2>
  </header>
  <div class="body">
    {#if s}
      <section>
        <h3>Signed in</h3>
        <p>{s.user.display_name || s.user.username}</p>
        {#if s.users.length > 1}
          <p class="muted">Shared with {s.users.filter((u) => u.id !== s.user.id).map((u) => u.display_name || u.username).join(', ')}</p>
        {/if}
      </section>

      <section>
        <h3>Appearance</h3>
        <div class="opts">
          {#each choices as c (c.v)}
            <button class="chip" class:on={theme.choice === c.v} onclick={() => theme.set(c.v)}>{c.label}</button>
          {/each}
        </div>
      </section>

      <section>
        <h3>Home and distance</h3>
        <p>
          Home is {s.home.source === 'ha' ? 'the Home Assistant home zone' : 'set by hand'}
          ({s.home.lat.toFixed(4)}, {s.home.lon.toFixed(4)}).
        </p>
        <p class="muted">
          The distance filter starts at {s.units === 'mi' ? `${Math.round(kmToMi(s.radius_km))} miles` : `${s.radius_km} km`}. Interests, discovery sources
          and notifications arrive with the discovery phase.
        </p>
      </section>
    {/if}

    <section>
      <div class="row">
        <h3>Services</h3>
        <button class="icon-btn" aria-label="Check again" onclick={check} disabled={checking}><RefreshCw size={16} class={checking ? 'spin' : ''} /></button>
      </div>
      {#if serviceError}
        <p class="error">{serviceError}</p>
      {:else if services}
        <ul class="services">
          {#each services as sv (sv.name)}
            <li>
              <span class="health" class:ok={sv.ok}></span>
              <span class="name">{SERVICE_LABEL[sv.name] ?? sv.name}</span>
              <span class="muted">{sv.ok ? `${sv.ms} ms` : (sv.detail ?? 'down')}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="muted">Checking</p>
      {/if}
    </section>

    <section>
      <h3>About</h3>
      <p class="muted">
        Map data from OpenStreetMap through Protomaps, served from this server. Place lookups use a local geocoder and the
        local AI model; nothing is sent to paid services.
      </p>
    </section>
  </div>
</div>

<style>
  .settings {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  .body {
    flex: 1;
    overflow-y: auto;
    padding: 4px 16px 24px;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 13px;
    color: var(--text-2);
  }
  p {
    margin: 0 0 4px;
    font-size: 14.5px;
  }
  .opts {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .row h3 {
    margin: 0;
  }
  .services {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .services li {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
  }
  .name {
    flex: 1;
  }
  .health {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--danger);
  }
  .health.ok {
    background: var(--ok);
  }
  .error {
    color: var(--danger);
  }
</style>
