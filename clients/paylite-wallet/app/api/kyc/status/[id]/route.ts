import { NextResponse } from "next/server";
import { getApplication } from "@/lib/trueid";

/** What the APPLICANT may see: a customer-facing state, never the fraud score or reasons.
 * PayLite policy: TrueID's "verification incomplete" (no fraud pattern, but no liveness) still opens a
 * minimum-KYC wallet with RBI's limits; anything else that isn't APPROVE waits for a person. */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const { status, body: v } = await getApplication(id);
    if (status !== 200) return NextResponse.json({ state: "unknown" }, { status });
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
