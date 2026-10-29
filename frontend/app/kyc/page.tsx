"use client";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import clsx from "clsx";
import { Camera, Check, ChevronRight, Lock, ShieldCheck, Sparkles, Upload, Wand2 } from "lucide-react";
import { Logo } from "@/components/ui";
import { ApiError, fileUrl, post } from "@/lib/api";
import { Telemetry } from "@/lib/telemetry";
import { cameraLabels, deviceId } from "@/lib/device";
import { CHALLENGE_TEXT, type Challenge, type ServerChallenge, getLandmarker, grabFrame, satisfied, signal } from "@/lib/liveness";

type Form = { name: string; dob: string; gender: string; id_number: string; pan: string; phone: string; email: string; address: string; pincode: string };
const EMPTY: Form = { name: "", dob: "", gender: "M", id_number: "", pan: "", phone: "", email: "", address: "", pincode: "" };
const STEPS = ["Consent", "Your details", "ID card", "Face check"];

export default function Page() {
  return <Suspense><Wizard /></Suspense>;
}

function Wizard() {
  const router = useRouter();
  const demo = useSearchParams().get("demo") === "1";
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Form>(EMPTY);
  const [card, setCard] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");
  const tel = useMemo(() => new Telemetry(), []);
  useEffect(() => { tel.attach(); return () => tel.detach(); }, [tel]);
  // applicant session cookie (HttpOnly) + the consent notice version the server expects
  const [consentVersion, setConsentVersion] = useState("");
  const [footprint, setFootprint] = useState(false);  // separate, optional purpose
  useEffect(() => { post<{ consent_version: string }>("/api/session").then((r) => setConsentVersion(r.consent_version)).catch((e) => setErr(String(e))); }, []);
  // one key per submission attempt: a double click or network retry cannot create two applications
  const idem = useRef<string>("");

  async function submit(selfie: Blob, frames: Blob[], challengeId: string | null, cams: string[], active: string) {
    setSubmitting(true); setErr("");
    idem.current ||= crypto.randomUUID();
    try {
      const fd = new FormData();
      const payload = {
        form: { ...form, id_number: form.id_number.replace(/\D/g, ""), pan: form.pan.toUpperCase().trim() },
        device: { device_id: await deviceId(), user_agent: navigator.userAgent, camera_labels: cams, active_camera: active || null },
        telemetry: tel.snapshot(), consent: { accepted: true, version: consentVersion, footprint }, challenge_id: challengeId, geo: await getGeo(),
      };
      fd.append("payload", JSON.stringify(payload));
      fd.append("card", card!);
      fd.append("selfie", selfie, "selfie.jpg");
      frames.forEach((f, i) => fd.append("frames", f, `frame${i}.jpg`));
      const { app_id } = await post<{ app_id: string }>("/api/apply", fd, { "Idempotency-Key": idem.current });
      router.push(`/kyc/progress/${app_id}`);
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 503 ? "Our checks are busy right now. Please try again in a few seconds." : String(e instanceof Error ? e.message : e));
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-[100dvh]">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <Logo />
        <span className="flex items-center gap-1.5 text-sm text-dim"><Lock className="size-3.5" />Secure connection</span>
      </header>
      <main className="mx-auto max-w-5xl px-6 pb-20">
        <ol className="mb-8 flex flex-wrap items-center gap-2">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span className={clsx("grid size-7 place-items-center rounded-full border text-xs font-semibold transition",
                i < step ? "border-brand bg-brand text-white" : i === step ? "border-brand text-brand" : "border-line-2 text-dim")}>
                {i < step ? <Check className="size-3.5" /> : i + 1}
              </span>
              <span className={clsx("text-sm", i === step ? "text-fg" : "text-dim")}>{s}</span>
              {i < STEPS.length - 1 && <ChevronRight className="size-4 text-dim" />}
            </li>
          ))}
        </ol>

        {demo && <DemoKit onPick={(f, c) => { setForm(f); setCard(c); }} />}

        <div className="fade-up" key={step}>
          {step === 0 && <Consent footprint={footprint} setFootprint={setFootprint} onNext={() => setStep(1)} />}
          {step === 1 && <Details form={form} setForm={setForm} tel={tel} onNext={() => setStep(2)} />}
          {step === 2 && <DocStep card={card} setCard={setCard} onBack={() => setStep(1)} onNext={() => setStep(3)} />}
          {step === 3 && <SelfieStep busy={submitting} onBack={() => setStep(2)} onDone={submit} />}
        </div>
        {err && <div className="panel mt-4 border-reject/40 p-4 text-sm text-reject">{err}</div>}
      </main>
    </div>
  );
}

function Consent({ footprint, setFootprint, onNext }: { footprint: boolean; setFootprint: (v: boolean) => void; onNext: () => void }) {
  const [ok, setOk] = useState(false);
  return (
    <div className="panel max-w-3xl p-8">
      <ShieldCheck className="size-8 text-brand" />
      <h1 className="display mt-4 text-[30px]">Verify your identity</h1>
      <p className="mt-2 text-muted">Takes about 2 minutes. We'll check your ID card, take a short selfie with a liveness challenge and confirm your details with the issuing registries.</p>
      <ul className="mt-6 space-y-3 text-sm text-muted">
        {["ID numbers are linked only through keyed hashes and shown masked (last 4 digits only).",
          "Your selfie and face-check frames are compared on our server with your card photo and the issuer's registry photo. Images are deleted after 30 days.",
          "We record how the form is filled (timing, not content) to detect bots and scripted fraud.",
          "With your permission we record your location and network at the time of the check, as digital KYC rules require.",
          "An AI assistant may summarise the result for a human reviewer. It never makes the decision."].map((t) => (
          <li key={t} className="flex gap-3"><Check className="mt-0.5 size-4 shrink-0 text-brand" />{t}</li>
        ))}
      </ul>
      <label className="mt-6 flex cursor-pointer items-center gap-3 text-sm">
        <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="size-4 accent-brand" />
        I consent to identity verification under the DPDP Act, 2023.
      </label>
      <label className="mt-3 flex cursor-pointer items-start gap-3 text-sm">
        <input type="checkbox" checked={footprint} onChange={(e) => setFootprint(e.target.checked)} className="mt-0.5 size-4 accent-brand" />
        <span>Optional: also check my email and mobile number&apos;s online history, and any account I link, against these details.
          <span className="block text-xs text-dim">Only contradictions are noted. Saying no, or having little online history, never counts against you.</span></span>
      </label>
      <button className="btn btn-primary mt-6" disabled={!ok} onClick={onNext}>Continue <ChevronRight className="size-4" /></button>
    </div>
  );
}

const FIELDS: { k: keyof Form; label: string; ph: string; span?: number; mono?: boolean }[] = [
  { k: "name", label: "Full name (as on ID)", ph: "Rahul Kumar", span: 2 },
  { k: "dob", label: "Date of birth", ph: "DD/MM/YYYY", mono: true },
  { k: "id_number", label: "National ID number", ph: "1234 5678 9012", mono: true },
  { k: "pan", label: "PAN", ph: "ABCPK1234Z", mono: true },
  { k: "phone", label: "Mobile", ph: "98XXXXXXXX", mono: true },
  { k: "email", label: "Email", ph: "you@example.com", span: 2 },
  { k: "address", label: "Address", ph: "House, street, city", span: 2 },
  { k: "pincode", label: "PIN code", ph: "403001", mono: true },
];

function Details({ form, setForm, tel, onNext }: { form: Form; setForm: (f: Form) => void; tel: Telemetry; onNext: () => void }) {
  const missing = [
    !form.name && "full name",
    !/^\d{2}\/\d{2}\/\d{4}$/.test(form.dob) && "date of birth as DD/MM/YYYY",
    form.id_number.replace(/\D/g, "").length !== 12 && "12-digit ID number",
    !form.phone && "mobile",
    !form.email && "email",
  ].filter(Boolean) as string[];
  const valid = missing.length === 0;
  return (
    <div className="panel p-8">
      <h2 className="display text-[22px]">Your details</h2>
      <p className="mt-1 text-sm text-muted">Enter them exactly as they appear on your ID card.</p>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {FIELDS.map(({ k, label, ph, span, mono }) => (
          <label key={k} className={clsx("block", span === 2 && "md:col-span-2")}>
            <span className="label">{label}</span>
            <input className={clsx("input mt-1.5", mono && "mono")} placeholder={ph} value={form[k]}
              onChange={(e) => setForm({ ...form, [k]: k === "dob" ? fmtDob(e.target.value) : e.target.value })} {...tel.bind(k)} />
          </label>
        ))}
        <label className="block">
          <span className="label">Gender</span>
          <select className="input mt-1.5" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })} {...tel.bind("gender")}>
            <option value="M">Male</option><option value="F">Female</option>
          </select>
        </label>
      </div>
      <div className="mt-6 flex items-center justify-between">
        <span className="text-xs text-dim">{valid ? "Typing rhythm and timing are captured silently for fraud detection. Field contents are not keylogged."
          : <span className="text-review">Still needed: {missing.join(", ")}</span>}</span>
        <button className="btn btn-primary" disabled={!valid} onClick={onNext}>Continue <ChevronRight className="size-4" /></button>
      </div>
    </div>
  );
}

/** Live GPS fix for the RBI V-CIP geo-tag; null if the browser has no geolocation or the user declines. */
async function getGeo(): Promise<Record<string, number | string> | null> {
  if (!navigator.geolocation) return null;
  return new Promise((res) => navigator.geolocation.getCurrentPosition(
    (g) => res({ lat: g.coords.latitude, lng: g.coords.longitude, accuracy: Math.round(g.coords.accuracy), ts: new Date().toISOString() }),
    () => res(null), { timeout: 2500, maximumAge: 60000 }));
}

/** 03082006 -> 03/08/2006 as the user types (keeps deletions natural). */
function fmtDob(v: string) {
  const d = v.replace(/\D/g, "").slice(0, 8);
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join("/");
}

function DocStep({ card, setCard, onBack, onNext }: { card: File | null; setCard: (f: File) => void; onBack: () => void; onNext: () => void }) {
  const url = useMemo(() => (card ? URL.createObjectURL(card) : ""), [card]);
  return (
    <div className="panel p-8">
      <h2 className="display text-[22px]">Upload your National ID card</h2>
      <p className="mt-2 text-sm text-muted">Front side, flat and fully visible. The signed QR code must be readable.</p>
      <label className={clsx("mt-6 grid cursor-pointer place-items-center overflow-hidden rounded-xl border border-dashed border-line-2 bg-bg-2/60 transition hover:border-brand",
        card ? "p-3" : "h-64")}>
        <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && setCard(e.target.files[0])} />
        {card ? <img src={url} alt="ID card" className="max-h-[360px] rounded-lg" /> :
          <div className="text-center text-muted"><Upload className="mx-auto size-8 text-dim" /><div className="mt-2 text-sm">Click to choose an image</div></div>}
      </label>
      <div className="mt-6 flex justify-between">
        <button className="btn" onClick={onBack}>Back</button>
        <button className="btn btn-primary" disabled={!card} onClick={onNext}>Continue <ChevronRight className="size-4" /></button>
      </div>
    </div>
  );
}

type LiveState = "idle" | "loading" | "ready" | "challenge" | "passed" | "failed";

function SelfieStep({ busy, onBack, onDone }: { busy: boolean; onBack: () => void; onDone: (selfie: Blob, frames: Blob[], challengeId: string | null, cams: string[], active: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<LiveState>("idle");
  const [chs, setChs] = useState<Challenge[]>([]);
  const [idx, setIdx] = useState(0);
  const [left, setLeft] = useState(8);
  const [hint, setHint] = useState("");
  const [cams, setCams] = useState<{ labels: string[]; active: string; virtual: boolean }>({ labels: [], active: "", virtual: false });
  const result = useRef<{ selfie?: Blob; frames: Blob[]; done: Challenge[]; id: string | null }>({ frames: [], done: [], id: null });
  const stream = useRef<MediaStream | null>(null);

  const stopCamera = () => stream.current?.getTracks().forEach((t) => t.stop());
  useEffect(() => stopCamera, []);

  async function start() {
    setState("loading");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      video.current!.srcObject = stream.current;
      await video.current!.play();
      setCams(await cameraLabels(stream.current));
      await getLandmarker();
      setState("ready");
    } catch (e) { setHint(`Camera unavailable: ${e}`); setState("idle"); }
  }

  async function run() {
    const lm = await getLandmarker();
    const v = video.current!;
    let ch: ServerChallenge;
    try { ch = await post<ServerChallenge>("/api/liveness/challenge"); } catch (e) { setHint(`Could not start the face check: ${e}`); return; }
    const list = ch.sequence;
    setChs(list); setIdx(0); setState("challenge");
    const neutral = await grabFrame(v);
    result.current = { frames: [neutral], done: [], id: ch.challenge_id };
    result.current.selfie = neutral;
    // capture a continuous burst through the whole challenge (~1 frame / 150ms): the server checks that the head
    // sweeps smoothly, so a few still photos can't stand in for a live turn. Capped under the server frame limit.
    let lastCap = 0;
    const capture = async (now: number) => {
      if (now - lastCap > 150 && result.current.frames.length < 34) { lastCap = now; result.current.frames.push(await grabFrame(v)); }
    };
    for (let i = 0; i < list.length; i++) {
      setIdx(i);
      const ok = await new Promise<boolean>((resolve) => {
        const t0 = performance.now();
        const tick = async () => {
          const el = (performance.now() - t0) / 1000;
          setLeft(Math.max(0, Math.ceil(8 - el)));
          if (el > 8) return resolve(false);
          const s = signal(lm.detectForVideo(v, performance.now()));
          setHint(s.faces === 0 ? "No face in frame" : s.faces > 1 ? "Only one person please" : "");
          await capture(performance.now());
          if (satisfied(list[i], s)) return resolve(true);
          requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
      if (!ok) { setState("failed"); return; }
      result.current.done.push(list[i]);
    }
    setState("passed");
    stopCamera();
  }

  /** Frames go to the server whatever happened here; the server alone decides if the turns were real. */
  function finish() {
    const r = result.current;
    stopCamera();
    onDone(r.selfie!, r.frames, r.id, cams.labels, cams.active);
  }

  async function uploadFallback(f: File) {
    stopCamera();
    onDone(f, [], null, [], "");
  }

  const current = chs[idx];
  return (
    <div className="grid gap-6 md:grid-cols-[1.3fr_1fr]">
      <div className="panel overflow-hidden p-3">
        <div className="relative aspect-[4/3] overflow-hidden rounded-lg bg-[#1b1e24]">
          <video ref={video} muted playsInline className="h-full w-full -scale-x-100 object-cover" />
          <div className="pointer-events-none absolute inset-0 grid place-items-center">
            <div className={clsx("h-[72%] aspect-[3/4] rounded-[50%] border-2 transition-colors",
              state === "passed" ? "border-approve" : state === "failed" ? "border-reject" : "border-white/40")} />
          </div>
          {state === "idle" && <div className="absolute inset-0 grid place-items-center"><button className="btn btn-primary" onClick={start}><Camera className="size-4" />Enable camera</button></div>}
          {state === "loading" && <div className="absolute inset-0 grid place-items-center text-sm text-muted">Loading face model…</div>}
          {state === "challenge" && current && (
            <div className="absolute inset-x-0 bottom-0 bg-black/70 px-5 py-4 text-white">
              <div className="text-sm text-white/80">Step {idx + 1} of {chs.length}, {left} seconds left</div>
              <div className="mt-1 text-xl font-semibold">{CHALLENGE_TEXT[current]}</div>
              {hint && <div className="mt-1 text-sm text-review">{hint}</div>}
            </div>
          )}
        </div>
      </div>
      <div className="panel flex flex-col p-6">
        <h2 className="display text-[22px]">Face check</h2>
        <p className="mt-2 text-sm text-muted">Turn your head left and right in the order shown, 8 seconds per step. The order is chosen by our server for this session, and the frames are checked there.</p>
        <div className="mt-5 space-y-2 text-sm">
          <Row ok={state !== "idle" && state !== "loading"} text="Camera on" />
          <Row ok={state !== "idle" && state !== "loading" ? !cams.virtual : null} text={cams.virtual ? `Virtual camera streaming: ${cams.active}` : "Physical camera (no injection tool)"} bad={cams.virtual} />
          {chs.map((c, i) => <Row key={c} ok={result.current.done.includes(c) ? true : state === "failed" && i === idx ? false : null} text={CHALLENGE_TEXT[c]} bad={state === "failed" && i === idx} />)}
        </div>
        <div className="mt-auto pt-6">
          {state === "ready" && <button className="btn btn-primary w-full" onClick={run}><Sparkles className="size-4" />Start liveness check</button>}
          {state === "passed" && <button className="btn btn-primary w-full" disabled={busy} onClick={finish}>{busy ? "Submitting…" : <>Submit application <ChevronRight className="size-4" /></>}</button>}
          {state === "failed" && <div className="space-y-2">
            <button className="btn w-full" onClick={run}>Try again</button>
            <button className="btn btn-danger w-full" disabled={busy} onClick={finish}>Submit anyway</button>
          </div>}
          <div className="mt-4 flex items-center justify-between">
            <button className="btn" onClick={onBack}>Back</button>
            <label className="cursor-pointer text-xs text-dim underline-offset-2 hover:underline">
              <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadFallback(e.target.files[0])} />
              No camera? Upload a selfie (a person will review it)
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ ok, text, bad }: { ok: boolean | null; text: string; bad?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className={clsx("grid size-5 place-items-center rounded-full border", ok ? "border-approve bg-approve/15 text-approve" : bad ? "border-reject text-reject" : "border-line-2 text-dim")}>
        {ok ? <Check className="size-3" /> : bad ? "!" : ""}
      </span>
      <span className={bad ? "text-reject" : ok ? "text-fg" : "text-muted"}>{text}</span>
    </div>
  );
}

/** Presenter kit (?demo=1): enrol your face, get 3 scenario cards + a cheat sheet to type from. */
function DemoKit({ onPick }: { onPick: (f: Form, card: File) => void }) {
  const [kit, setKit] = useState<Record<string, { card: string; form: Form; note?: string }> | null>(null);
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState<string | null>(null);
  // the kit enrols a registry identity, so keep it across runs instead of re-enrolling every time
  useEffect(() => {
    try { const k = localStorage.getItem("trueid-demo-kit"); if (k) setKit(JSON.parse(k)); } catch {}
  }, []);
  async function build(photo: File) {
    setBusy(true);
    const fd = new FormData(); fd.append("photo", photo);
    try {
      const k = await post("/api/demo/kit", fd);
      setKit(k);
      try { localStorage.setItem("trueid-demo-kit", JSON.stringify(k)); } catch {}
    } catch (e) {
      setKit({ error: e instanceof ApiError && e.status === 401 ? "Sign in to the analyst console in this browser first." : String(e) } as any);
    } finally { setBusy(false); }
  }
  async function pick(k: string, autofill: boolean) {
    const s = kit![k];
    const blob = await (await fetch(fileUrl(s.card))).blob();
    const file = new File([blob], `${k}.jpg`, { type: "image/jpeg" });
    onPick(autofill ? s.form : { ...EMPTY, gender: s.form.gender }, file);
    setShown(k);
  }
  return (
    <div className="panel mb-6 border-sim/30 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Wand2 className="size-4 text-sim" /><span className="font-semibold">Presenter kit</span>
        <span className="text-xs text-muted">Enrol your face as a registry citizen → get a genuine card, a Poisson-edited DOB card, and a Frankenstein card.</span>
        <label className="btn ml-auto cursor-pointer">
          <input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && build(e.target.files[0])} />
          {busy ? "Building…" : kit ? "Rebuild" : "Upload presenter photo"}
        </label>
      </div>
      {kit && !("error" in kit) && (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {Object.entries(kit).map(([k, s]) => (
            <div key={k} className={clsx("rounded-xl border p-3", shown === k ? "border-sim" : "border-line")}>
              <img src={fileUrl(s.card)} alt={k} className="rounded-md" />
              <div className="mt-2 text-sm font-semibold capitalize">{k.replaceAll("_", " ")}</div>
              {s.note && <div className="text-xs text-muted">{s.note}</div>}
              <div className="mono mt-2 space-y-0.5 text-[11px] text-dim">
                {Object.entries(s.form).map(([fk, fv]) => <div key={fk}><span className="text-muted">{fk}:</span> {fv}</div>)}
              </div>
              <div className="mt-3 flex gap-2">
                <button className="btn flex-1 py-1.5 text-xs" onClick={() => pick(k, false)}>Use card (type form)</button>
                <button className="btn py-1.5 text-xs" title="Autofill skips typing, so behaviour checks will flag it" onClick={() => pick(k, true)}>Autofill</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {kit && "error" in kit && <div className="mt-3 text-sm text-reject">{String((kit as any).error)}</div>}
    </div>
  );
}
