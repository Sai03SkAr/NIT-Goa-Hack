import { NextResponse } from "next/server";
import { OPS_COOKIE, opsToken } from "@/lib/ops-auth";

export async function POST(req: Request) {
  const { passcode } = await req.json();
  const expected = await opsToken();
  if ((await opsToken(String(passcode ?? ""))) !== expected)
    return NextResponse.json({ error: "That passcode isn't right." }, { status: 401 });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(OPS_COOKIE, expected, { httpOnly: true, sameSite: "strict", path: "/", maxAge: 60 * 60 * 8 });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(OPS_COOKIE);
  return res;
}
