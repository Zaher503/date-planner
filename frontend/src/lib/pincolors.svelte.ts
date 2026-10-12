// Per-category pin colour overrides, remembered on this device

const KEY = 'dates.pincolors';

function read(): Record<string, string> {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    return v && typeof v === 'object' ? v : {};
  } catch {
    return {};
  }
}

class PinColors {
  overrides = $state<Record<string, string>>(read());

  private save() {
    try {
      if (Object.keys(this.overrides).length) localStorage.setItem(KEY, JSON.stringify(this.overrides));
      else localStorage.removeItem(KEY);
    } catch {
      // storage blocked
    }
  }

  set(cat: string, color: string) {
    this.overrides = { ...this.overrides, [cat]: color };
    this.save();
  }

  reset(cat?: string) {
    if (cat) {
      const { [cat]: _drop, ...rest } = this.overrides;
      this.overrides = rest;
    } else {
      this.overrides = {};
    }
    this.save();
  }
}

export const pinColors = new PinColors();
