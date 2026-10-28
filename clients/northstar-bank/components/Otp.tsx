"use client";
import { useState } from "react";
import { MessageSquareText } from "lucide-react";

/** Simulated OTP: no SMS gateway in the demo, so the code is shown in an on-screen "SMS". */
export function useOtp() {
  const [code, setCode] = useState<string | null>(null);
  const send = () => setCode(String(Math.floor(100000 + Math.random() * 900000)));
  return { code, send, sent: code !== null, check: (v: string) => code !== null && v === code };
}

export function DemoSms({ code, to }: { code: string | null; to: string }) {
  if (!code) return null;
  return (
    <div role="status" className="mt-4 flex items-start gap-3 rounded-xl border border-line bg-mist/60 px-4 py-3 text-sm">
      <MessageSquareText className="mt-0.5 size-4 shrink-0 text-spruce" />
      <div>
        <div className="text-muted">Demo message to {to}</div>
        <div>Your Northstar code is <b className="tabular-nums tracking-wider">{code}</b>. It expires in 10 minutes.</div>
      </div>
    </div>
  );
}

export function OtpInput({ value, onChange, label = "Enter the 6-digit code" }: { value: string; onChange: (v: string) => void; label?: string }) {
  return (
    <label className="field mt-5">
      <span className="field-label">{label}</span>
      <input className="input mono max-w-[12rem] text-lg" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
        value={value} onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))} placeholder="••••••" />
    </label>
  );
}
