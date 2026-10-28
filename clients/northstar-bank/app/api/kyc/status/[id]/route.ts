import { NextResponse } from "next/server";
import { trueid } from "@/lib/trueid";

/** What the APPLICANT may see: a customer-facing state, never the fraud score or reasons. */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const r = await trueid(`/api/partner/v1/applications/${encodeURIComponent(id)}`);
    if (!r.ok) return NextResponse.json({ state: "unknown" }, { status: r.status });
    const v = await r.json();
    const state = v.status !== "completed" ? (v.status === "error" ? "review" : "checking")
      : v.decision === "APPROVE" ? "approved" : v.decision === "REJECT" ? "declined" : "review";
    return NextResponse.json({ state, reference: v.reference });
  } catch {
    return NextResponse.json({ state: "checking" });
  }
}
