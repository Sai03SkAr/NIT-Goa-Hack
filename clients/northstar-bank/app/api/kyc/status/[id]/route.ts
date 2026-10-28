import { NextResponse } from "next/server";
import { getApplication } from "@/lib/trueid";

/** What the APPLICANT may see: a customer-facing state, never the fraud score or reasons. */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const { status, body: v } = await getApplication(id);
    if (status !== 200) return NextResponse.json({ state: "unknown" }, { status });
    const state = v.status !== "completed" ? (v.status === "error" ? "review" : "checking")
      : v.decision === "APPROVE" ? "approved" : v.decision === "REJECT" ? "declined" : "review";
    return NextResponse.json({ state, reference: v.reference });
  } catch {
    return NextResponse.json({ state: "checking" });
  }
}
