"use client";
/** Silent session telemetry (D3): per-field time, inter-key intervals, pastes, corrections, tab switches,
 * mouse-direction entropy and a 12-dim keystroke-rhythm vector used to link identities typed by one person. */

type FieldStat = { focusMs: number; focusAt: number | null; pasted: boolean };

export class Telemetry {
  start = 0;
  fields: Record<string, FieldStat> = {};
  keyTimes: number[] = [];
  dwell: number[] = [];
  down: Record<string, number> = {};
  corrections = 0;
  blurs = 0;
  dirs = new Array(8).fill(0);
  last: { x: number; y: number } | null = null;
  private off: (() => void)[] = [];

  attach() {
    const onBlur = () => { if (document.visibilityState === "hidden") this.blurs++; };
    const onWinBlur = () => this.blurs++;
    const onMove = (e: MouseEvent) => {
      if (this.last) {
        const dx = e.clientX - this.last.x, dy = e.clientY - this.last.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) this.dirs[Math.floor(((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI)) * 8) % 8]++;
      }
      this.last = { x: e.clientX, y: e.clientY };
    };
    document.addEventListener("visibilitychange", onBlur);
    window.addEventListener("blur", onWinBlur);
    window.addEventListener("mousemove", onMove);
    this.off = [() => document.removeEventListener("visibilitychange", onBlur),
      () => window.removeEventListener("blur", onWinBlur), () => window.removeEventListener("mousemove", onMove)];
  }
  detach() { this.off.forEach((f) => f()); }

  private f(name: string) { return (this.fields[name] ??= { focusMs: 0, focusAt: null, pasted: false }); }

  /** spread onto an <input>: {...tel.bind("name")} */
  bind(name: string) {
    return {
      onFocus: () => { if (!this.start) this.start = performance.now(); this.f(name).focusAt = performance.now(); },
      onBlur: () => { const s = this.f(name); if (s.focusAt) s.focusMs += performance.now() - s.focusAt; s.focusAt = null; },
      onPaste: () => { this.f(name).pasted = true; },
      onKeyDown: (e: React.KeyboardEvent) => {
        const t = performance.now();
        if (e.key === "Backspace" || e.key === "Delete") this.corrections++;
        else if (e.key.length === 1) { this.keyTimes.push(t); this.down[e.key] = t; }
      },
      onKeyUp: (e: React.KeyboardEvent) => {
        const t0 = this.down[e.key];
        if (t0) { this.dwell.push(performance.now() - t0); delete this.down[e.key]; }
      },
    };
  }

  snapshot() {
    const iki: number[] = [];
    for (let i = 1; i < this.keyTimes.length; i++) {
      const d = this.keyTimes[i] - this.keyTimes[i - 1];
      if (d < 2000) iki.push(d); // pauses between fields are not rhythm
    }
    const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
    const std = (a: number[]) => { const m = mean(a); return Math.sqrt(mean(a.map((x) => (x - m) ** 2))); };
    const q = (a: number[], p: number) => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
    const tot = this.dirs.reduce((s, x) => s + x, 0);
    const entropy = tot ? -this.dirs.filter(Boolean).reduce((s, c) => s + (c / tot) * Math.log2(c / tot), 0) : 0;
    const fieldTimes = Object.values(this.fields).map((f) => f.focusMs / 1000);
    // z-scored against typical human typing so cosine similarity compares rhythm shape, not scale
    const raw = [mean(iki), std(iki), q(iki, .1), q(iki, .5), q(iki, .9), mean(this.dwell), std(this.dwell),
      q(this.dwell, .5), iki.filter((x) => x < 100).length / (iki.length || 1), iki.filter((x) => x > 400).length / (iki.length || 1),
      this.corrections / (this.keyTimes.length || 1), mean(fieldTimes)];
    const MU = [185, 70, 90, 170, 300, 95, 30, 90, .15, .1, .05, 8];
    const SD = [60, 30, 30, 55, 120, 30, 15, 30, .12, .1, .05, 6];
    return {
      field_times: fieldTimes.map((x) => +x.toFixed(2)),
      fill_time: +(((performance.now() - (this.start || performance.now())) / 1000)).toFixed(1),
      iki_mean: +mean(iki).toFixed(1), iki_std: +std(iki).toFixed(1),
      paste_fields: Math.min(7, Object.values(this.fields).filter((f) => f.pasted).length),
      corrections: this.corrections, blur_count: this.blurs, mouse_entropy: +entropy.toFixed(2),
      keystroke_vec: raw.map((x, i) => +((x - MU[i]) / SD[i]).toFixed(3)),
    };
  }
}
