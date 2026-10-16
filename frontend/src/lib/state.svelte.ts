// Shared app state: settings, facets, live job progress and a data version for refetches

import { api, SessionExpired, type AddResult, type Facets, type Job, type Settings } from './api';

export interface Toast {
  key: string;
  jobId: number | null;
  title: string;
  stage: string;
  pct: number;
  status: 'working' | 'done' | 'failed' | 'info';
  // First pinned item, for the Show button
  target: { t: 'place' | 'event'; id: string } | null;
  detail: string;
}

const POLL_MS = 1500;
const DONE_TOAST_MS = 9000;

class AppState {
  settings = $state<Settings | null>(null);
  facets = $state<Facets>({ tags: [], categories: [] });
  loadError = $state('');
  // The sign-in ran out (as opposed to the server being down)
  signedOut = $state(false);
  // Bumped when items change (job finished, edit, delete) so the map refetches
  version = $state(0);
  toasts = $state<Toast[]>([]);
  desktop = $state(false);

  #tracked = new Set<number>();
  #timer: ReturnType<typeof setTimeout> | null = null;

  async init() {
    try {
      this.settings = await api.settings();
    } catch (e) {
      this.signedOut = e instanceof SessionExpired;
      this.loadError = e instanceof Error ? e.message : String(e);
      return;
    }
    this.refreshFacets();
    // Pick up links that are still being read (for example sent from the phone)
    this.poll(true);
  }

  async refreshFacets() {
    try {
      this.facets = await api.facets();
    } catch {
      // keep the old ones
    }
  }

  changed() {
    this.version++;
    this.refreshFacets();
  }

  info(title: string, detail = '', target: Toast['target'] = null) {
    const key = `i${Date.now()}${Math.random()}`;
    this.toasts = [...this.toasts, { key, jobId: null, title, stage: '', pct: 100, status: 'info', target, detail }];
    setTimeout(() => this.dismiss(key), 5000);
  }

  dismiss(key: string) {
    this.toasts = this.toasts.filter((t) => t.key !== key);
  }

  track(res: AddResult, label: string) {
    if (res.status === 'exists') {
      this.info('Already saved', 'That link was added before.');
      return;
    }
    if (res.status === 'stub' || res.job_id == null) {
      this.info('Saved for review', 'This kind of link cannot be read automatically.');
      return;
    }
    this.#tracked.add(res.job_id);
    this.upsertToast(res.job_id, { title: label, stage: 'queued', pct: 2, status: 'working' });
    this.poll();
  }

  private upsertToast(jobId: number, patch: Partial<Toast>) {
    const i = this.toasts.findIndex((t) => t.jobId === jobId);
    if (i === -1) {
      this.toasts = [
        ...this.toasts,
        { key: `j${jobId}`, jobId, title: 'Reading link', stage: '', pct: 0, status: 'working', target: null, detail: '', ...patch }
      ];
    } else {
      this.toasts[i] = { ...this.toasts[i], ...patch };
    }
  }

  private apply(job: Job) {
    const label = job.title || job.url || 'Link';
    if (job.status === 'queued' || job.status === 'running') {
      this.upsertToast(job.id, {
        title: label,
        stage: job.stage === 'retrying' ? 'retrying soon' : job.stage || 'queued',
        pct: Math.max(job.pct, 2),
        status: 'working',
        detail: job.error && job.stage === 'retrying' ? job.error : ''
      });
      return;
    }
    this.#tracked.delete(job.id);
    const items = (job.result?.items ?? []).filter((x) => x.id);
    if (job.status === 'done' && items.length) {
      const first = items[0];
      const names = items.map((x) => x.event_title || x.name).filter(Boolean);
      const review = items.filter((x) => x.review).length;
      this.upsertToast(job.id, {
        title: items.length === 1 ? `Pinned ${names[0]}` : `Pinned ${items.length} places`,
        stage: '',
        pct: 100,
        status: 'done',
        target: first.id && first.type ? { t: first.type, id: first.id } : null,
        detail: [items.length > 1 ? names.slice(0, 4).join(', ') + (names.length > 4 ? ' and more' : '') : '', review ? `${review} need${review === 1 ? 's' : ''} a check` : '']
          .filter(Boolean)
          .join('. ')
      });
      this.changed();
    } else {
      this.upsertToast(job.id, {
        title: label,
        stage: '',
        pct: 100,
        status: 'failed',
        detail: job.error || job.result?.error || 'Nothing could be pinned from this link.'
      });
    }
    const key = `j${job.id}`;
    setTimeout(() => this.dismiss(key), DONE_TOAST_MS);
  }

  // Adopt every active job (a bulk import queues them on the server after the request returns)
  watch() {
    let n = 0;
    const tick = () => {
      this.poll(true);
      if (++n < 6) setTimeout(tick, 2500);
    };
    tick();
  }

  async poll(initial = false) {
    if (this.#timer) {
      clearTimeout(this.#timer);
      this.#timer = null;
    }
    let jobs: Job[] = [];
    try {
      jobs = (await api.jobs()).filter((j) => j.type === 'ingest');
    } catch {
      // try again next tick
    }
    for (const j of jobs) {
      const active = j.status === 'queued' || j.status === 'running';
      if (initial && active) this.#tracked.add(j.id);
      if (this.#tracked.has(j.id)) this.apply(j);
    }
    // A tracked job that dropped out of the list finished more than 5 minutes ago
    const seen = new Set(jobs.map((j) => j.id));
    for (const id of [...this.#tracked]) if (!seen.has(id)) this.#tracked.delete(id);
    if (this.#tracked.size) this.#timer = setTimeout(() => this.poll(), POLL_MS);
  }
}

export const app = new AppState();
