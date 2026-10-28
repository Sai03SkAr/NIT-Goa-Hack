/* Browser helpers shared by both KYC replicas (identical copy in each folder). Plain JS, no build step.
 * TrueID signals SDK: per-field time, keystroke rhythm, pastes, corrections, tab switches, mouse entropy, device hash,
 * virtual-camera detection. Same output shape as clients/northstar-bank/lib/telemetry.ts. */
(function () {
  class Telemetry {
    constructor() {
      this.start = 0; this.fields = {}; this.keyTimes = []; this.dwell = []; this.down = {};
      this.corrections = 0; this.blurs = 0; this.dirs = new Array(8).fill(0); this.last = null;
    }
    attach(root) {
      const f = (el) => el.name || el.id || "field";
      const st = (n) => (this.fields[n] ??= { focusMs: 0, focusAt: null, pasted: false });
      root.addEventListener("focusin", (e) => { if (!e.target.matches("input,textarea,select")) return; if (!this.start) this.start = performance.now(); st(f(e.target)).focusAt = performance.now(); });
      root.addEventListener("focusout", (e) => { if (!e.target.matches("input,textarea,select")) return; const s = st(f(e.target)); if (s.focusAt) s.focusMs += performance.now() - s.focusAt; s.focusAt = null; });
      root.addEventListener("paste", (e) => { if (e.target.matches("input,textarea")) st(f(e.target)).pasted = true; });
      root.addEventListener("keydown", (e) => {
        if (!e.target.matches("input,textarea")) return;
        const t = performance.now();
        if (e.key === "Backspace" || e.key === "Delete") this.corrections++;
        else if (e.key.length === 1) { this.keyTimes.push(t); this.down[e.key] = t; }
      });
      root.addEventListener("keyup", (e) => { const t0 = this.down[e.key]; if (t0) { this.dwell.push(performance.now() - t0); delete this.down[e.key]; } });
      document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") this.blurs++; });
      window.addEventListener("blur", () => this.blurs++);
      window.addEventListener("mousemove", (e) => {
        if (this.last) {
          const dx = e.clientX - this.last.x, dy = e.clientY - this.last.y;
          if (Math.abs(dx) + Math.abs(dy) > 4) this.dirs[Math.floor(((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI)) * 8) % 8]++;
        }
        this.last = { x: e.clientX, y: e.clientY };
      });
    }
    snapshot() {
      const iki = [];
      for (let i = 1; i < this.keyTimes.length; i++) { const d = this.keyTimes[i] - this.keyTimes[i - 1]; if (d < 2000) iki.push(d); }
      const mean = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0);
      const std = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((x) => (x - m) ** 2))); };
      const q = (a, p) => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
      const tot = this.dirs.reduce((s, x) => s + x, 0);
      const entropy = tot ? -this.dirs.filter(Boolean).reduce((s, c) => s + (c / tot) * Math.log2(c / tot), 0) : 0;
      const fieldTimes = Object.values(this.fields).map((f) => f.focusMs / 1000);
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

  async function deviceId(salt) {
    const c = document.createElement("canvas"), g = c.getContext("2d");
    if (g) { g.textBaseline = "top"; g.font = "14px Arial"; g.fillStyle = "#f60"; g.fillRect(0, 0, 80, 20); g.fillStyle = "#069"; g.fillText(salt, 2, 2); }
    const parts = [navigator.userAgent, `${screen.width}x${screen.height}x${screen.colorDepth}`,
      Intl.DateTimeFormat().resolvedOptions().timeZone, navigator.language, String(navigator.hardwareConcurrency), c.toDataURL()];
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(parts.join("|")));
    return "D" + Array.from(new Uint8Array(buf)).slice(0, 5).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  const VIRTUAL = ["virtual", "obs", "manycam", "xsplit", "snap camera", "droidcam", "vcam", "splitcam"];
  async function cameraLabels(stream) {
    const devs = await navigator.mediaDevices.enumerateDevices();
    const labels = devs.filter((d) => d.kind === "videoinput").map((d) => d.label);
    const active = stream.getVideoTracks()[0]?.label ?? "";
    return { labels, active, virtual: VIRTUAL.some((v) => active.toLowerCase().includes(v)) };
  }

  /** Any image source (File, video, canvas) -> JPEG data URL, longest side <= max. */
  async function toJpeg(src, max = 1280, q = 0.88) {
    let img = src;
    if (src instanceof Blob) {
      img = await new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = URL.createObjectURL(src); });
    }
    const w = img.videoWidth || img.naturalWidth || img.width, h = img.videoHeight || img.naturalHeight || img.height;
    const s = Math.min(1, max / Math.max(w, h));
    const c = document.createElement("canvas"); c.width = Math.round(w * s); c.height = Math.round(h * s);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", q);
  }

  const otp = () => String(Math.floor(100000 + Math.random() * 900000));
  const api = async (url, body) => {
    const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    return r.json().then((j) => ({ status: r.status, ...j }));
  };
  /** yyyy-mm-dd (date input) <-> dd/mm/yyyy (registry format) */
  const toDmy = (iso) => (iso ? iso.split("-").reverse().join("/") : "");

  window.KYC = { Telemetry, deviceId, cameraLabels, toJpeg, otp, api, toDmy };
})();
