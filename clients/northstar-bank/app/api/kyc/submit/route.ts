import { NextResponse } from "next/server";
import { clientIp, trueid } from "@/lib/trueid";

/** Browser -> Northstar backend -> TrueID. The bank adds what only the server knows (applicant IP, its own
 * reference number) and the partner key, then returns only the reference to the browser. */
export async function POST(req: Request) {
  const inbound = await req.formData();
  const payload = JSON.parse(String(inbound.get("payload") ?? "{}"));
  const reference = `NSB-${Date.now().toString(36).toUpperCase().slice(-6)}`;
  payload.reference = reference;
  payload.device = { ...(payload.device ?? {}), ip: clientIp(req.headers) };

  const out = new FormData();
  out.append("payload", JSON.stringify(payload));
  for (const k of ["card", "selfie"]) {
    const f = inbound.get(k);
    if (!(f instanceof Blob)) return NextResponse.json({ error: `${k} is required` }, { status: 422 });
    out.append(k, f, `${k}.jpg`);
  }
  inbound.getAll("frames").forEach((f, i) => f instanceof Blob && out.append("frames", f, `frame${i}.jpg`));

  try {
    const r = await trueid("/api/partner/v1/applications", { method: "POST", body: out });
    const j = await r.json();
    if (!r.ok) return NextResponse.json({ error: j.detail ?? "verification service rejected the request" }, { status: r.status });
    return NextResponse.json({ id: j.application_id, reference });
  } catch {
    return NextResponse.json({ error: "Verification service is offline. Start the TrueID backend on port 8000." }, { status: 503 });
  }
}
