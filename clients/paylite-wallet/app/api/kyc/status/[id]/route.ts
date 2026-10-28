import { NextResponse } from "next/server";
import { trueid } from "@/lib/trueid";

/** What the APPLICANT may see: a customer-facing state, never the fraud score or reasons.
 * PayLite policy: TrueID's "verification incomplete" (no fraud pattern, but no liveness) still opens a
 * minimum-KYC wallet with RBI's limits; anything else that isn't APPROVE waits for a person. */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const r = await trueid(`/api/partner/v1/applications/${encodeURIComponent(id)}`);
    if (!r.ok) return NextResponse.json({ state: "unknown" }, { status: r.status });
    const v = await r.json();
    let state = "checking";
    if (v.status === "error") state = "review";
    else if (v.status === "completed")
      state = v.decision === "APPROVE" ? "approved" : v.decision === "REJECT" ? "declined"
        : v.fraud_type === "incomplete" ? "limited" : "review";
    return NextResponse.json({ state, reference: v.reference });
  } catch {
    return NextResponse.json({ state: "checking" });
  }
}
