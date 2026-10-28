import Link from "next/link";
import { ArrowRight, Fingerprint, FileCheck2, Network, Radar, ScanFace, ShieldAlert } from "lucide-react";
import { Logo } from "@/components/ui";

const SIGNALS = [
  { icon: FileCheck2, title: "Signed-QR documents", text: "Ed25519 issuer signature + QR ↔ OCR ↔ form. A pixel-perfect forgery still can't forge a key." },
  { icon: ScanFace, title: "Biometrics & liveness", text: "Selfie ↔ card ↔ registry, face reuse across identities, random challenges, virtual-camera detection." },
  { icon: Radar, title: "Behaviour", text: "Typing rhythm, paste patterns, velocity windows, sequential emails — one fraudster has one rhythm." },
  { icon: Fingerprint, title: "Registries", text: "UIDAI-like, PAN, telecom, CKYC, bureau. Synthetic identities look clean but have no history." },
  { icon: Network, title: "Identity graph", text: "Specificity-weighted links (IP down-weighted for CGNAT) expose rings; families aren't flagged." },
  { icon: ShieldAlert, title: "Attacked by us", text: "12 attacks incl. the DeepID fine-edit and an adaptive attacker. Fused beats every single check." },
];

export default function Home() {
  return (
    <div className="grid-bg min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <div className="flex gap-2">
          <Link href="/dashboard" className="btn">Analyst console</Link>
          <Link href="/kyc" className="btn btn-primary">Start KYC <ArrowRight className="size-4" /></Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-24 pt-14">
        <div className="chip mb-6"><span className="size-1.5 rounded-full bg-brand" />Hacksploit 2026 · PS3 · Synthetic identity fraud in automated KYC</div>
        <h1 className="max-w-4xl text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
          Every check passes alone.<br />
          <span className="bg-gradient-to-r from-brand to-brand-2 bg-clip-text text-transparent">The lie shows up in the correlation.</span>
        </h1>
        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
          A synthetic identity has a valid ID number, a real-looking card and a face that matches its photo. The best
          ID-forgery detectors at ICCV 2025 scored at chance on a carefully edited date of birth. So TrueID Shield trusts
          no single check: it correlates documents, biometrics, behaviour, registries and a cross-application identity
          graph — and proves it by attacking itself.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/kyc" className="btn btn-primary px-5 py-3 text-base">Run a live KYC <ArrowRight className="size-4" /></Link>
          <Link href="/dashboard/metrics" className="btn px-5 py-3 text-base">See the evidence</Link>
        </div>

        <div className="mt-16 grid gap-4 md:grid-cols-3">
          {SIGNALS.map(({ icon: I, title, text }, i) => (
            <div key={title} className="panel fade-up p-5" style={{ animationDelay: `${i * 60}ms` }}>
              <I className="size-5 text-brand" />
              <div className="mt-3 font-semibold">{title}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>

        <div className="panel mt-10 flex flex-wrap items-center justify-between gap-4 p-5 text-sm">
          <span className="text-muted">The LLM only explains, citing fixed reason codes. <span className="text-fg">It never decides.</span></span>
          <span className="mono text-xs text-dim">LangGraph · XGBoost + isotonic · SHAP · InsightFace · EasyOCR · MediaPipe</span>
        </div>
      </main>
    </div>
  );
}
