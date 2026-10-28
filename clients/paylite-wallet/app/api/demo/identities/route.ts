import { NextResponse } from "next/server";
import { demoIdentities, mode } from "@/lib/trueid";

/** Test identities for demo mode; empty when connected to the real TrueID backend. */
export async function GET() {
  return NextResponse.json({ mode: await mode(), identities: await demoIdentities() });
}
