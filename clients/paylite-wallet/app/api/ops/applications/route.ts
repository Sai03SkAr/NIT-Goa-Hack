import { NextResponse } from "next/server";
import { trueid } from "@/lib/trueid";

export async function GET() {
  try {
    const r = await trueid("/api/partner/v1/applications?limit=100");
    return NextResponse.json(await r.json(), { status: r.status });
  } catch {
    return NextResponse.json({ error: "TrueID backend is offline (port 8000)." }, { status: 503 });
  }
}
