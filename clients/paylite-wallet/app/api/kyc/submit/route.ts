import { NextResponse } from "next/server";
import { PARTNER } from "@/lib/partner";
import { clientIp, submitApplication } from "@/lib/trueid";

/** Browser -> this site's server -> TrueID. The server adds what only it knows (applicant IP, its own reference
 * number) and the partner key, then returns only the reference to the browser. */
export async function POST(req: Request) {
  const inbound = await req.formData();
  let payload;
  try { payload = JSON.parse(String(inbound.get("payload") ?? "{}")); }
  catch { return NextResponse.json({ error: "Malformed application" }, { status: 400 }); }
  const reference = `${PARTNER.refPrefix}-${Date.now().toString(36).toUpperCase().slice(-6)}`;
  payload.reference = reference;
  payload.device = { ...(payload.device ?? {}), ip: clientIp(req.headers) };

  const card = inbound.get("card"), selfie = inbound.get("selfie");
  if (!(card instanceof Blob) || !(selfie instanceof Blob))
    return NextResponse.json({ error: "Add both the ID card and the selfie." }, { status: 422 });
  const frames = inbound.getAll("frames").filter((f): f is File => f instanceof File);

  try {
    const r = await submitApplication(payload, { card, selfie, frames });
    if (r.status !== 200) return NextResponse.json({ error: r.body.detail ?? "Verification service rejected the application" }, { status: r.status });
    return NextResponse.json({ id: r.body.application_id, reference });
  } catch {
    return NextResponse.json({ error: "Verification service is offline. Start the TrueID backend, or set TRUEID_MODE=local." }, { status: 503 });
  }
}
