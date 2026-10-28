import { NextResponse } from "next/server";
import { registry } from "@/lib/trueid";

type Uid = { name: string; dob: string; gender: string };

/** Simulated DigiLocker fetch: identity details come from the issuer, so the applicant can't type their own.
 * The fetched identity must be the one the PAN is linked to. */
export async function POST(req: Request) {
  const { id_number, otp, pan_name, pan_last4 } = await req.json();
  const id = String(id_number ?? "").replace(/\s/g, "");
  if (!/^\d{12}$/.test(id)) return NextResponse.json({ ok: false, error: "Enter your 12-digit national ID number." });
  if (!/^\d{6}$/.test(String(otp ?? ""))) return NextResponse.json({ ok: false, error: "Enter the 6-digit OTP." });
  const rec = await registry<Uid>(`/uidai/${id}`);
  if (!rec) return NextResponse.json({ ok: false, error: "DigiLocker couldn't find this ID number." });
  if (pan_last4 && id.slice(-4) !== pan_last4)
    return NextResponse.json({ ok: false, error: "This ID isn't the one linked to your PAN." });
  if (pan_name && rec.name.toLowerCase() !== String(pan_name).toLowerCase())
    return NextResponse.json({ ok: false, error: "The name on your ID differs from your PAN. Update one of them, then try again." });
  return NextResponse.json({ ok: true, name: rec.name, dob: rec.dob, gender: rec.gender, id_number: id });
}
