import { NextResponse } from "next/server";
import { listApplications } from "@/lib/trueid";

export async function GET() {
  try {
    const r = await listApplications();
    return NextResponse.json(r.body, { status: r.status });
  } catch {
    return NextResponse.json({ error: "TrueID backend is offline. Start it, or set TRUEID_MODE=local." }, { status: 503 });
  }
}
