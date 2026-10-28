"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { Check, Loader2, Lock, ShieldCheck } from "lucide-react";
import { Header } from "@/components/Brand";
import { DemoSms, OtpInput, useOtp } from "@/components/Otp";
import { DocCapture } from "@/components/DocCapture";
import { LiveSelfie, type LiveResult } from "@/components/LiveSelfie";
import { SignaturePad } from "@/components/SignaturePad";
import { deviceId } from "@/lib/device";
import { Telemetry } from "@/lib/telemetry";

const STEPS = [
  { key: "mobile", title: "Mobile number" },
  { key: "email", title: "Email address" },
  { key: "pan", title: "PAN" },
  { key: "digilocker", title: "National ID via DigiLocker" },
  { key: "details", title: "Address and occupation" },
  { key: "document", title: "Photo of your ID card" },
  { key: "selfie", title: "Live selfie" },
  { key: "signature", title: "Signature" },
  { key: "esign", title: "Review and eSign" },
] as const;

type Identity = { name: string; dob: string; gender: string; id_number: string };

const mask = {
  phone: (p: string) => `+91 ${p.slice(0, 2)}••••${p.slice(-4)}`,
  email: (e: string) => e.replace(/^(.)(.*)(@.*)$/, (_, a, b, c) => a + "•".repeat(Math.min(6, b.length)) + c),
  pan: (p: string) => `${p.slice(0, 2)}•••••${p.slice(-3)}`,
  id: (i: string) => `•••• •••• ${i.slice(-4)}`,
};

export default function Onboard() {
  const router = useRouter();
  const tel = useMemo(() => new Telemetry(), []);
  useEffect(() => { tel.attach(); return () => tel.detach(); }, [tel]);

  const [step, setStep] = useState(0);
  const [record, setRecord] = useState<Record<string, string>>({});
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [pan, setPan] = useState("");
  const [panInfo, setPanInfo] = useState<{ name: string; id_last4: string } | null>(null);
  const [dob, setDob] = useState("");
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [details, setDetails] = useState({ address: "", pincode: "", occupation: "Salaried", income: "5–10 lakh" });
  const [card, setCard] = useState<{ blob: Blob; source: string } | null>(null);
  const [live, setLive] = useState<LiveResult | null>(null);
  const [geo, setGeo] = useState<{ lat: number; lon: number } | "denied" | null>(null);
  const [signed, setSigned] = useState(false);

  const complete = (key: string, note: string) => {
    setRecord((r) => ({ ...r, [key]: note }));
    setStep((s) => s + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const back = () => setStep((s) => Math.max(0, s - 1));

  async function submit(esignOk: boolean) {
    const form = { ...identity!, pan, phone, email, address: details.address, pincode: details.pincode };
    const payload = {
      form,
      extra: { occupation: details.occupation, annual_income: details.income },
      device: { device_id: await deviceId(), user_agent: navigator.userAgent, camera_labels: live!.cameras.labels,
        active_camera: live!.cameras.active, geo: typeof geo === "object" ? geo : null },
      telemetry: tel.snapshot(),
      liveness: live!.liveness,
      capture: { card: card!.source, selfie: "live_camera" },
      partner_checks: { mobile_otp: true, email_otp: true, pan_nsdl: true, digilocker_identity: true,
        live_selfie: true, signature: signed, esign_otp: esignOk, geolocation: typeof geo === "object" && geo !== null },
    };
    const fd = new FormData();
    fd.append("payload", JSON.stringify(payload));
    fd.append("card", card!.blob, "card.jpg");
    fd.append("selfie", live!.selfie, "selfie.jpg");
    live!.frames.forEach((f, i) => fd.append("frames", f, `frame${i}.jpg`));
    const r = await fetch("/api/kyc/submit", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error ?? "Submission failed");
    router.push(`/onboard/done/${j.id}?ref=${j.reference}`);
  }

  const current = STEPS[step];
  return (
    <>
      <Header right={<span className="inline-flex items-center gap-1.5"><Lock className="size-3.5" />Secure session</span>} />
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 md:py-12">
        <div className="mb-6 md:hidden">
          <div className="flex justify-between text-sm text-muted"><span>Step {step + 1} of {STEPS.length}</span><span>{current.title}</span></div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-spruce transition-[width]" style={{ width: `${((step + 1) / STEPS.length) * 100}%` }} />
          </div>
        </div>
        <div className="grid gap-8 md:grid-cols-[17rem_1fr] lg:gap-12">
          <VerificationRecord step={step} record={record} />
          <main className="card step-enter min-w-0 p-6 sm:p-8" key={step}>
            {current.key === "mobile" && <MobileStep phone={phone} setPhone={setPhone} tel={tel} onDone={() => complete("mobile", mask.phone(phone))} />}
            {current.key === "email" && <EmailStep email={email} setEmail={setEmail} tel={tel} onBack={back} onDone={() => complete("email", mask.email(email))} />}
            {current.key === "pan" && (
              <PanStep pan={pan} setPan={setPan} dob={dob} setDob={setDob} tel={tel} onBack={back}
                onDone={(info) => { setPanInfo(info); complete("pan", `${mask.pan(pan)}, ${info.name}`); }} />
            )}
            {current.key === "digilocker" && (
              <DigiLockerStep panInfo={panInfo!} tel={tel} onBack={back}
                onDone={(id) => { setIdentity(id); complete("digilocker", `${id.name}, ${mask.id(id.id_number)}`); }} />
            )}
            {current.key === "details" && (
              <DetailsStep identity={identity!} details={details} setDetails={setDetails} tel={tel} onBack={back}
                onDone={() => complete("details", `${details.occupation}, PIN ${details.pincode}`)} />
            )}
            {current.key === "document" && (
              <StepFrame title="Photograph your ID card" lead="Place the front of your national ID card inside the frame, flat and without glare. We read the printed details and the secure QR code."
                onBack={back} canNext={!!card} onNext={() => complete("document", card!.source === "camera" ? "Captured live" : "e-ID file from DigiLocker")}>
                <DocCapture onCapture={(b, s) => setCard(b && s ? { blob: b, source: s } : null)} />
              </StepFrame>
            )}
            {current.key === "selfie" && (
              <StepFrame title="Take a live selfie" lead="RBI rules ask us to confirm you're present in person. We'll also ask for your location, since accounts can only be opened from India."
                onBack={back} canNext={!!live}
                onNext={() => complete("selfie", `Liveness passed${typeof geo === "object" && geo ? ", location shared" : ""}`)}>
                <LiveSelfie onResult={(r) => {
                  setLive(r);
                  if (r && geo === null) navigator.geolocation?.getCurrentPosition(
                    (p) => setGeo({ lat: +p.coords.latitude.toFixed(3), lon: +p.coords.longitude.toFixed(3) }),
                    () => setGeo("denied"), { timeout: 8000 });
                }} />
              </StepFrame>
            )}
            {current.key === "signature" && (
              <StepFrame title="Add your signature" lead="Sign the way you'd sign a cheque. It's printed on your account opening form and used to verify cheques."
                onBack={back} canNext={signed} onNext={() => complete("signature", "Captured")}>
                <SignaturePad onChange={setSigned} />
              </StepFrame>
            )}
            {current.key === "esign" && (
              <EsignStep phone={phone} identity={identity!} pan={pan} email={email} details={details} onBack={back} onSubmit={submit} />
            )}
          </main>
        </div>
      </div>
    </>
  );
}

function VerificationRecord({ step, record }: { step: number; record: Record<string, string> }) {
  return (
    <aside className="hidden md:block">
      <div className="sticky top-8">
        <h2 className="text-sm font-semibold">Your verification record</h2>
        <p className="mt-1 text-sm text-muted">Each item is checked before you move on.</p>
        <ol className="relative mt-6 space-y-0">
          {STEPS.map((s, i) => {
            const done = i < step, now = i === step;
            return (
              <li key={s.key} className="relative flex gap-3 pb-5 last:pb-0">
                {i < STEPS.length - 1 && <span className={clsx("absolute left-[11px] top-7 h-[calc(100%-1.75rem+2px)] w-px", done ? "bg-spruce" : "bg-line")} />}
                <span className={clsx("relative z-10 grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold tabular-nums",
                  done ? "border-spruce bg-spruce text-white" : now ? "border-spruce bg-surface text-spruce" : "border-line bg-paper text-faint")}>
                  {done ? <Check className="size-3.5" /> : i + 1}
                </span>
                <div className="min-w-0 pt-0.5">
                  <div className={clsx("text-sm", now ? "font-semibold" : done ? "font-medium" : "text-faint")}>{s.title}</div>
                  {done && record[s.key] && <div className="truncate text-xs text-muted">{record[s.key]}</div>}
                </div>
              </li>
            );
          })}
        </ol>
        <div className="mt-8 flex items-start gap-2 border-t border-line pt-4 text-xs text-muted">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-spruce" />
          <span>Fraud screening by TrueID Shield. Your data is used only to open this account.</span>
        </div>
      </div>
    </aside>
  );
}

function StepFrame({ title, lead, children, onBack, onNext, canNext, busy, nextLabel = "Continue", error }: {
  title: string; lead?: string; children: React.ReactNode; onBack?: () => void; onNext: () => void;
  canNext: boolean; busy?: boolean; nextLabel?: string; error?: string;
}) {
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (canNext && !busy) onNext(); }}>
      <h1 className="text-2xl font-semibold tracking-[-0.02em] sm:text-[1.75rem]">{title}</h1>
      {lead && <p className="mt-2 max-w-[62ch] text-muted">{lead}</p>}
      <div className="mt-7">{children}</div>
      {error && <p role="alert" className="error mt-4">{error}</p>}
      <div className="mt-8 flex items-center justify-between gap-3 border-t border-line pt-6">
        {onBack ? <button type="button" className="btn" onClick={onBack}>Back</button> : <span />}
        <button type="submit" className="btn btn-primary min-w-36" disabled={!canNext || busy}>
          {busy && <Loader2 className="size-4 animate-spin" />}{nextLabel}
        </button>
      </div>
    </form>
  );
}

type TelProps = { tel: Telemetry };

function MobileStep({ phone, setPhone, tel, onDone }: { phone: string; setPhone: (v: string) => void; onDone: () => void } & TelProps) {
  const otp = useOtp();
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const valid = /^[6-9]\d{9}$/.test(phone);
  return (
    <StepFrame title="Start with your mobile number" lead="Use the number linked to your national ID. You'll need it again for DigiLocker and eSign."
      canNext={otp.sent ? code.length === 6 : valid} nextLabel={otp.sent ? "Verify" : "Send code"} error={err}
      onNext={() => {
        if (!otp.sent) { otp.send(); return; }
        if (otp.check(code)) onDone(); else setErr("That code doesn't match. Check the message and try again.");
      }}>
      <label className="field max-w-sm">
        <span className="field-label">Mobile number</span>
        <div className="flex">
          <span className="grid place-items-center rounded-l-[10px] border border-r-0 border-line bg-mist px-3 text-muted">+91</span>
          <input className="input mono rounded-l-none" inputMode="numeric" autoComplete="tel-national" maxLength={10} value={phone}
            readOnly={otp.sent} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="98XXXXXXXX" {...tel.bind("phone")} />
        </div>
      </label>
      {otp.sent && <><DemoSms code={otp.code} to={mask.phone(phone)} /><OtpInput value={code} onChange={(v) => { setCode(v); setErr(""); }} /></>}
    </StepFrame>
  );
}

function EmailStep({ email, setEmail, tel, onBack, onDone }: { email: string; setEmail: (v: string) => void; onBack: () => void; onDone: () => void } & TelProps) {
  const otp = useOtp();
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  const valid = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email);
  return (
    <StepFrame title="Verify your email" lead="Statements and account alerts go here." onBack={onBack}
      canNext={otp.sent ? code.length === 6 : valid} nextLabel={otp.sent ? "Verify" : "Send code"} error={err}
      onNext={() => {
        if (!otp.sent) { otp.send(); return; }
        if (otp.check(code)) onDone(); else setErr("That code doesn't match. Check the email and try again.");
      }}>
      <label className="field max-w-md">
        <span className="field-label">Email address</span>
        <input className="input" type="email" autoComplete="email" value={email} readOnly={otp.sent}
          onChange={(e) => setEmail(e.target.value.trim())} placeholder="you@example.com" {...tel.bind("email")} />
      </label>
      {otp.sent && <><DemoSms code={otp.code} to={mask.email(email)} /><OtpInput value={code} onChange={(v) => { setCode(v); setErr(""); }} /></>}
    </StepFrame>
  );
}

function PanStep({ pan, setPan, dob, setDob, tel, onBack, onDone }: {
  pan: string; setPan: (v: string) => void; dob: string; setDob: (v: string) => void; onBack: () => void;
  onDone: (info: { name: string; id_last4: string }) => void;
} & TelProps) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dobOk = /^\d{2}\/\d{2}\/\d{4}$/.test(dob);
  return (
    <StepFrame title="Enter your PAN" lead="We check it with the Income Tax Department. Your PAN and date of birth must match their records."
      onBack={onBack} canNext={pan.length === 10 && dobOk} busy={busy} nextLabel="Verify PAN" error={err}
      onNext={async () => {
        setBusy(true); setErr("");
        try {
          const r = await (await fetch("/api/verify/pan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pan, dob }) })).json();
          if (r.ok) onDone({ name: r.name, id_last4: r.id_last4 }); else setErr(r.error);
        } catch { setErr("PAN verification is unavailable right now. Try again in a minute."); }
        finally { setBusy(false); }
      }}>
      <div className="grid max-w-lg gap-5 sm:grid-cols-2">
        <label className="field">
          <span className="field-label">PAN</span>
          <input className="input mono uppercase" maxLength={10} autoCapitalize="characters" value={pan}
            onChange={(e) => setPan(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} placeholder="ABCPK1234Z" {...tel.bind("pan")} />
        </label>
        <label className="field">
          <span className="field-label">Date of birth</span>
          <input className="input mono" inputMode="numeric" maxLength={10} value={dob} placeholder="DD/MM/YYYY" {...tel.bind("dob")}
            onChange={(e) => {
              const d = e.target.value.replace(/\D/g, "").slice(0, 8);
              setDob([d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join("/"));
            }} />
        </label>
      </div>
    </StepFrame>
  );
}

function DigiLockerStep({ panInfo, tel, onBack, onDone }: { panInfo: { name: string; id_last4: string }; onBack: () => void; onDone: (id: Identity) => void } & TelProps) {
  const otp = useOtp();
  const [idn, setIdn] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fetched, setFetched] = useState<Identity | null>(null);
  const digits = idn.replace(/\s/g, "");

  if (fetched) {
    return (
      <StepFrame title="Details fetched from DigiLocker" lead="These come straight from the issuer, so you can't edit them here. If something is wrong, update it with the issuer first."
        onBack={onBack} canNext onNext={() => onDone(fetched)} nextLabel="These are correct">
        <dl className="grid max-w-lg gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
          {[["Name", fetched.name], ["Date of birth", fetched.dob], ["Gender", fetched.gender === "F" ? "Female" : fetched.gender === "M" ? "Male" : fetched.gender],
            ["National ID", mask.id(fetched.id_number)]].map(([k, v]) => (
            <div key={k} className="bg-surface px-4 py-3"><dt className="text-xs text-muted">{k}</dt><dd className="mt-0.5 font-medium">{v}</dd></div>
          ))}
        </dl>
      </StepFrame>
    );
  }
  return (
    <StepFrame title="Fetch your national ID from DigiLocker" lead={`We'll fetch your name, date of birth and gender from the issuer. The ID must be the one linked to your PAN (ending ${panInfo.id_last4}).`}
      onBack={onBack} busy={busy} error={err}
      canNext={otp.sent ? code.length === 6 : digits.length === 12} nextLabel={otp.sent ? "Fetch details" : "Send OTP"}
      onNext={async () => {
        if (!otp.sent) { otp.send(); return; }
        if (!otp.check(code)) { setErr("That OTP doesn't match."); return; }
        setBusy(true); setErr("");
        try {
          const r = await (await fetch("/api/verify/digilocker", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_number: digits, otp: code, pan_name: panInfo.name, pan_last4: panInfo.id_last4 }) })).json();
          if (r.ok) setFetched(r); else setErr(r.error);
        } catch { setErr("DigiLocker is unavailable right now. Try again in a minute."); }
        finally { setBusy(false); }
      }}>
      <label className="field max-w-sm">
        <span className="field-label">National ID number</span>
        <input className="input mono" inputMode="numeric" maxLength={14} value={idn} readOnly={otp.sent} placeholder="1234 5678 9012" {...tel.bind("id_number")}
          onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 12); setIdn(d.replace(/(\d{4})(?=\d)/g, "$1 ")); }} />
        <span className="field-hint">DigiLocker sends an OTP to the mobile linked to this ID.</span>
      </label>
      {otp.sent && <><DemoSms code={otp.code} to="your ID-linked mobile" /><OtpInput value={code} onChange={(v) => { setCode(v); setErr(""); }} label="DigiLocker OTP" /></>}
    </StepFrame>
  );
}

function DetailsStep({ identity, details, setDetails, tel, onBack, onDone }: {
  identity: Identity; details: { address: string; pincode: string; occupation: string; income: string };
  setDetails: (d: { address: string; pincode: string; occupation: string; income: string }) => void; onBack: () => void; onDone: () => void;
} & TelProps) {
  const set = (k: keyof typeof details) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setDetails({ ...details, [k]: e.target.value });
  return (
    <StepFrame title={`A few more details, ${identity.name.split(" ")[0]}`} lead="Banks are required to record your address and occupation."
      onBack={onBack} onNext={onDone} canNext={details.address.trim().length > 8 && /^\d{6}$/.test(details.pincode)}>
      <div className="grid max-w-xl gap-5 sm:grid-cols-2">
        <label className="field sm:col-span-2">
          <span className="field-label">Current address</span>
          <textarea className="input min-h-24" value={details.address} onChange={set("address")} autoComplete="street-address"
            placeholder="House, street, area, city" {...tel.bind("address")} />
        </label>
        <label className="field">
          <span className="field-label">PIN code</span>
          <input className="input mono" inputMode="numeric" maxLength={6} value={details.pincode} autoComplete="postal-code"
            onChange={(e) => setDetails({ ...details, pincode: e.target.value.replace(/\D/g, "") })} placeholder="403001" {...tel.bind("pincode")} />
        </label>
        <label className="field">
          <span className="field-label">Occupation</span>
          <select className="input" value={details.occupation} onChange={set("occupation")}>
            {["Salaried", "Self-employed", "Business owner", "Student", "Homemaker", "Retired"].map((o) => <option key={o}>{o}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="field-label">Annual income</span>
          <select className="input" value={details.income} onChange={set("income")}>
            {["Below 1 lakh", "1–5 lakh", "5–10 lakh", "10–25 lakh", "Above 25 lakh"].map((o) => <option key={o}>{o}</option>)}
          </select>
        </label>
      </div>
    </StepFrame>
  );
}

function EsignStep({ phone, identity, pan, email, details, onBack, onSubmit }: {
  phone: string; identity: Identity; pan: string; email: string; details: { address: string; pincode: string; occupation: string };
  onBack: () => void; onSubmit: (esignOk: boolean) => Promise<void>;
}) {
  const otp = useOtp();
  const [code, setCode] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const rows: [string, string][] = [["Name", identity.name], ["Date of birth", identity.dob], ["National ID", mask.id(identity.id_number)],
    ["PAN", mask.pan(pan)], ["Mobile", mask.phone(phone)], ["Email", email], ["Address", `${details.address}, ${details.pincode}`], ["Occupation", details.occupation]];
  return (
    <StepFrame title="Review and eSign your application" lead="eSign uses an OTP to your ID-linked mobile, and it counts as your signature on the account opening form."
      onBack={onBack} busy={busy} error={err} canNext={agree && (otp.sent ? code.length === 6 : true)}
      nextLabel={otp.sent ? "eSign and submit" : "Send eSign OTP"}
      onNext={async () => {
        if (!otp.sent) { otp.send(); return; }
        if (!otp.check(code)) { setErr("That OTP doesn't match."); return; }
        setBusy(true); setErr("");
        try { await onSubmit(true); } catch (e) { setErr(e instanceof Error ? e.message : "Submission failed."); setBusy(false); }
      }}>
      <dl className="divide-y divide-line overflow-hidden rounded-xl border border-line">
        {rows.map(([k, v]) => (
          <div key={k} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[10rem_1fr]">
            <dt className="text-sm text-muted">{k}</dt><dd className="min-w-0 break-words text-sm font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <label className="mt-6 flex cursor-pointer items-start gap-3 text-sm">
        <input type="checkbox" className="mt-0.5 size-4 accent-[var(--color-spruce)]" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
        <span>I confirm these details are mine and correct, and I agree to the account terms and to Northstar using a fraud-screening service to verify my identity.</span>
      </label>
      {otp.sent && <><DemoSms code={otp.code} to="your ID-linked mobile" /><OtpInput value={code} onChange={(v) => { setCode(v); setErr(""); }} label="eSign OTP" /></>}
    </StepFrame>
  );
}
