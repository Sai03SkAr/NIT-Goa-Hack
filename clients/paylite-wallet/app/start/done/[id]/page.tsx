"use client";
import { use, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CircleAlert, CircleCheck, Clock3, Loader2 } from "lucide-react";
import { Logo } from "@/components/Brand";

type State = "checking" | "approved" | "limited" | "review" | "declined" | "unknown";
const COPY: Record<State, { title: string; body: string }> = {
  checking: { title: "Setting up your wallet", body: "Checking your details. This takes a few seconds." },
  approved: { title: "Your wallet is ready", body: "Add money with UPI and start paying." },
  limited: { title: "Your wallet is ready", body: "You can spend up to ₹10,000 a month. Complete full KYC with a video selfie to remove the limit." },
  review: { title: "We're checking a few details", body: "Our team will look at your application and text you within 24 hours." },
  declined: { title: "We couldn't create your wallet", body: "We couldn't verify the details you gave. Check that they match your ID card exactly." },
  unknown: { title: "We can't find this application", body: "Start again from the PayLite home page." },
};

export default function Done({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const ref = useSearchParams().get("ref");
  const [state, setState] = useState<State>("checking");
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const j = await (await fetch(`/api/kyc/status/${id}`)).json();
        if (stop) return;
        setState(j.state);
        if (j.state === "checking") setTimeout(poll, 2000);
      } catch { if (!stop) setTimeout(poll, 3000); }
    };
    poll();
    return () => { stop = true; };
  }, [id]);
  const Icon = state === "checking" ? Loader2 : state === "approved" || state === "limited" ? CircleCheck : state === "review" ? Clock3 : CircleAlert;
  const tone = state === "approved" || state === "limited" ? "text-ok" : state === "review" ? "text-warn" : state === "checking" ? "text-plum" : "text-err";
  return (
    <div className="mx-auto flex min-h-dvh max-w-[440px] flex-col px-5 pb-8 pt-5">
      <Logo />
      <main className="mt-16" aria-live="polite">
        <Icon className={`size-12 ${tone} ${state === "checking" ? "animate-spin" : ""}`} />
        <h1 className="mt-6 text-[2rem] font-bold leading-[1.05] tracking-[-0.03em]">{COPY[state].title}</h1>
        <p className="mt-3 text-lg text-muted">{COPY[state].body}</p>
        {ref && <p className="mt-8 text-sm text-muted">Reference <b className="tabular-nums text-ink">{ref}</b></p>}
      </main>
      <Link href="/" className="btn mt-auto w-full">Done</Link>
    </div>
  );
}
