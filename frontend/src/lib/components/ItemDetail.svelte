<script lang="ts">
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Globe from '@lucide/svelte/icons/globe';
  import Phone from '@lucide/svelte/icons/phone';
  import Ticket from '@lucide/svelte/icons/ticket';
  import Tag from '@lucide/svelte/icons/tag';
  import Repeat from '@lucide/svelte/icons/repeat';
  import Pencil from '@lucide/svelte/icons/pencil';
  import ImageIcon from '@lucide/svelte/icons/image';
  import RefreshCw from '@lucide/svelte/icons/refresh-cw';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import Eye from '@lucide/svelte/icons/eye';
  import Crosshair from '@lucide/svelte/icons/crosshair';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Link from '@lucide/svelte/icons/link';
  import LoaderCircle from '@lucide/svelte/icons/loader-circle';
  import Play from '@lucide/svelte/icons/play';
  import { api, type Item, type ItemType, type MyState, type MyStatus } from '$lib/api';
  import { colorOf, labelOf } from '$lib/categories';
  import { appleMapsUrl, duration, googleMapsUrl, hostOf, longWhen, relativeAgo, when } from '$lib/format';
  import { app } from '$lib/state.svelte';
  import ItemEdit from './ItemEdit.svelte';
  import OccurrenceCalendar from './OccurrenceCalendar.svelte';
  import Stars from './Stars.svelte';

  interface Props {
    item: Item | null;
    loading: boolean;
    error: string;
    tz: string;
    onclose: () => void;
    onselect: (t: ItemType, id: string, edit?: boolean) => void;
    startEditing?: boolean;
    onchanged: (item: Item) => void;
    ondeleted: () => void;
    onfly: () => void;
    onmovepin: () => void;
  }

  let { item, loading, error, tz, startEditing = false, onclose, onselect, onchanged, ondeleted, onfly, onmovepin }: Props = $props();

  let editing = $state(false);
  let saving = $state(false);
  let busy = $state('');
  let confirmDelete = $state(false);
  let notes = $state('');
  let notesSaved = $state(true);
  let actionError = $state('');
  let notesTimer: ReturnType<typeof setTimeout> | null = null;
  let lastId = '';

  // Reset local state when a different item opens
  $effect(() => {
    const id = item?.id ?? '';
    if (id !== lastId) {
      lastId = id;
      editing = startEditing;
      playing = false;
      showPics = false;
      showOriginal = false;
      showSources = false;
      confirmDelete = false;
      actionError = '';
      notes = item?.me?.notes ?? '';
      notesSaved = true;
    }
  });

  const thumbSource = $derived(item?.sources.find((s) => s.thumb) ?? null);
  const videoSource = $derived(item?.sources.find((s) => s.video) ?? null);
  let playing = $state(false);
  let showPics = $state(false);
  const pics = $derived(item?.images ?? []);
  const hero = $derived(pics.find((i) => i.chosen) ?? null);
  const heroSrc = $derived(hero?.url ?? videoSource?.thumb ?? null);
  const stamp = (s: number | null) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`);

  async function pickImage(id: number | null) {
    if (!item) return;
    const it = item;
    const updated = await run('image', () => api.setImage(it.type, it.id, id));
    if (updated) {
      onchanged(updated);
      app.changed();
    }
  }
  const color = $derived(colorOf(item?.category));
  const isEvent = $derived(item?.type === 'event');
  const unsure = $derived(!!item && item.candidates.length > 0 && (item.review_status === 'needs_review' || isEvent));
  const hidden = $derived(item?.review_status === 'dismissed');
  const venueName = $derived.by(() => {
    const v = item?.venue_name?.trim();
    if (!isEvent || !v || v === item?.title || v === item?.place?.title) return null;
    return v;
  });
  const originalText = $derived.by(() => {
    const text = item?.sources.find((s) => s.caption?.trim())?.caption?.trim() ?? '';
    return text && text !== item?.description?.trim() ? text : '';
  });
  let showOriginal = $state(false);
  let showSources = $state(false);

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    busy = label;
    actionError = '';
    try {
      return await fn();
    } catch (e) {
      actionError = e instanceof Error ? e.message : String(e);
    } finally {
      busy = '';
    }
  }

  async function setMine(patch: Partial<MyState>) {
    if (!item) return;
    const it = item;
    const me = await run('me', () => api.setMine(it.type, it.id, patch));
    if (me) {
      onchanged({ ...it, me });
      app.changed();
    }
  }

  function status(s: MyStatus) {
    setMine({ status: item?.me?.status === s ? null : s });
  }

  function notesInput() {
    notesSaved = false;
    if (notesTimer) clearTimeout(notesTimer);
    notesTimer = setTimeout(saveNotes, 900);
  }

  async function saveNotes() {
    if (notesTimer) clearTimeout(notesTimer);
    if (!item || notesSaved) return;
    const value = notes.trim() ? notes : null;
    if ((item.me?.notes ?? null) === value) {
      notesSaved = true;
      return;
    }
    await setMine({ notes: value });
    notesSaved = true;
  }

  async function save(patch: Record<string, unknown>) {
    if (!item) return;
    if (!Object.keys(patch).length) {
      editing = false;
      return;
    }
    const it = item;
    saving = true;
    const updated = await run('save', () => api.patch(it.type, it.id, patch));
    saving = false;
    if (updated) {
      editing = false;
      onchanged(updated);
      app.changed();
    }
  }

  async function reprocess() {
    if (!item) return;
    const it = item;
    const res = await run('reprocess', () => api.reprocess(it.type, it.id));
    if (res) {
      if (!res.jobs.length) app.info('Nothing to reread', 'This item has no link to read again.');
      for (const id of res.jobs) app.track({ status: 'queued', job_id: id, source_id: '', kind: '' }, `Rereading ${it.title}`);
    }
  }

  async function remove() {
    if (!item) return;
    if (!confirmDelete) {
      confirmDelete = true;
      setTimeout(() => (confirmDelete = false), 4000);
      return;
    }
    const it = item;
    const ok = await run('delete', async () => {
      await api.remove(it.type, it.id);
      return true;
    });
    if (ok) {
      app.info(`Deleted ${it.title}`);
      app.changed();
      ondeleted();
    }
  }

  async function toggleHidden() {
    if (!item) return;
    await save({ review_status: hidden ? 'ok' : 'dismissed' });
  }

  async function choose(candidateId: number | null) {
    if (!item) return;
    const placeId = item.type === 'place' ? item.id : item.place?.id;
    if (!placeId) return;
    const it = item;
    const res = await run('resolve', () => api.resolve(placeId, candidateId));
    if (res) {
      const fresh = await run('reload', () => api.item(it.type, it.id));
      if (fresh) onchanged(fresh);
      app.changed();
    }
  }

  function sourceLabel(kind: string): string {
    return (
      { tiktok: 'TikTok', youtube: 'YouTube', gmaps: 'Google Maps', applemaps: 'Apple Maps', event_page: 'Web page', text: 'Note', image: 'Screenshot', instagram: 'Instagram' }[kind] ??
      kind
    );
  }

  function statusWord(s: MyStatus | null): string {
    return s ? { want: 'wants to go', going: 'is going', been: 'has been', dismissed: 'passed' }[s] : '';
  }
</script>

<div class="detail">
  <header>
    <button class="icon-btn" aria-label="Back to the list" onclick={onclose}><ChevronLeft size={22} /></button>
    {#if item}
      <span class="cat" style="--c: {color}"><span class="dot" class:event={isEvent}></span>{labelOf(item.category)}{isEvent ? ' event' : ''}</span>
      <button class="icon-btn" aria-label="Show on the map" title="Show on the map" onclick={onfly}><Crosshair size={19} /></button>
    {/if}
  </header>

  {#if loading && !item}
    <div class="state"><LoaderCircle class="spin" size={22} /></div>
  {:else if error && !item}
    <div class="state error">{error}</div>
  {:else if item}
    <div class="body">
      <h2>{item.title}</h2>
      {#if isEvent && item.place && item.place.title !== item.title}
        <button class="link-row" onclick={() => item?.place && onselect('place', item.place.id)}>at {item.place.title}</button>
      {/if}

      {#if hidden}
        <div class="banner muted-banner"><EyeOff size={16} /> Hidden from the map.</div>
      {/if}

      {#if unsure}
        <section class="banner review">
          <div class="banner-title"><TriangleAlert size={16} /> Not sure this pin is right</div>
          <p>Pick the right place. The letters are shown on the map.</p>
          <ul class="cands">
            {#each item.candidates as c, i (c.id)}
              <li class:chosen={c.chosen}>
                <span class="letter">{String.fromCharCode(65 + i)}</span>
                <span class="cand-text">
                  <span class="cand-name">{c.name}</span>
                  {#if c.address}<span class="cand-addr">{c.address}</span>{/if}
                </span>
                {#if c.chosen}
                  <span class="cand-now">Current</span>
                {:else}
                  <button class="btn small" disabled={!!busy} onclick={() => choose(c.id)}>Use</button>
                {/if}
              </li>
            {/each}
          </ul>
          <div class="review-actions">
            <button class="btn small primary" disabled={!!busy} onclick={() => choose(null)}>The current pin is right</button>
            <button class="btn small" disabled={!!busy} onclick={onmovepin}><MapPin size={14} /> Put it somewhere else</button>
          </div>
        </section>
      {/if}

      {#if editing}
        <ItemEdit {item} {tz} {saving} onsave={save} oncancel={() => (editing = false)} {onmovepin} />
      {:else}
        {#if videoSource && playing}
          <!-- svelte-ignore a11y_media_has_caption -->
          <video class="player" src="{videoSource.video}{hero?.kind === 'frame' && hero.at != null ? `#t=${hero.at}` : ''}" poster={heroSrc ?? undefined} controls autoplay playsinline></video>
        {:else if videoSource}
          <button class="media" onclick={() => (playing = true)}>
            {#if heroSrc}<img src={heroSrc} alt="" loading="lazy" />{:else}<span class="noimg"></span>{/if}
            <span class="play"><Play size={26} /></span>
            <span class="media-label">Saved copy of the {sourceLabel(videoSource.kind)} video</span>
          </button>
        {:else if thumbSource}
          <a class="media" href={thumbSource.url ?? undefined} target="_blank" rel="noopener noreferrer">
            <img src={hero?.url ?? thumbSource.thumb} alt="" loading="lazy" />
            <span class="media-label"><ExternalLink size={13} /> Open on {sourceLabel(thumbSource.kind)}</span>
          </a>
        {:else if hero}
          <div class="media"><img src={hero.url} alt="" loading="lazy" /></div>
        {/if}

        {#if pics.length > 1 || (pics.length === 1 && !hero)}
          <button class="pics-toggle" onclick={() => (showPics = !showPics)} aria-expanded={showPics}>
            <ImageIcon size={14} /> {showPics ? 'Hide pictures' : 'Change picture'}
          </button>
          {#if showPics}
            <div class="pics" role="group" aria-label="Choose a picture">
              {#if heroSrc || thumbSource}
                {@const first = thumbSource?.thumb ?? videoSource?.thumb}
                {#if first}
                  <button class="pic" class:on={!hero} disabled={busy === 'image'} onclick={() => pickImage(null)} title="Link thumbnail">
                    <img src={first} alt="Link thumbnail" loading="lazy" />
                  </button>
                {/if}
              {/if}
              {#each pics as p (p.id)}
                <button class="pic" class:on={p.chosen} disabled={busy === 'image'} onclick={() => pickImage(p.id)}
                  title={p.at != null ? `Video at ${stamp(p.at)}` : 'Photo from the page'}>
                  <img src={p.url} alt="Option" loading="lazy" />
                  {#if p.at != null}<span class="pic-time">{stamp(p.at)}</span>{/if}
                </button>
              {/each}
            </div>
          {/if}
        {/if}

        <div class="mine">
          <div class="seg" role="group" aria-label="My status">
            <button class:on={item.me?.status === 'want'} disabled={busy === 'me'} onclick={() => status('want')}><Bookmark size={16} /> Want</button>
            <button class:on={item.me?.status === 'going'} disabled={busy === 'me'} onclick={() => status('going')}><CalendarCheck size={16} /> Going</button>
            <button class:on={item.me?.status === 'been'} class:been={item.me?.status === 'been'} disabled={busy === 'me'} onclick={() => status('been')}><CircleCheck size={16} /> Been</button>
          </div>
          <div class="rate">
            <Stars value={item.me?.rating ?? null} onchange={(v) => setMine({ rating: v })} />
          </div>
        </div>

        <ul class="facts">
          {#if isEvent}
            {#if item.starts_at && (item.occurrences?.length ?? 0) <= 1}
              <li>
                <Clock size={17} />
                <span>
                  {longWhen(item.starts_at, item.ends_at ?? null, { allDay: item.all_day, tz: item.tz ?? tz })}
                  {#if item.duration_min && !item.all_day}
                    <span class="sub">{duration(item.duration_min)}{item.duration_estimated ? ' (estimated)' : ''}</span>
                  {/if}
                </span>
              </li>
            {/if}
            {#if (item.occurrences?.length ?? 0) > 1}
              <li class="cal-row"><CalendarDays size={17} /><OccurrenceCalendar occurrences={item.occurrences ?? []} tz={item.tz ?? tz} allDay={!!item.all_day} /></li>
            {/if}
            {#if item.recurrence_text}
              <li><Repeat size={17} /><span>{item.recurrence_text.replace(/^\w/, (c) => c.toUpperCase())}</span></li>
            {/if}
            {#if !item.starts_at && !item.recurrence_text}
              <li><Clock size={17} /><span class="muted">Date not known</span></li>
            {/if}
          {:else if item.opening_hours}
            <li>
              <Clock size={17} />
              <span>
                {#if item.open_now === true}<span class="open">Open now</span>{:else if item.open_now === false}<span class="closed">Closed now</span>{/if}
                <span class="sub mono">{item.opening_hours}</span>
              </span>
            </li>
          {:else if item.hours_text}
            <li><Clock size={17} /><span class="sub">{item.hours_text}</span></li>
          {/if}
          {#if item.price_label || item.price_text}
            <li>
              <Ticket size={17} />
              <span>{item.price_label ?? ''}{#if item.price_text && item.price_text !== item.price_label}<span class="sub">{item.price_text}</span>{/if}</span>
            </li>
          {/if}
          {#if item.price_tiers?.length}
            <li class="tiers">
              <span></span>
              <span>
                {#each item.price_tiers as t}
                  <span class="sub">{t.label}: {t.price == null ? 'ask' : '$' + t.price}{t.note ? ` (${t.note})` : ''}</span>
                {/each}
              </span>
            </li>
          {/if}
          <li>
            <MapPin size={17} />
            <span>
              {#if venueName}<strong class="venue">{venueName}</strong>{/if}
              {#if item.address_text}{item.address_text}{:else if !venueName}{(isEvent ? item.venue_name : null) ?? 'No address yet'}{/if}
              <span class="maplinks">
                <a href={appleMapsUrl(item.lat, item.lon, item.title, item.address_text)} target="_blank" rel="noopener noreferrer">Apple Maps</a>
                <a href={googleMapsUrl(item.lat, item.lon, item.title, item.address_text)} target="_blank" rel="noopener noreferrer">Google Maps</a>
              </span>
            </span>
          </li>
          {#if item.website}
            <li><Globe size={17} /><a href={item.website} target="_blank" rel="noopener noreferrer">{hostOf(item.website)}</a></li>
          {/if}
          {#if item.phone}
            <li><Phone size={17} /><a href="tel:{item.phone}">{item.phone}</a></li>
          {/if}
          {#if item.ticket_url}
            <li><Ticket size={17} /><a href={item.ticket_url} target="_blank" rel="noopener noreferrer">Tickets on {hostOf(item.ticket_url)}</a></li>
          {/if}
        </ul>

        {#if item.description}
          <p class="desc">{item.description}</p>
        {/if}

        {#if originalText}
          <section class="original">
            <button class="toggle" aria-expanded={showOriginal} onclick={() => (showOriginal = !showOriginal)}>
              <ChevronDown size={16} class={showOriginal ? 'flip' : ''} /> Original description
            </button>
            {#if showOriginal}<p class="desc orig-text">{originalText}</p>{/if}
          </section>
        {/if}

        {#if item.tags.length}
          <div class="tags"><Tag size={15} />{#each item.tags as t (t)}<span class="tag">{t}</span>{/each}</div>
        {/if}

        <section>
          <label class="label" for="notes">My notes {#if !notesSaved}<span class="saving">saving</span>{/if}</label>
          <textarea id="notes" class="field" rows="2" placeholder="Parking, what to order, who told us about it" bind:value={notes} oninput={notesInput} onblur={saveNotes}></textarea>
        </section>

        {#if item.others.some((o) => o.status || o.rating || o.notes)}
          <section class="others">
            {#each item.others as o (o.user)}
              {#if o.status || o.rating || o.notes}
                <div class="other">
                  <div>
                    <strong>{o.user}</strong>
                    {statusWord(o.status)}
                    {#if o.rating}<Stars value={o.rating} readonly size={14} />{/if}
                  </div>
                  {#if o.notes}<p>{o.notes}</p>{/if}
                </div>
              {/if}
            {/each}
          </section>
        {/if}

        {#if item.events?.length}
          <section>
            <h3>Events here</h3>
            <ul class="linked">
              {#each item.events as ev (ev.id)}
                <li class="ev-row">
                  <button class="ev-open" onclick={() => onselect('event', ev.id)}>
                    <span>{ev.title}</span>
                    <span class="sub">{[ev.starts_at ? when(ev.starts_at, { tz }) : ev.recurrence_text, ev.price_label].filter(Boolean).join(' · ')}</span>
                  </button>
                  <button class="ev-edit" aria-label="Edit {ev.title}" title="Edit" onclick={() => onselect('event', ev.id, true)}><Pencil size={15} /></button>
                </li>
              {/each}
            </ul>
          </section>
        {/if}

        {#if actionError}<p class="error">{actionError}</p>{/if}

        <div class="actions">
          <button class="btn small" onclick={() => (editing = true)}><Pencil size={15} /> Edit</button>
          <button class="btn small" disabled={!!busy} onclick={reprocess}><RefreshCw size={15} class={busy === 'reprocess' ? 'spin' : ''} /> Reread link</button>
          <button class="btn small" disabled={!!busy} onclick={toggleHidden}>
            {#if hidden}<Eye size={15} /> Show again{:else}<EyeOff size={15} /> Hide{/if}
          </button>
          <button class="btn small danger" disabled={busy === 'delete'} onclick={remove}><Trash2 size={15} /> {confirmDelete ? 'Tap again to delete' : 'Delete'}</button>
        </div>
        {#if item.edited.length}
          <p class="fine">Your edits ({item.edited.join(', ')}) are kept when the link is reread.</p>
        {/if}

        {#if item.sources.length}
          <div class="saved-from">
            <button class="chip" aria-expanded={showSources} onclick={() => (showSources = !showSources)}>
              <Link size={13} /> Saved from {item.sources.length === 1 ? sourceLabel(item.sources[0].kind) : `${item.sources.length} links`}
            </button>
            {#if showSources}
              <ul class="sources">
                {#each item.sources as s (s.id)}
                  <li>
                    <span>
                      {#if s.url}
                        <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || hostOf(s.url) || sourceLabel(s.kind)}</a>
                      {:else}
                        {s.title || sourceLabel(s.kind)}
                      {/if}
                      <span class="sub">{sourceLabel(s.kind)} · {relativeAgo(s.created_at)}{s.submitted_by ? ` by ${s.submitted_by}` : ''}</span>
                    </span>
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .detail {
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
  .cat {
    flex: 1;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-2);
  }
  .dot {
    width: 11px;
    height: 11px;
    border-radius: 50%;
    background: var(--c);
  }
  .dot.event {
    border-radius: 3px;
  }
  .state {
    display: grid;
    place-items: center;
    padding: 40px;
    color: var(--text-3);
  }
  .state.error {
    color: var(--danger);
  }
  .body {
    flex: 1;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 0 16px 24px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  h2 {
    margin: 0;
    font-size: 22px;
    line-height: 1.2;
    letter-spacing: -0.01em;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 13px;
    color: var(--text-2);
    font-weight: 650;
  }
  .link-row {
    align-self: flex-start;
    margin-top: -10px;
    border: none;
    background: none;
    padding: 0;
    color: var(--accent);
    font-weight: 550;
  }
  .banner {
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 14px;
  }
  .muted-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface-2);
    color: var(--text-2);
  }
  .banner.review {
    background: var(--warn-soft);
  }
  .banner-title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 650;
    color: var(--warn);
  }
  .banner p {
    margin: 4px 0 8px;
    color: var(--text-2);
    font-size: 13px;
  }
  .cands {
    list-style: none;
    margin: 0 0 10px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .cands li {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--surface);
    border-radius: 10px;
    padding: 7px 8px;
  }
  .cands li.chosen {
    outline: 2px solid var(--ok);
  }
  .letter {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: var(--text);
    color: var(--surface);
    font-weight: 700;
    font-size: 12px;
    flex: none;
  }
  .chosen .letter {
    background: var(--ok);
  }
  .cand-text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .cand-name {
    font-weight: 600;
    font-size: 14px;
  }
  .cand-addr {
    font-size: 12.5px;
    color: var(--text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cand-now {
    font-size: 12px;
    font-weight: 650;
    color: var(--ok);
  }
  .review-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .media {
    position: relative;
    display: block;
    border-radius: 14px;
    overflow: hidden;
    background: var(--surface-2);
    max-height: 260px;
  }
  button.media {
    border: none;
    padding: 0;
    width: 100%;
    cursor: pointer;
  }
  .noimg {
    display: block;
    height: 180px;
  }
  .play {
    position: absolute;
    inset: 0;
    margin: auto;
    width: 58px;
    height: 58px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    background: rgb(0 0 0 / 0.55);
    color: #fff;
  }
  .player {
    width: 100%;
    max-height: 70vh;
    border-radius: 14px;
    background: #000;
  }
  .media img {
    display: block;
    width: 100%;
    max-height: 260px;
    object-fit: cover;
  }
  .media-label {
    position: absolute;
    left: 8px;
    bottom: 8px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 9px;
    border-radius: 999px;
    background: rgb(0 0 0 / 0.62);
    color: #fff;
    font-size: 12px;
    font-weight: 600;
  }
  .pics-toggle {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: none;
    background: none;
    padding: 2px 0;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--text-2);
    cursor: pointer;
  }
  .pics {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 4px;
  }
  .pic {
    position: relative;
    flex: none;
    width: 96px;
    height: 72px;
    padding: 0;
    border: 2px solid transparent;
    border-radius: 10px;
    overflow: hidden;
    background: var(--surface-2);
    cursor: pointer;
  }
  .pic.on {
    border-color: var(--accent);
  }
  .pic img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .pic-time {
    position: absolute;
    right: 3px;
    bottom: 3px;
    padding: 1px 5px;
    border-radius: 999px;
    background: rgb(0 0 0 / 0.62);
    color: #fff;
    font-size: 11px;
    font-weight: 600;
  }
  .mine {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .seg {
    display: inline-flex;
    background: var(--surface-2);
    border-radius: 12px;
    padding: 3px;
    gap: 2px;
  }
  .seg button {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: none;
    background: transparent;
    padding: 7px 11px;
    border-radius: 9px;
    font-weight: 600;
    font-size: 13.5px;
    color: var(--text-2);
  }
  .seg button.on {
    background: var(--surface);
    color: var(--accent);
    box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
  }
  .seg button.on.been {
    color: var(--ok);
  }
  .facts {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .facts li {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    font-size: 14.5px;
  }
  .facts li > :global(svg) {
    flex: none;
    margin-top: 1px;
    color: var(--text-3);
  }
  .tiers > :first-child {
    flex: none;
    width: 17px;
  }
  .cal-row > :global(.cal) {
    flex: 1;
    min-width: 0;
  }
  .sub {
    display: block;
    font-size: 12.5px;
    color: var(--text-2);
  }
  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px;
  }
  .open {
    color: var(--ok);
    font-weight: 650;
  }
  .closed {
    color: var(--danger);
    font-weight: 650;
  }
  .maplinks {
    display: flex;
    gap: 14px;
    margin-top: 3px;
    font-size: 13px;
    font-weight: 600;
  }
  .maplinks a {
    text-decoration: none;
  }
  .desc {
    margin: 0;
    font-size: 14.5px;
    color: var(--text);
    white-space: pre-line;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    color: var(--text-3);
  }
  .tag {
    padding: 3px 9px;
    border-radius: 999px;
    background: var(--surface-2);
    color: var(--text-2);
    font-size: 12.5px;
    font-weight: 550;
  }
  .saving {
    font-weight: 500;
    color: var(--text-3);
    margin-left: 6px;
  }
  .others {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .other {
    background: var(--surface-2);
    border-radius: 12px;
    padding: 9px 12px;
    font-size: 14px;
  }
  .other div {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .other p {
    margin: 4px 0 0;
    color: var(--text-2);
  }
  .linked,
  .sources {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .ev-row {
    display: flex;
    gap: 6px;
  }
  .ev-open {
    flex: 1;
    min-width: 0;
  }
  .linked .ev-edit {
    flex: none;
    width: 40px;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 10px;
    display: grid;
    place-items: center;
  }
  .linked .ev-open {
    width: auto;
  }
  .linked button {
    width: 100%;
    text-align: left;
    border: 1px solid var(--line);
    background: var(--surface);
    border-radius: 10px;
    padding: 8px 10px;
    font-weight: 600;
  }
  .sources li {
    font-size: 13.5px;
  }
  .venue {
    display: block;
    font-weight: 650;
  }
  .toggle {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: none;
    background: none;
    padding: 0;
    color: var(--text-2);
    font-size: 13px;
    font-weight: 650;
  }
  .toggle :global(svg) {
    transition: transform 0.15s;
    transform: rotate(-90deg);
  }
  .toggle :global(svg.flip) {
    transform: none;
  }
  .orig-text {
    margin-top: 6px;
    font-size: 13.5px;
    color: var(--text-2);
    word-break: break-word;
  }
  .saved-from {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border: 1px solid var(--line);
    background: var(--surface-2);
    color: var(--text-2);
    border-radius: 999px;
    padding: 3px 10px;
    font-size: 12px;
    font-weight: 600;
  }
  .sources a {
    word-break: break-word;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding-top: 4px;
    border-top: 1px solid var(--line);
    padding-top: 12px;
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: 13.5px;
  }
  .fine {
    margin: -6px 0 0;
    font-size: 12px;
    color: var(--text-3);
  }
</style>
