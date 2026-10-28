import { NextResponse, type NextRequest } from "next/server";
import { isOps, OPS_COOKIE } from "@/lib/ops-auth";

export async function middleware(req: NextRequest) {
  const p = req.nextUrl.pathname;
  if (p === "/ops/login" || p === "/api/ops/login") return NextResponse.next();
  if (await isOps(req.cookies.get(OPS_COOKIE)?.value)) return NextResponse.next();
  if (p.startsWith("/api/")) return NextResponse.json({ error: "sign in to the operations console" }, { status: 401 });
  return NextResponse.redirect(new URL("/ops/login", req.url));
}

export const config = { matcher: ["/ops/:path*", "/api/ops/:path*"] };
