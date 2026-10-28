import { NextResponse } from "next/server";
import { registry } from "@/lib/trueid";

type Pan = { name: string; dob: string; id_last4: string };
const PAN_RE = /^[A-Z]{3}P[A-Z]\d{4}[A-Z]$/;

/** Simulated NSDL PAN verification: PAN must exist, belong to an individual, and match the date of birth. */
export async function POST(req: Request) {
  const { pan, dob } = await req.json();
  const p = String(pan ?? "").toUpperCase().trim();
  if (!PAN_RE.test(p)) return NextResponse.json({ ok: false, error: "Enter a valid individual PAN, like ABCPK1234Z." });
  const rec = await registry<Pan>("pan", p);
  if (!rec) return NextResponse.json({ ok: false, error: "This PAN isn't in the Income Tax records. Check it and try again." });
  if (rec.dob !== dob) return NextResponse.json({ ok: false, error: "Date of birth doesn't match the PAN records." });
  return NextResponse.json({ ok: true, name: rec.name, id_last4: rec.id_last4 });
}
