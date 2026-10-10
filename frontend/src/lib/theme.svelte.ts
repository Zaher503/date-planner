// Light/dark theme: follows the system unless the person picked one (remembered per device)

export type ThemeChoice = 'system' | 'light' | 'dark';

const KEY = 'dates.theme';

function readChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'light' || v === 'dark') return v;
  } catch {
    // storage blocked
  }
  return 'system';
}

const media = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null;

class ThemeState {
  choice = $state<ThemeChoice>(readChoice());
  systemDark = $state(media?.matches ?? false);
  resolved = $derived<'light' | 'dark'>(this.choice === 'system' ? (this.systemDark ? 'dark' : 'light') : this.choice);

  constructor() {
    media?.addEventListener('change', (e) => (this.systemDark = e.matches));
  }

  set(choice: ThemeChoice) {
    this.choice = choice;
    try {
      if (choice === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, choice);
    } catch {
      // storage blocked
    }
  }
}

export const theme = new ThemeState();
