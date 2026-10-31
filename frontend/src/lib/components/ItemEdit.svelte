<script lang="ts">
  import MapPin from '@lucide/svelte/icons/map-pin';
  import type { Item } from '$lib/api';
  import { CATEGORIES, labelOf } from '$lib/categories';
  import { fromLocalInput, toLocalInput } from '$lib/format';

  interface Props {
    item: Item;
    tz: string;
    saving: boolean;
    onsave: (patch: Record<string, unknown>) => void;
    oncancel: () => void;
    onmovepin: () => void;
  }

  let { item, tz, saving, onsave, oncancel, onmovepin }: Props = $props();

  // Form copy of the editable fields
  const init = () => ({
    title: item.title,
    category: item.category ?? 'other',
    description: item.description ?? '',
    tags: item.tags.join(', '),
    address_text: item.address_text ?? '',
    website: item.website ?? '',
    phone: item.phone ?? '',
    opening_hours: item.opening_hours ?? '',
    price_level: item.price_level == null ? '' : String(item.price_level),
    standing: item.standing ?? false,
    watch_url: item.watch_url ?? '',
    watch_every_days: String(item.watch_every_days ?? 7),
    starts_at: toLocalInput(item.starts_at, item.tz ?? tz),
    ends_at: toLocalInput(item.ends_at, item.tz ?? tz),
    all_day: item.all_day ?? false,
    recurrence_text: item.recurrence_text ?? '',
    is_free: item.is_free == null ? '' : item.is_free ? 'yes' : 'no',
    price_min: item.price_min == null ? '' : String(item.price_min),
    price_max: item.price_max == null ? '' : String(item.price_max),
    price_text: item.price_text ?? '',
    ticket_url: item.ticket_url ?? '',
    min_age: item.min_age ? String(item.min_age) : ''
  });
  let f = $state(init());
  let error = $state('');
  const isPlace = $derived(item.type === 'place');

  const orNull = (s: string) => (s.trim() ? s.trim() : null);
  const num = (s: string) => (s.trim() === '' ? null : Number(s));

  function submit(e: SubmitEvent) {
    e.preventDefault();
    error = '';
    const base = init();
    const patch: Record<string, unknown> = {};
    const changed = (k: keyof typeof f) => f[k] !== base[k];
    if (!f.title.trim()) {
      error = 'A name is needed.';
      return;
    }
    if (changed('title')) patch.title = f.title.trim();
    if (changed('category')) patch.category = f.category;
    if (changed('description')) patch.description = orNull(f.description);
    if (changed('tags'))
      patch.tags = [...new Set(f.tags.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean))].slice(0, 12);
    if (changed('address_text')) patch.address_text = orNull(f.address_text);
    if (isPlace) {
      if (changed('website')) patch.website = orNull(f.website);
      if (changed('phone')) patch.phone = orNull(f.phone);
      if (changed('opening_hours')) patch.opening_hours = orNull(f.opening_hours);
      if (changed('price_level')) patch.price_level = num(f.price_level);
      if (changed('standing')) patch.standing = f.standing;
      if (changed('watch_url')) patch.watch_url = orNull(f.watch_url);
      if (changed('watch_every_days')) patch.watch_every_days = Math.min(90, Math.max(1, Number(f.watch_every_days) || 7));
      if (f.standing && !f.watch_url.trim() && !f.website.trim()) {
        error = 'A standing venue needs a website or a page to read.';
        return;
      }
    } else {
      const ztz = item.tz ?? tz;
      if (changed('starts_at')) patch.starts_at = f.starts_at ? fromLocalInput(f.starts_at, ztz) : null;
      if (changed('ends_at')) patch.ends_at = f.ends_at ? fromLocalInput(f.ends_at, ztz) : null;
      const s = f.starts_at ? fromLocalInput(f.starts_at, ztz) : null;
      const en = f.ends_at ? fromLocalInput(f.ends_at, ztz) : null;
      if (s && en && en < s) {
        error = 'The end is before the start.';
        return;
      }
      if (changed('all_day')) patch.all_day = f.all_day;
      if (changed('recurrence_text')) patch.recurrence_text = orNull(f.recurrence_text);
      if (changed('is_free')) patch.is_free = f.is_free === '' ? null : f.is_free === 'yes';
      if (changed('price_min')) patch.price_min = num(f.price_min);
      if (changed('price_max')) patch.price_max = num(f.price_max);
      const lo = num(f.price_min);
      const hi = num(f.price_max);
      if (lo != null && hi != null && hi < lo) {
        error = 'The highest price is below the lowest.';
        return;
      }
      if (changed('price_text')) patch.price_text = orNull(f.price_text);
      if (changed('ticket_url')) patch.ticket_url = orNull(f.ticket_url);
      if (changed('min_age')) patch.min_age = f.min_age ? Number(f.min_age) : null;
    }
    // Address edits on events belong to the place
    if (!isPlace) delete patch.address_text;
    onsave(patch);
  }
</script>

<form class="edit" onsubmit={submit}>
  <label>
    <span class="label">Name</span>
    <input class="field" bind:value={f.title} maxlength="200" required />
  </label>
  <div class="two">
    <label>
      <span class="label">Category</span>
      <select class="field" bind:value={f.category}>
        {#each CATEGORIES as c (c)}
          <option value={c}>{labelOf(c)}</option>
        {/each}
      </select>
    </label>
    {#if isPlace}
      <label>
        <span class="label">Price level</span>
        <select class="field" bind:value={f.price_level}>
          <option value="">Unknown</option>
          <option value="0">Free</option>
          <option value="1">$</option>
          <option value="2">$$</option>
          <option value="3">$$$</option>
          <option value="4">$$$$</option>
        </select>
      </label>
    {:else}
      <label>
        <span class="label">Free?</span>
        <select class="field" bind:value={f.is_free}>
          <option value="">Unknown</option>
          <option value="yes">Free</option>
          <option value="no">Paid</option>
        </select>
      </label>
    {/if}
  </div>

  {#if !isPlace}
    <div class="two">
      <label>
        <span class="label">Starts</span>
        <input class="field" type="datetime-local" bind:value={f.starts_at} />
      </label>
      <label>
        <span class="label">Ends</span>
        <input class="field" type="datetime-local" bind:value={f.ends_at} min={f.starts_at} />
      </label>
    </div>
    <label class="check"><input type="checkbox" bind:checked={f.all_day} /> All day</label>
    <label>
      <span class="label">Repeats (as written, for example "every Sunday")</span>
      <input class="field" bind:value={f.recurrence_text} maxlength="200" />
    </label>
    <div class="two">
      <label>
        <span class="label">Lowest price ($)</span>
        <input class="field" type="number" min="0" step="0.01" inputmode="decimal" bind:value={f.price_min} />
      </label>
      <label>
        <span class="label">Highest price ($)</span>
        <input class="field" type="number" min="0" step="0.01" inputmode="decimal" bind:value={f.price_max} />
      </label>
    </div>
    <label>
      <span class="label">Price note</span>
      <input class="field" bind:value={f.price_text} maxlength="200" />
    </label>
    <label>
      <span class="label">Ticket link</span>
      <input class="field" type="url" bind:value={f.ticket_url} />
    </label>
    <label>
      <span class="label">Minimum age</span>
      <select class="field" bind:value={f.min_age}>
        <option value="">Not stated</option>
        <option value="18">18+</option>
        <option value="21">21+</option>
      </select>
    </label>
  {:else}
    <label>
      <span class="label">Address</span>
      <input class="field" bind:value={f.address_text} maxlength="300" />
    </label>
    <div class="two">
      <label>
        <span class="label">Website</span>
        <input class="field" type="url" bind:value={f.website} />
      </label>
      <label>
        <span class="label">Phone</span>
        <input class="field" type="tel" bind:value={f.phone} />
      </label>
    </div>
    <label>
      <span class="label">Opening hours (OSM style, for example "Mo-Fr 17:00-23:00; Sa,Su 12:00-23:00")</span>
      <input class="field" bind:value={f.opening_hours} maxlength="300" />
    </label>
    <fieldset class="standing">
      <label class="check">
        <input type="checkbox" bind:checked={f.standing} />
        <span>Standing venue: keep this place as it is and re-read its page for new events</span>
      </label>
      {#if f.standing}
        <div class="two">
          <label>
            <span class="label">Page to read (blank: the website)</span>
            <input class="field" type="url" bind:value={f.watch_url} placeholder={f.website || 'https://'} />
          </label>
          <label>
            <span class="label">Every how many days</span>
            <input class="field" type="number" min="1" max="90" bind:value={f.watch_every_days} />
          </label>
        </div>
      {/if}
    </fieldset>
  {/if}

  <label>
    <span class="label">Tags (comma separated)</span>
    <input class="field" bind:value={f.tags} />
  </label>
  <label>
    <span class="label">Description</span>
    <textarea class="field" rows="3" bind:value={f.description} maxlength="2000"></textarea>
  </label>

  <button type="button" class="btn small" onclick={onmovepin}><MapPin size={15} /> Move the pin on the map</button>

  {#if error}<p class="error">{error}</p>{/if}
  <div class="actions">
    <button type="button" class="btn" onclick={oncancel} disabled={saving}>Cancel</button>
    <button type="submit" class="btn primary" disabled={saving}>{saving ? 'Saving' : 'Save'}</button>
  </div>
</form>

<style>
  .edit {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .standing {
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 10px;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }
  .check input {
    accent-color: var(--accent);
    width: 17px;
    height: 17px;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    position: sticky;
    bottom: 0;
    padding: 10px 0 4px;
    background: var(--surface);
  }
  .error {
    margin: 0;
    color: var(--danger);
    font-size: 13.5px;
  }
  .btn.small {
    align-self: flex-start;
  }
</style>
