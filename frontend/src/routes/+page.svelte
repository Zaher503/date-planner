<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import Plus from '@lucide/svelte/icons/plus';
  import X from '@lucide/svelte/icons/x';
  import Settings from '@lucide/svelte/icons/settings';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import { api, type Item, type ItemType, type ListItem, type MapData } from '$lib/api';
  import { activeCount, apiQuery, EMPTY, filterParams, parseFilters, type Filters } from '$lib/filters';
  import { DEFAULT_TZ } from '$lib/format';
  import MapView from '$lib/map/MapView.svelte';
  import { app } from '$lib/state.svelte';
  import { theme } from '$lib/theme.svelte';
  import AddDialog from '$lib/components/AddDialog.svelte';
  import FilterPanel from '$lib/components/FilterPanel.svelte';
  import ItemDetail from '$lib/components/ItemDetail.svelte';
  import ItemList from '$lib/components/ItemList.svelte';
  import SearchBar from '$lib/components/SearchBar.svelte';
  import SettingsPanel from '$lib/components/SettingsPanel.svelte';
  import Sheet, { type Snap } from '$lib/components/Sheet.svelte';
  import Toasts from '$lib/components/Toasts.svelte';

  const FILTER_KEYS = ['q', 'types', 'when', 'from', 'to', 'open_now', 'past', 'archive', 'price', 'tags', 'cats', 'status', 'dist_km', 'near'];

  // URL state
  const filters = $derived(parseFilters(page.url.searchParams));
  const sel = $derived.by(() => {
    const m = (page.url.searchParams.get('sel') ?? '').match(/^(place|event):([0-9a-f-]{36})$/);
    return m ? { t: m[1] as ItemType, id: m[2] } : null;
  });
  const panel = $derived(page.url.searchParams.get('panel'));
  const listMode = $derived(!!filters.q || filters.status.length > 0 || filters.archive);

  let mapView: MapView | undefined = $state();
  let mapData = $state<MapData | null>(null);
  let mapLoading = $state(false);
  let mapError = $state('');
  let view = $state<{ bbox: [number, number, number, number]; center: { lat: number; lon: number; zoom: number } } | null>(null);
  let me = $state<{ lat: number; lon: number } | null>(null);
  let snap = $state<Snap>('peek');
  let sheetPx = $state(112);
  let adding = $state<string | null>(null);
  let picking = $state(false);
  let reviewCount = $state(0);
  let filtersOpen = $state(false);
  let drawerEl: HTMLElement | undefined = $state();

  // Width of the floating details panel on desktop
  const DETAIL_W = 340;

  // Desktop side pane width, draggable and remembered
  const PANE_MIN = 300;
  const PANE_MAX = 720;
  const PANE_DEFAULT = 400;
  let paneW = $state(PANE_DEFAULT);
  let resizing = $state(false);

  function setPane(w: number) {
    paneW = Math.round(Math.max(PANE_MIN, Math.min(PANE_MAX, w, window.innerWidth - 240)));
  }

  function savePane() {
    try {
      localStorage.setItem('dates.paneW', String(paneW));
    } catch {
      /* storage can be blocked */
    }
  }

  function paneDown(e: PointerEvent) {
    resizing = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function paneMove(e: PointerEvent) {
    if (resizing) setPane(e.clientX);
  }

  function paneUp() {
    if (!resizing) return;
    resizing = false;
    savePane();
  }

  function paneKey(e: KeyboardEvent) {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      setPane(paneW + (e.key === 'ArrowRight' ? 20 : -20));
      savePane();
    }
  }

  // The map has to learn about its new size
  $effect(() => {
    void paneW;
    const id = requestAnimationFrame(() => mapView?.resize());
    return () => cancelAnimationFrame(id);
  });

  let globalList = $state<ListItem[] | null>(null);
  let globalTotal = $state(0);

  let item = $state<Item | null>(null);
  let itemLoading = $state(false);
  let itemError = $state('');

  const settings = $derived(app.settings);
  const tz = $derived(settings?.tz ?? DEFAULT_TZ);
  const units = $derived(settings?.units ?? 'mi');

  onMount(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    app.desktop = mq.matches;
    const on = (e: MediaQueryListEvent) => (app.desktop = e.matches);
    mq.addEventListener('change', on);
    try {
      const saved = Number(localStorage.getItem('dates.paneW'));
      if (saved) setPane(saved);
    } catch {
      /* storage can be blocked */
    }
    app.init();
    const add = page.url.searchParams.get('add');
    if (add !== null) {
      adding = add;
      nav((sp) => sp.delete('add'));
    }
    return () => mq.removeEventListener('change', on);
  });

  function nav(mut: (sp: URLSearchParams) => void, push = false) {
    const url = new URL(page.url);
    mut(url.searchParams);
    if (url.search === page.url.search) return;
    goto(url.pathname + url.search, { replaceState: !push, keepFocus: true, noScroll: true });
  }

  // A filter change shows its results, so an open detail closes
  function setFilters(f: Filters) {
    restore = null;
    nav((sp) => {
      for (const k of FILTER_KEYS) sp.delete(k);
      for (const [k, v] of filterParams(f)) sp.set(k, v);
      sp.delete('sel');
    });
  }

  let openEdit = $state(false);

  function select(t: ItemType, id: string, edit = false) {
    openEdit = edit;
    if (!sel && rows.length) frozen = rows;
    restore = null;
    const push = !sel;
    nav((sp) => {
      sp.set('sel', `${t}:${id}`);
      sp.delete('panel');
    }, push);
    if (!app.desktop && snap === 'peek') snap = 'half';
  }

  function closeDetail(gone = false) {
    picking = false;
    if (sel && frozen.length) {
      const id = sel.id;
      restore = { rows: gone ? frozen.filter((r) => r.id !== id) : frozen, top: id };
    }
    nav((sp) => sp.delete('sel'));
  }

  function openSettings() {
    // The button toggles: a second click closes the panel
    if (panel === 'settings') {
      nav((sp) => sp.delete('panel'), true);
      return;
    }
    nav((sp) => {
      sp.set('panel', 'settings');
      sp.delete('sel');
    }, true);
    if (!app.desktop) snap = 'full';
  }

  // Map padding so flyTo centres the pin in the uncovered part of the map
  const padding = $derived(app.desktop ? { top: 70, bottom: 40, left: 40, right: sel ? DETAIL_W + 40 : 40 } : { top: 90, bottom: Math.min(sheetPx, 420) + 10, left: 20, right: 20 });

  // Map data for every place that matches (the list keeps them all while the map zooms); refetched when the filters change
  const WORLD = [-180, -85, 180, 85];
  let fetched: { key: string; version: number } | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;

  $effect(() => {
    if (!settings) return;
    if (filters.near === 'me' && !me) return;
    const key = apiQuery(filters, { me });
    const version = app.version;
    if (fetched && fetched.key === key && fetched.version === version) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(async () => {
      controller?.abort();
      controller = new AbortController();
      mapLoading = true;
      try {
        mapData = await api.map(apiQuery(filters, { me, bbox: WORLD }), controller.signal);
        fetched = { key, version };
        mapError = '';
      } catch (e) {
        if ((e as Error).name !== 'AbortError') mapError = e instanceof Error ? e.message : String(e);
      } finally {
        mapLoading = false;
      }
    }, 150);
  });

  // Search and status filters list everything that matches, not only the viewport
  let lastListKey = '';
  $effect(() => {
    if (!settings) return;
    if (!listMode) {
      globalList = null;
      lastListKey = '';
      return;
    }
    if (filters.near === 'me' && !me) return;
    const key = apiQuery(filters, { me });
    const version = app.version;
    const fresh = key !== lastListKey;
    lastListKey = key;
    api
      .list(`${key}&limit=200&sort=${filters.archive ? 'date' : 'name'}`)
      .then((r) => {
        if (apiQuery(filters, { me }) !== key || app.version !== version) return;
        globalList = r.items;
        globalTotal = r.total;
        // A new search moves the map to its results
        if (fresh && r.items.length && !sel) mapView?.fitPoints(r.items.slice(0, 50));
      })
      .catch(() => {});
  });

  // Count of pins needing a check, for the warning button
  $effect(() => {
    if (!settings) return;
    void app.version;
    api
      .list('status=review&limit=1')
      .then((r) => (reviewCount = r.total))
      .catch(() => {});
  });

  // Ask the browser for the device location (shows its permission prompt)
  function locate(ok: (pos: { lat: number; lon: number }) => void, fail: () => void) {
    if (!window.isSecureContext || !navigator.geolocation) {
      app.info('Location needs a secure connection', 'Open the app over https to use your location. Measuring from home instead.');
      fail();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => ok({ lat: p.coords.latitude, lon: p.coords.longitude }),
      (e) => {
        const denied = e.code === e.PERMISSION_DENIED;
        app.info(
          denied ? 'Location is blocked' : 'Location not available',
          denied ? 'Allow location for this site in the browser, then try again. Measuring from home instead.' : 'Measuring from home instead.'
        );
        fail();
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  }

  // Picking "My location" asks for permission right away, from the tap itself
  function chooseNear(near: 'home' | 'me') {
    if (near === 'home' || me) {
      setFilters({ ...filters, near });
      return;
    }
    locate(
      (pos) => {
        me = pos;
        setFilters({ ...filters, near: 'me' });
      },
      () => setFilters({ ...filters, near: 'home' })
    );
  }

  // A link that opens with near=me asks as soon as the page loads
  $effect(() => {
    if (filters.near !== 'me' || me) return;
    locate(
      (pos) => (me = pos),
      () => setFilters({ ...filters, near: 'home' })
    );
  });

  // Rows for the list: every matching feature, alphabetical
  const byName = (a: ListItem, b: ListItem) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base', numeric: true }) || a.t.localeCompare(b.t);
  const liveRows = $derived.by((): ListItem[] => {
    if (listMode && globalList) return globalList;
    if (!mapData) return [];
    const out: ListItem[] = [];
    for (const f of mapData.features) {
      const [lon, lat] = f.geometry.coordinates;
      out.push({ ...f.properties, lat, lon });
    }
    return group(out.sort(byName));
  });

  // A place with several events is one row named after the place: "N events here", the soonest date up front
  function group(list: ListItem[]): ListItem[] {
    const events = new Map<string, ListItem[]>();
    for (const r of list) if (r.t === 'event' && r.place_id) events.set(r.place_id, [...(events.get(r.place_id) ?? []), r]);
    const many = new Map([...events].filter(([, evs]) => evs.length > 1));
    if (!many.size) return list;
    const soonest = (evs: ListItem[]) => {
      const floor = Date.now() - 3 * 3600e3;
      const next = evs.filter((e) => e.start && Date.parse(e.start) >= floor).sort((a, b) => Date.parse(a.start!) - Date.parse(b.start!))[0];
      return { count: evs.length, next: next?.start ?? null, allDay: next?.all_day ?? false };
    };
    const out: ListItem[] = [];
    const placed = new Set<string>();
    for (const r of list) {
      if (r.t === 'event' && r.place_id && many.has(r.place_id)) continue;
      if (r.t === 'place' && many.has(r.id)) {
        out.push({ ...r, group: soonest(many.get(r.id)!) });
        placed.add(r.id);
      } else out.push(r);
    }
    // The venue itself is outside this list (another filter or view): show it from its events
    for (const [pid, evs] of many) {
      if (placed.has(pid)) continue;
      const first = evs.find((e) => e.hero || e.thumb_src) ?? evs[0];
      out.push({ ...first, t: 'place', id: pid, title: first.venue ?? first.title, start: null, end: null, rec: null, dates: 0, price: null, group: soonest(evs) });
    }
    return out.sort(byName);
  }

  // Opening an item zooms the map onto it. Coming back shows the list as it was, the item scrolled to the
  // top, until the map is moved by hand.
  let frozen: ListItem[] = [];
  let restore = $state<{ rows: ListItem[]; top: string } | null>(null);
  // The kept rows stay in place but take the latest pictures, so a hero changed in the details shows in the list
  function withFreshPictures(kept: ListItem[]): ListItem[] {
    const now = new Map(liveRows.map((r) => [`${r.t}:${r.id}`, r]));
    return kept.map((r) => {
      const live = now.get(`${r.t}:${r.id}`);
      return live ? { ...r, thumb: live.thumb, thumb_src: live.thumb_src, hero: live.hero } : r;
    });
  }
  const rows = $derived(restore ? withFreshPictures(restore.rows) : liveRows);
  // With the details floating over the map the list stays put while the map moves
  const shownRows = $derived(app.desktop && sel && frozen.length ? withFreshPictures(frozen) : rows);

  // The number on top counts what the map shows right now; the list below keeps everything
  const counts = $derived.by(() => {
    let places = 0;
    let events = 0;
    if (mapData && view) {
      const [w, s, e, n] = view.bbox;
      for (const f of mapData.features) {
        const [lon, lat] = f.geometry.coordinates;
        if (lon < w || lon > e || lat < s || lat > n) continue;
        if (f.properties.t === 'place') places++;
        else events++;
      }
    }
    return { places, events };
  });

  // Item detail
  let loadedKey = '';
  $effect(() => {
    const s = sel;
    const key = s ? `${s.t}:${s.id}` : '';
    if (key === loadedKey) return;
    loadedKey = key;
    item = null;
    itemError = '';
    if (!s) return;
    itemLoading = true;
    api
      .item(s.t, s.id)
      .then((it) => {
        if (loadedKey !== key) return;
        item = it;
        // Bring it into view if it is off screen or hidden inside a cluster
        if (view) {
          const [w, so, e, n] = view.bbox;
          const off = it.lon < w || it.lon > e || it.lat < so || it.lat > n;
          if (off || view.center.zoom < 13.5) mapView?.flyTo(it.lon, it.lat, 14);
        }
      })
      .catch((e) => {
        if (loadedKey === key) itemError = e?.status === 404 ? 'This item no longer exists.' : String(e.message ?? e);
      })
      .finally(() => {
        if (loadedKey === key) itemLoading = false;
      });
  });

  // Refresh the open item when something changed elsewhere (a reread finished)
  let seenVersion = 0;
  $effect(() => {
    const v = app.version;
    if (v === seenVersion) return;
    seenVersion = v;
    const s = sel;
    if (!s || !item) return;
    api
      .item(s.t, s.id)
      .then((it) => {
        if (sel?.id === it.id) item = it;
      })
      .catch(() => {});
  });

  const candidates = $derived(item && item.candidates.length && (item.review_status === 'needs_review' || item.type === 'event') ? item.candidates : []);

  async function onCandidate(id: number) {
    if (!item) return;
    const placeId = item.type === 'place' ? item.id : item.place?.id;
    if (!placeId) return;
    try {
      await api.resolve(placeId, id);
      item = await api.item(item.type, item.id);
      app.changed();
    } catch (e) {
      app.info('Could not move the pin', e instanceof Error ? e.message : String(e));
    }
  }

  async function onPick(pos: { lat: number; lon: number }) {
    if (!item) return;
    picking = false;
    // Moving an event moves its place, so both stay together
    const target = item.type === 'event' && item.place ? { t: 'place' as const, id: item.place.id } : { t: item.type, id: item.id };
    try {
      await api.patch(target.t, target.id, { lat: pos.lat, lon: pos.lon });
      if (item.review_status === 'needs_review' || (item.type === 'event' && candidates.length)) {
        await api.patch(target.t, target.id, { review_status: 'ok' }).catch(() => {});
      }
      item = await api.item(item.type, item.id);
      app.changed();
      app.info('Pin moved');
    } catch (e) {
      app.info('Could not move the pin', e instanceof Error ? e.message : String(e));
    }
  }

  function flyToItem() {
    if (item) mapView?.flyTo(item.lon, item.lat, 15);
  }

  const resultLabel = $derived.by(() => {
    const n = listMode && globalList ? globalTotal : rows.length;
    return n === 0 ? 'Show results' : `Show ${n} result${n === 1 ? '' : 's'}`;
  });

  // Move focus into the panel when it opens
  $effect(() => {
    if (filtersOpen) queueMicrotask(() => drawerEl?.querySelector<HTMLElement>('.close')?.focus());
  });

  const circle = $derived.by(() => {
    if (!filters.dist_km || !settings) return null;
    const c = filters.near === 'me' && me ? me : settings.home;
    return { lat: c.lat, lon: c.lon, km: filters.dist_km };
  });

  function onKey(e: KeyboardEvent) {
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || adding !== null) return;
    if (e.key === 'Escape') {
      if (filtersOpen) filtersOpen = false;
      else if (picking) picking = false;
      else if (sel) closeDetail();
      else if (panel) nav((sp) => sp.delete('panel'));
    } else if (e.key === '/') {
      e.preventDefault();
      document.getElementById('search')?.focus();
    } else if (e.key === 'f' && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      filtersOpen = !filtersOpen;
    } else if (e.key === 'n' || e.key === 'a') {
      e.preventDefault();
      adding = '';
    }
  }
</script>

<svelte:window onkeydown={onKey} />

{#snippet detail()}
  <ItemDetail
    {item}
    loading={itemLoading}
    error={itemError}
    {tz}
    onclose={() => closeDetail()}
    onselect={select}
    startEditing={openEdit}
    onchanged={(it) => (item = it)}
    ondeleted={() => closeDetail(true)}
    onfly={flyToItem}
    onmovepin={() => {
      picking = true;
      if (!app.desktop) snap = 'peek';
    }}
  />
{/snippet}

{#if app.loadError}
  <div class="fatal">
    <h1>Dates</h1>
    {#if app.signedOut}
      <p>Your sign-in expired.</p>
      <button class="btn primary" onclick={() => location.reload()}>Sign in again</button>
    {:else}
      <p>The app could not reach its server: {app.loadError}</p>
      <button class="btn primary" onclick={() => location.reload()}>Try again</button>
    {/if}
  </div>
{:else if !settings}
  <div class="fatal"><LoaderCircle class="spin" size={26} /></div>
{:else}
  <div class="app" class:desktop={app.desktop} class:resizing style:--pane-w="{paneW}px">
    <div class="map-area">
      <MapView
        bind:this={mapView}
        data={mapData}
        theme={theme.resolved}
        tiles={settings.map.tiles}
        assets={settings.map.assets}
        bounds={settings.map.bounds}
        home={settings.home}
        {tz}
        selected={sel?.id ?? null}
        {candidates}
        {circle}
        {padding}
        {picking}
        onpick={onPick}
        onview={(bbox, center, user) => {
          view = { bbox, center };
          if (user) restore = null;
        }}
        onselect={select}
        oncandidate={onCandidate}
        onmapclick={() => {
          if (panel === 'settings') nav((sp) => sp.delete('panel'), true);
          else if (sel) closeDetail();
        }}
        onlocate={(pos) => (me = pos)}
      />
      {#if mapLoading}<div class="loading-bar"></div>{/if}
      {#if mapError}<div class="map-msg">Could not load pins: {mapError}</div>{/if}
    </div>

    <div class="bar-wrap">
      <SearchBar
        {filters}
        {units}
        desktop={app.desktop}
        {filtersOpen}
        onchange={setFilters}
        onfilters={() => (filtersOpen = !filtersOpen)}
        onadd={() => (adding = '')}
        onsettings={openSettings}
      />
    </div>

    {#if app.desktop}
      <div class="pane-head">
        <span class="wordmark">Dates</span>
        <button class="fbtn" class:on={activeCount(filters) > 0} aria-expanded={filtersOpen} aria-controls="filter-panel" onclick={() => (filtersOpen = !filtersOpen)}>
          <SlidersHorizontal size={14} />Filters{#if activeCount(filters)}<span class="bd">{activeCount(filters)}</span>{/if}
        </button>
      </div>
    {/if}

    {#if app.desktop && sel}
      <aside class="insp glass" aria-label="Details">
        {@render detail()}
      </aside>
    {/if}

    <Sheet {snap} desktop={app.desktop} onsnap={(s) => (snap = s)} onheight={(px) => (sheetPx = px)}>
      {#snippet header()}
        {#if (!sel || app.desktop) && panel !== 'settings'}
          <div class="summary">
            <span class="sum-text">
              {#if listMode && globalList}
                {#if filters.archive}
                  <strong>{globalTotal} past event{globalTotal === 1 ? '' : 's'}</strong>
                  <span class="muted">in the Archive, newest first</span>
                {:else}
                  <strong>{globalTotal} match{globalTotal === 1 ? '' : 'es'}</strong>
                  <span class="muted">{filters.q ? `for "${filters.q}"` : 'anywhere'}</span>
                {/if}
              {:else if rows.length}
                <strong>{counts.places} place{counts.places === 1 ? '' : 's'}{counts.events ? `, ${counts.events} event${counts.events === 1 ? '' : 's'}` : ''}</strong>
                <span class="muted">in view</span>
              {:else}
                <strong>Nothing here yet</strong>
              {/if}
            </span>
            {#if !app.desktop}
              <button class="icon-btn sum-gear" aria-label="Settings" title="Settings" onpointerdown={(e) => e.stopPropagation()} onclick={openSettings}><Settings size={18} /></button>
            {/if}
          </div>
        {/if}
      {/snippet}

      {#if sel && !app.desktop}
        {@render detail()}
      {:else if panel === 'settings'}
        <SettingsPanel onclose={() => nav((sp) => sp.delete('panel'))} />
      {:else if shownRows.length}
        <ItemList items={shownRows} {units} {tz} selected={app.desktop ? (sel?.id ?? null) : null} topId={restore?.top ?? null} onselect={select} />
      {:else}
        <div class="empty">
          {#if mapData && mapData.features.length === 0 && JSON.stringify(filters) === JSON.stringify({ ...EMPTY, near: filters.near })}
            <p>No date ideas around here yet.</p>
            <button class="btn primary" onclick={() => (adding = '')}><Plus size={16} /> Add one</button>
          {:else}
            <p>Nothing matches in this part of the map.</p>
            <p class="muted">Zoom out or change the filters.</p>
          {/if}
        </div>
      {/if}
    </Sheet>

    <div class="scrim" class:open={filtersOpen} onclick={() => (filtersOpen = false)} aria-hidden="true"></div>
    <aside id="filter-panel" class="drawer" class:open={filtersOpen} inert={!filtersOpen} aria-label="Filters" bind:this={drawerEl}>
      <FilterPanel
        {filters}
        {units}
        radiusKm={settings.radius_km}
        {reviewCount}
        {resultLabel}
        onchange={setFilters}
        onnear={chooseNear}
        onclose={() => (filtersOpen = false)}
      />
    </aside>

    {#if app.desktop}
      <div
        class="pane-grip"
        role="slider"
        tabindex="0"
        aria-label="Resize the side panel"
        aria-orientation="horizontal"
        aria-valuemin={PANE_MIN}
        aria-valuemax={PANE_MAX}
        aria-valuenow={paneW}
        onpointerdown={paneDown}
        onpointermove={paneMove}
        onpointerup={paneUp}
        onpointercancel={paneUp}
        ondblclick={() => (setPane(PANE_DEFAULT), savePane())}
        onkeydown={paneKey}
      ><span class="grip-handle" aria-hidden="true"></span></div>
    {/if}

    {#if picking}
      <div class="pick">
        <span>Tap the map where the pin should go</span>
        <button class="btn small" onclick={() => (picking = false)}><X size={15} /> Cancel</button>
      </div>
    {/if}

    <Toasts onshow={select} />
  </div>
{/if}

{#if adding !== null}
  <AddDialog initial={adding} onclose={() => (adding = null)} />
{/if}

<style>
  .fatal {
    height: 100%;
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 10px;
    padding: 24px;
    text-align: center;
    color: var(--text-2);
  }
  .fatal h1 {
    margin: 0;
    color: var(--text);
  }
  .app {
    position: fixed;
    inset: 0;
    overflow: hidden;
  }
  .map-area {
    position: absolute;
    inset: 0;
  }
  /* Search bar floating over the map */
  .bar-wrap {
    position: absolute;
    z-index: 20;
    top: calc(var(--safe-top) + 12px);
    left: 10px;
    right: 10px;
  }
  .pane-head {
    display: none;
  }
  .pane-grip {
    display: none;
  }
  .summary {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 16px 8px;
    min-height: 40px;
  }
  .sum-text {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: baseline;
    gap: 6px;
    font-size: 15px;
    overflow: hidden;
    white-space: nowrap;
  }
  .sum-text strong {
    font-size: 17px;
    letter-spacing: -0.01em;
  }
  .sum-gear {
    margin-right: -8px;
  }
  .empty {
    padding: 18px 16px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }
  .empty p {
    margin: 0;
  }
  .pick {
    position: absolute;
    z-index: 25;
    left: 50%;
    transform: translateX(-50%);
    top: calc(var(--safe-top) + 120px);
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 8px 8px 14px;
    border-radius: 14px;
    background: var(--text);
    color: var(--surface);
    box-shadow: var(--shadow-lg);
    font-weight: 600;
    font-size: 14px;
    white-space: nowrap;
  }
  .loading-bar {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    z-index: 5;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    background-size: 40% 100%;
    background-repeat: no-repeat;
    animation: slide 1s linear infinite;
  }
  @keyframes slide {
    from {
      background-position: -40% 0;
    }
    to {
      background-position: 140% 0;
    }
  }
  .map-msg {
    position: absolute;
    z-index: 5;
    left: 50%;
    transform: translateX(-50%);
    bottom: 50%;
    padding: 8px 12px;
    border-radius: 10px;
    background: var(--surface);
    color: var(--danger);
    box-shadow: var(--shadow);
    font-size: 13.5px;
  }

  /* Filters: a tall sheet from the bottom on a phone, a drawer over the list on desktop */
  .scrim {
    position: absolute;
    z-index: 28;
    inset: 0;
    background: rgb(0 0 0 / 0.28);
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s, visibility 0.2s;
  }
  .scrim.open {
    opacity: 1;
    visibility: visible;
  }
  .drawer {
    position: absolute;
    z-index: 30;
    left: 0;
    right: 0;
    bottom: 0;
    top: calc(var(--safe-top) + 70px);
    background: var(--surface);
    border-radius: 20px 20px 0 0;
    box-shadow: 0 -8px 30px rgb(0 0 0 / 0.25);
    transform: translateY(105%);
    visibility: hidden;
    transition: transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1), visibility 0.28s;
  }
  .drawer.open {
    transform: none;
    visibility: visible;
  }
  @media (prefers-reduced-motion: reduce) {
    .drawer,
    .scrim {
      transition: none;
    }
  }

  @media (min-width: 768px) {
    .app {
      display: grid;
      grid-template-columns: var(--pane-w, 400px) 1fr;
      grid-template-rows: auto 1fr;
    }
    .map-area {
      position: relative;
      grid-column: 2;
      grid-row: 1 / 3;
    }
    .bar-wrap {
      top: 10px;
      left: calc(var(--pane-w, 400px) + 12px);
      right: 12px;
      max-width: 620px;
    }
    .pane-head {
      grid-column: 1;
      grid-row: 1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 12px 6px 16px;
      background: var(--surface);
      border-right: 1px solid var(--line);
    }
    .wordmark {
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .fbtn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 30px;
      padding: 0 12px;
      border: none;
      border-radius: 9px;
      background: var(--surface-2);
      color: var(--text);
      font-weight: 600;
    }
    .fbtn:hover {
      background: var(--surface-3);
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
    .app :global(.sheet) {
      grid-column: 1;
      grid-row: 2;
      border-right: 1px solid var(--line);
    }
    .insp {
      position: absolute;
      z-index: 15;
      grid-column: 2;
      top: 64px;
      bottom: 12px;
      right: 12px;
      width: 340px;
      border-radius: 16px;
      overflow: hidden;
      background: color-mix(in srgb, var(--surface) 92%, transparent);
      animation: insp-in 0.22s ease-out;
    }
    @keyframes insp-in {
      from {
        opacity: 0;
        transform: translateX(14px);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .insp {
        animation: none;
      }
    }
    .pick {
      top: 16px;
      left: calc(var(--pane-w, 400px) + (100% - var(--pane-w, 400px)) / 2);
    }
    .scrim {
      right: auto;
      width: var(--pane-w, 400px);
    }
    .drawer {
      right: auto;
      top: 0;
      width: min(300px, var(--pane-w, 400px));
      border-radius: 0;
      border-right: 1px solid var(--line);
      box-shadow: var(--shadow-lg);
      transform: translateX(-104%);
    }
    .pane-grip {
      display: block;
      position: absolute;
      z-index: 24;
      top: 0;
      bottom: 0;
      left: calc(var(--pane-w, 400px) - 4px);
      width: 8px;
      cursor: col-resize;
      touch-action: none;
    }
    .pane-grip::after {
      content: '';
      position: absolute;
      inset: 0 3px;
      background: var(--accent);
      opacity: 0;
      transition: opacity 0.15s;
    }
    .grip-handle {
      position: absolute;
      top: 50%;
      left: 50%;
      width: 6px;
      height: 44px;
      transform: translate(-50%, -50%);
      border-radius: 3px;
      background: var(--text-2);
      border: 1px solid var(--surface);
      opacity: 0.55;
      transition: opacity 0.15s, background 0.15s;
    }
    .pane-grip:hover .grip-handle,
    .pane-grip:focus-visible .grip-handle,
    .resizing .grip-handle {
      opacity: 1;
      background: var(--accent);
    }
    .pane-grip:hover::after,
    .pane-grip:focus-visible::after,
    .resizing .pane-grip::after {
      opacity: 0.6;
    }
    .resizing {
      user-select: none;
      cursor: col-resize;
    }
  }
</style>
