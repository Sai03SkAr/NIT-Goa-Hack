"use client";
/** PayLite onboarding, minimum KYC. Deliberate gaps, mirroring real min-KYC wallets:
 *  - only the mobile number is verified (OTP); name, DOB, ID number and PAN are self-declared and never checked
 *  - the ID card and the selfie are plain file uploads (gallery allowed), so edited or AI-made images get in
 *  - no liveness, no email verification, no DigiLocker, no signature
 * TrueID Shield's signals SDK (telemetry + device id) is the one thing PayLite added, so behaviour still reaches TrueID. */
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { ArrowLeft, ImagePlus, Loader2, MessageSquareText } from "lucide-react";
import { Logo } from "@/components/Brand";
import { deviceId } from "@/lib/device";
import { Telemetry } from "@/lib/telemetry";

type Form = { name: string; dob: string; gender: string; id_number: string; pan: string; email: string; pincode: string };
const EMPTY: Form = { name: "", dob: "", gender: "", id_number: "", pan: "", email: "", pincode: "" };
const TITLES = ["Your number", "About you", "Your ID and photo"];

export default function Start() {
  const router = useRouter();
  const tel = useMemo(() => new Telemetry(), []);
  useEffect(() => { tel.attach(); return () => tel.detach(); }, [tel]);
  const [step, setStep] = useState(0);
  const [phone, setPhone] = useState("");
  const [form, setForm] = useState<Form>(EMPTY);
  const [card, setCard] = useState<File | null>(null);
  const [selfie, setSelfie] = useState<File | null>(null);

  async function submit() {
    const fd = new FormData();
    fd.append("payload", JSON.stringify({
      form: { ...form, id_number: form.id_number.replace(/\s/g, ""), phone, address: "" },
      device: { device_id: await deviceId(), user_agent: navigator.userAgent, camera_labels: [] },
      telemetry: tel.snapshot(),
      liveness: { performed: false },
      capture: { card: "gallery_upload", selfie: "gallery_upload" },
      partner_checks: { mobile_otp: true },
    }));
    fd.append("card", card!, "card.jpg");
    fd.append("selfie", selfie!, "selfie.jpg");
    const r = await fetch("/api/kyc/submit", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error ?? "Something went wrong. Try again.");
    router.push(`/start/done/${j.id}?ref=${j.reference}`);
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-[440px] flex-col px-5 pb-8 pt-5">
      <header className="flex items-center justify-between">
        {step > 0 ? (
          <button aria-label="Back" className="grid size-10 place-items-center rounded-full bg-surface" onClick={() => setStep(step - 1)}>
            <ArrowLeft className="size-5" />
          </button>
        ) : <Logo />}
        <div className="flex items-center gap-1.5" aria-label={`Step ${step + 1} of 3`}>
          {TITLES.map((t, i) => <span key={t} className={clsx("h-1.5 rounded-full transition-all", i === step ? "w-7 bg-plum" : i < step ? "w-3 bg-plum/60" : "w-3 bg-line")} />)}
        </div>
      </header>
      <main className="mt-8 flex flex-1 flex-col">
        {step === 0 && <PhoneStep phone={phone} setPhone={setPhone} tel={tel} onDone={() => setStep(1)} />}
        {step === 1 && <AboutStep form={form} setForm={setForm} tel={tel} onDone={() => setStep(2)} />}
        {step === 2 && <DocsStep card={card} setCard={setCard} selfie={selfie} setSelfie={setSelfie} onSubmit={submit} />}
      </main>
    </div>
  );
}

function Title({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-7">
      <h1 className="text-[2rem] font-bold leading-[1.05] tracking-[-0.03em]">{children}</h1>
      {sub && <p className="mt-2 text-muted">{sub}</p>}
    </div>
  );
}

function Bottom({ children }: { children: React.ReactNode }) {
  return <div className="sticky bottom-0 mt-auto bg-gradient-to-t from-paper from-70% to-transparent pt-6">{children}</div>;
}

function PhoneStep({ phone, setPhone, tel, onDone }: { phone: string; setPhone: (v: string) => void; tel: Telemetry; onDone: () => void }) {
  const [sent, setSent] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const ok = /^[6-9]\d{9}$/.test(phone);
  return (
    <form className="flex flex-1 flex-col" onSubmit={(e) => {
      e.preventDefault();
      if (!sent) { setSent(String(Math.floor(100000 + Math.random() * 900000))); return; }
      if (code === sent) onDone(); else setErr("Wrong code. Check the SMS and try again.");
    }}>
      <Title sub="We'll text you a code to confirm it's yours.">What&apos;s your mobile number?</Title>
      <label className="field">
        <span className="sr-only">Mobile number</span>
        <div className="flex items-center gap-2 rounded-[14px] border-[1.5px] border-line bg-surface px-4 focus-within:border-plum">
          <span className="text-lg text-muted">+91</span>
          <input className="w-full bg-transparent py-3.5 text-xl tracking-wide tabular-nums outline-none" inputMode="numeric" autoComplete="tel-national" autoFocus
            maxLength={10} value={phone} readOnly={!!sent} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="98765 43210" {...tel.bind("phone")} />
        </div>
      </label>
      {sent && (
        <>
          <div role="status" className="mt-4 flex gap-3 rounded-2xl bg-mist px-4 py-3 text-sm">
            <MessageSquareText className="mt-0.5 size-4 shrink-0 text-plum" />
            <span>Demo SMS: <b className="tabular-nums tracking-wider">{sent}</b> is your PayLite code.</span>
          </div>
          <label className="field mt-5">
            <span className="field-label">Enter the code</span>
            <input className="input text-center text-2xl tracking-[0.5em] tabular-nums" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              value={code} onChange={(e) => { setCode(e.target.value.replace(/\D/g, "")); setErr(""); }} />
          </label>
        </>
      )}
      {err && <p role="alert" className="error mt-3">{err}</p>}
      <Bottom>
        <button className="btn btn-primary w-full" disabled={sent ? code.length !== 6 : !ok}>{sent ? "Verify" : "Send code"}</button>
      </Bottom>
    </form>
  );
}

function AboutStep({ form, setForm, tel, onDone }: { form: Form; setForm: (f: Form) => void; tel: Telemetry; onDone: () => void }) {
  const set = (k: keyof Form, v: string) => setForm({ ...form, [k]: v });
  const valid = form.name.trim().split(/\s+/).length >= 2 && /^\d{2}\/\d{2}\/\d{4}$/.test(form.dob) && !!form.gender
    && form.id_number.replace(/\s/g, "").length === 12 && (!form.pan || /^[A-Z]{5}\d{4}[A-Z]$/.test(form.pan))
    && /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(form.email);
  return (
    <form className="flex flex-1 flex-col" onSubmit={(e) => { e.preventDefault(); if (valid) onDone(); }}>
      <Title sub="Enter them exactly as they appear on your ID card.">Tell us about you</Title>
      <div className="space-y-4">
        <label className="field">
          <span className="field-label">Full name</span>
          <input className="input" autoComplete="name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Riya Kamat" {...tel.bind("name")} />
        </label>
        <div className="grid grid-cols-[1fr_auto] gap-3">
          <label className="field">
            <span className="field-label">Date of birth</span>
            <input className="input tabular-nums" inputMode="numeric" maxLength={10} value={form.dob} placeholder="DD/MM/YYYY" {...tel.bind("dob")}
              onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 8); set("dob", [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join("/")); }} />
          </label>
          <fieldset>
            <legend className="field-label">Gender</legend>
            <div className="flex gap-1.5">
              {[["F", "F"], ["M", "M"], ["O", "Other"]].map(([v, l]) => (
                <button type="button" key={v} aria-pressed={form.gender === v} onClick={() => set("gender", v)}
                  className={clsx("h-[3.2rem] min-w-12 rounded-[14px] border-[1.5px] px-3 font-semibold",
                    form.gender === v ? "border-plum bg-plum text-white" : "border-line bg-surface")}>{l}</button>
              ))}
            </div>
          </fieldset>
        </div>
        <label className="field">
          <span className="field-label">National ID number</span>
          <input className="input tabular-nums tracking-wider" inputMode="numeric" maxLength={14} value={form.id_number} placeholder="1234 5678 9012" {...tel.bind("id_number")}
            onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 12); set("id_number", d.replace(/(\d{4})(?=\d)/g, "$1 ")); }} />
        </label>
        <label className="field">
          <span className="field-label">PAN <span className="font-normal text-muted">(optional)</span></span>
          <input className="input uppercase tracking-wider" maxLength={10} value={form.pan} placeholder="ABCPK1234Z" {...tel.bind("pan")}
            onChange={(e) => set("pan", e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} />
        </label>
        <label className="field">
          <span className="field-label">Email</span>
          <input className="input" type="email" autoComplete="email" value={form.email} onChange={(e) => set("email", e.target.value.trim())}
            placeholder="you@example.com" {...tel.bind("email")} />
          <span className="field-hint">For receipts. We won&apos;t send a verification link.</span>
        </label>
      </div>
      <Bottom><button className="btn btn-primary w-full" disabled={!valid}>Continue</button></Bottom>
    </form>
  );
}

function Upload({ label, hint, file, setFile, round }: { label: string; hint: string; file: File | null; setFile: (f: File) => void; round?: boolean }) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  return (
    <label className="flex cursor-pointer items-center gap-4 rounded-2xl border-[1.5px] border-dashed border-line bg-surface p-4 hover:border-plum focus-within:border-plum">
      <span className={clsx("grid size-16 shrink-0 place-items-center overflow-hidden bg-mist text-plum", round ? "rounded-full" : "rounded-xl")}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {url ? <img src={url} alt="" className="h-full w-full object-cover" /> : <ImagePlus className="size-6" />}
      </span>
      <span className="min-w-0">
        <span className="block font-semibold">{label}</span>
        <span className="block truncate text-sm text-muted">{file ? file.name : hint}</span>
      </span>
      <input type="file" accept="image/*" className="sr-only" onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])} />
    </label>
  );
}

function DocsStep({ card, setCard, selfie, setSelfie, onSubmit }: {
  card: File | null; setCard: (f: File) => void; selfie: File | null; setSelfie: (f: File) => void; onSubmit: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [agree, setAgree] = useState(false);
  const [err, setErr] = useState("");
  return (
    <form className="flex flex-1 flex-col" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setErr("");
      try { await onSubmit(); } catch (x) { setErr(x instanceof Error ? x.message : "Something went wrong."); setBusy(false); }
    }}>
      <Title sub="A clear photo of the front of your ID card, and a photo of your face.">Add your ID and a photo</Title>
      <div className="space-y-3">
        <Upload label="ID card, front" hint="Take a photo or choose from your gallery" file={card} setFile={setCard} />
        <Upload label="Your photo" hint="Face the camera, no sunglasses" file={selfie} setFile={setSelfie} round />
      </div>
      <label className="mt-6 flex cursor-pointer items-start gap-3 text-sm text-muted">
        <input type="checkbox" className="mt-0.5 size-4 accent-[var(--color-plum)]" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
        <span>I agree to PayLite&apos;s terms and to my details being checked by a fraud-screening partner.</span>
      </label>
      {err && <p role="alert" className="error mt-3">{err}</p>}
      <Bottom>
        <button className="btn btn-primary w-full" disabled={!card || !selfie || !agree || busy}>
          {busy && <Loader2 className="size-4 animate-spin" />}Create my wallet
        </button>
      </Bottom>
    </form>
  );
}
