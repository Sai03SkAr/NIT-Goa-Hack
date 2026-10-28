"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/Brand";

export default function OpsLogin() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  return (
    <>
      <Header />
      <main className="mx-auto max-w-sm px-4 py-16">
        <form className="card p-7" onSubmit={async (e) => {
          e.preventDefault(); setErr("");
          const r = await fetch("/api/ops/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ passcode: code }) });
          if (r.ok) router.push("/ops"); else setErr((await r.json()).error);
        }}>
          <h1 className="text-xl font-semibold">Operations console</h1>
          <p className="mt-1 text-sm text-muted">For Northstar staff. Demo passcode is in .env.example.</p>
          <label className="field mt-6">
            <span className="field-label">Passcode</span>
            <input className="input" type="password" autoComplete="current-password" value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          {err && <p role="alert" className="error mt-3">{err}</p>}
          <button className="btn btn-primary mt-6 w-full" disabled={!code}>Sign in</button>
        </form>
      </main>
    </>
  );
}
