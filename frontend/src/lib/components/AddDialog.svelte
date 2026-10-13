<script lang="ts">
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
  import ImageIcon from '@lucide/svelte/icons/image';
  import { api } from '$lib/api';
  import { hostOf } from '$lib/format';
  import { app } from '$lib/state.svelte';

  interface Props {
    initial?: string;
    onclose: () => void;
  }

  let { initial = '', onclose }: Props = $props();
  let text = $state(untrack(() => initial));
  let sending = $state(false);
  let error = $state('');
  let image = $state<File | null>(null);
  let preview = $state('');
  let picker: HTMLInputElement;
  let box: HTMLTextAreaElement;
  let dialog: HTMLDialogElement;

  $effect(() => {
    dialog.showModal();
    box.focus();
  });

  const canPaste = typeof navigator !== 'undefined' && !!navigator.clipboard?.readText;

  async function paste() {
    try {
      text = (await navigator.clipboard.readText()).trim();
      box.focus();
    } catch {
      error = 'The browser did not allow reading the clipboard. Long-press the box and paste.';
    }
  }

  function label(t: string): string {
    const url = t.match(/https?:\/\/\S+/)?.[0];
    if (!url) return t.length > 40 ? t.slice(0, 40) + '...' : t;
    const host = hostOf(url);
    if (host.includes('tiktok')) return 'TikTok link';
    if (host.includes('google') || host.includes('goo.gl')) return 'Google Maps link';
    if (host.includes('apple')) return 'Apple Maps link';
    return host || 'Link';
  }

  function setImage(f: File | null) {
    if (preview) URL.revokeObjectURL(preview);
    image = f;
    preview = f ? URL.createObjectURL(f) : '';
    error = '';
    if (f && f.size > 10_000_000) {
      error = 'That image is over 10 MB.';
      image = null;
      preview = '';
    }
  }

  // Pasting a screenshot into the box attaches it
  function pasted(e: ClipboardEvent) {
    const f = [...(e.clipboardData?.files ?? [])].find((x) => x.type.startsWith('image/'));
    if (f) {
      e.preventDefault();
      setImage(f);
    }
  }

  // Several links pasted at once are added one by one
  const links = $derived([...new Set(text.match(/https?:\/\/[^\s<>"]+/g) ?? [])]);

  async function bulk() {
    const res = await api.addBulk(links);
    app.info(`Importing ${res.accepted} links`, 'They are read in the background. Open the queue to follow them.');
    app.watch();
    onclose();
  }

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    const t = text.trim();
    if (!t && !image) return;
    sending = true;
    error = '';
    try {
      if (!image && links.length > 1) {
        await bulk();
        return;
      }
      if (image) {
        app.track(await api.addImage(image, image.name || 'screenshot.png'), 'Screenshot');
        setImage(null);
        if (!t) {
          onclose();
          return;
        }
      }
      const res = await api.add(t);
      app.track(res, label(t));
      onclose();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      sending = false;
    }
  }
</script>

<dialog bind:this={dialog} onclose={onclose} onclick={(e) => e.target === dialog && onclose()}>
  <form onsubmit={submit}>
    <header>
      <h2>Add a date idea</h2>
      <button type="button" class="icon-btn" aria-label="Close" onclick={onclose}><X size={20} /></button>
    </header>
    <p class="muted">Paste a TikTok (or a whole list of links), a Google or Apple Maps link, an event page, a screenshot, or just type a place and what it is.</p>
    <textarea
      bind:this={box}
      class="field"
      rows="4"
      maxlength="8000"
      placeholder="https://www.tiktok.com/@... or 'Rooftop jazz at Perch, Saturday 8pm'"
      bind:value={text}
      onpaste={pasted}
      onkeydown={(e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) (e.currentTarget.form as HTMLFormElement).requestSubmit();
      }}
    ></textarea>
    {#if links.length > 1}<p class="muted">{links.length} links found, each will be added as its own idea.</p>{/if}
    {#if preview}
      <div class="shot">
        <img src={preview} alt="Screenshot to add" />
        <button type="button" class="btn small" onclick={() => setImage(null)}>Remove</button>
      </div>
    {/if}
    {#if error}<p class="error">{error}</p>{/if}
    <input bind:this={picker} type="file" accept="image/png,image/jpeg,image/webp" hidden onchange={(e) => setImage(e.currentTarget.files?.[0] ?? null)} />
    <div class="actions">
      {#if canPaste}
        <button type="button" class="btn" onclick={paste}><ClipboardPaste size={16} /> Paste</button>
      {/if}
      <button type="button" class="btn" onclick={() => picker.click()}><ImageIcon size={16} /> Screenshot</button>
      <span class="spacer"></span>
      <button type="button" class="btn" onclick={onclose}>Cancel</button>
      <button type="submit" class="btn primary" disabled={sending || (!text.trim() && !image)}>{sending ? 'Adding' : links.length > 1 ? `Add ${links.length}` : 'Add'}</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(520px, calc(100vw - 24px));
    border: none;
    border-radius: 18px;
    padding: 0;
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow-lg);
    margin: auto;
  }
  dialog::backdrop {
    background: rgb(10 10 15 / 0.45);
  }
  form {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h2 {
    margin: 0;
    font-size: 18px;
  }
  p {
    margin: 0;
    font-size: 14px;
  }
  .error {
    color: var(--danger);
  }
  .shot {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .shot img {
    width: 72px;
    height: 72px;
    object-fit: cover;
    border-radius: 10px;
    border: 1px solid var(--line);
  }
  .actions {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .spacer {
    flex: 1;
  }
  @media (max-width: 767px) {
    dialog {
      margin: auto auto 12px;
    }
  }
</style>
