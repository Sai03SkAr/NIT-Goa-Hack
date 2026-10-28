"use client";
import { use, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CircleCheck, Clock3, Loader2, CircleAlert } from "lucide-react";
import { Header } from "@/components/Brand";

type State = "checking" | "approved" | "review" | "declined" | "unknown";

const COPY: Record<State, { title: string; body: string }> = {
  checking: { title: "Checking your application", body: "This usually takes under a minute. You can keep this page open." },
  approved: { title: "Your account is open", body: "We've emailed your account number and customer ID. Your debit card ships within 5 working days." },
  review: { title: "We're reviewing your application", body: "A Northstar officer will check a few details and contact you within one working day. You don't need to do anything now." },
  declined: { title: "We couldn't open your account online", body: "We weren't able to verify your identity from the details provided. Visit any Northstar branch with your original ID and PAN." },
  unknown: { title: "We can't find this application", body: "Check the link, or start a new application." },
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

  const Icon = state === "checking" ? Loader2 : state === "approved" ? CircleCheck : state === "review" ? Clock3 : CircleAlert;
  const tone = state === "approved" ? "text-ok" : state === "declined" || state === "unknown" ? "text-err" : state === "review" ? "text-warn" : "text-spruce";
  return (
    <>
      <Header />
      <main className="mx-auto max-w-xl px-4 py-16 sm:px-6">
        <div className="card p-8" aria-live="polite">
          <Icon className={`size-10 ${tone} ${state === "checking" ? "animate-spin" : ""}`} />
          <h1 className="mt-5 text-2xl font-semibold tracking-[-0.02em]">{COPY[state].title}</h1>
          <p className="mt-2 text-muted">{COPY[state].body}</p>
          {ref && <p className="mt-6 text-sm">Application reference <b className="tabular-nums">{ref}</b></p>}
        </div>
        <Link href="/" className="mt-6 inline-block text-sm text-muted hover:text-ink">Back to Northstar Bank</Link>
      </main>
    </>
  );
}
