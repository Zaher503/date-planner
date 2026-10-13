<script lang="ts">
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { dayKey } from '$lib/format';

  interface Props {
    occurrences: { starts_at: string; ends_at: string | null }[];
    tz: string;
    allDay?: boolean;
  }

  let { occurrences, tz, allDay = false }: Props = $props();

  const today = $derived(dayKey(new Date(), tz));
  const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  // Times grouped by calendar day in the event's zone
  const byDay = $derived.by(() => {
    const m = new Map<string, string[]>();
    for (const o of occurrences) {
      const d = new Date(o.starts_at);
      const key = dayKey(d, tz);
      const time = allDay ? '' : new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' }).format(d);
      m.set(key, [...(m.get(key) ?? []), time]);
    }
    return m;
  });
  const days = $derived([...byDay.keys()].sort());
  const upcoming = $derived(days.filter((d) => d >= today));

  // Month on show (first of the month), starting at the next date
  let month = $state('');
  let picked = $state('');
  $effect(() => {
    if (!month) {
      const first = upcoming[0] ?? days[days.length - 1] ?? today;
      month = first.slice(0, 7) + '-01';
      picked = upcoming[0] ?? '';
    }
  });

  function shift(by: number) {
    const [y, m] = month.split('-').map(Number);
    const d = new Date(Date.UTC(y, m - 1 + by, 1));
    month = d.toISOString().slice(0, 10);
  }

  const title = $derived(
    month ? new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(new Date(month + 'T00:00:00Z')) : ''
  );
  const cells = $derived.by(() => {
    if (!month) return [];
    const [y, m] = month.split('-').map(Number);
    const lead = new Date(Date.UTC(y, m - 1, 1)).getUTCDay();
    const n = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const out: (string | null)[] = Array(lead).fill(null);
    for (let d = 1; d <= n; d++) out.push(`${month.slice(0, 8)}${String(d).padStart(2, '0')}`);
    return out;
  });
  const hasBefore = $derived(!!days.length && days[0] < month);
  const hasAfter = $derived.by(() => {
    if (!days.length || !month) return false;
    const [y, m] = month.split('-').map(Number);
    return days[days.length - 1] >= new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 10);
  });

  const longDay = (key: string) =>
    new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'long', month: 'long', day: 'numeric' }).format(new Date(key + 'T00:00:00Z'));
  const pickedTimes = $derived((picked && byDay.get(picked)) || []);
</script>

<div class="cal">
  <div class="head">
    <button class="nav" aria-label="Previous month" disabled={!hasBefore} onclick={() => shift(-1)}><ChevronLeft size={18} /></button>
    <strong>{title}</strong>
    <button class="nav" aria-label="Next month" disabled={!hasAfter} onclick={() => shift(1)}><ChevronRight size={18} /></button>
  </div>
  <div class="grid" role="grid" aria-label="Dates for this event">
    {#each WEEKDAYS as w, i (i)}<span class="wd">{w}</span>{/each}
    {#each cells as key, i (i)}
      {#if key}
        {@const on = byDay.has(key)}
        <button
          class="day"
          class:on
          class:past={on && key < today}
          class:today={key === today}
          class:picked={key === picked}
          disabled={!on}
          aria-label={on ? longDay(key) : undefined}
          aria-pressed={key === picked}
          onclick={() => (picked = key)}>{Number(key.slice(8))}</button>
      {:else}
        <span></span>
      {/if}
    {/each}
  </div>
  <p class="picked-line">
    {#if picked}
      <strong>{longDay(picked)}</strong>{#if pickedTimes.some(Boolean)}<span class="sub"> · {pickedTimes.join(', ')}</span>{/if}
    {:else}
      <span class="sub">{days.length} dates, all past</span>
    {/if}
  </p>
  <p class="count">{upcoming.length} upcoming of {days.length} dates</p>
</div>

<style>
  .cal {
    width: 100%;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 4px;
  }
  .nav {
    display: grid;
    place-items: center;
    width: 30px;
    height: 30px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: var(--text-2);
  }
  .nav:disabled {
    opacity: 0.3;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 2px;
    text-align: center;
  }
  .wd {
    font-size: 11px;
    color: var(--text-3);
    padding: 2px 0;
  }
  .day {
    aspect-ratio: 1;
    max-height: 38px;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: var(--text-3);
    font: inherit;
    font-size: 13px;
  }
  .day.on {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 650;
  }
  .day.past {
    background: var(--surface-2);
    color: var(--text-3);
  }
  .day.today {
    outline: 1.5px solid var(--text-3);
  }
  .day.picked {
    background: var(--accent);
    color: var(--on-accent);
  }
  .picked-line {
    margin: 8px 0 0;
    font-size: 14px;
  }
  .sub {
    color: var(--text-2);
    font-size: 12.5px;
  }
  .count {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--text-3);
  }
</style>
