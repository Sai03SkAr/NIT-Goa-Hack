/** Server-side client for the TrueID Shield partner API. The partner key never reaches the browser. */

export const TRUEID = process.env.TRUEID_API_URL ?? "http://127.0.0.1:8000";
const KEY = process.env.TRUEID_PARTNER_KEY ?? "pl_test_41d8e0c6aa27";

export async function trueid(path: string, init: RequestInit = {}) {
  return fetch(`${TRUEID}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...(init.headers ?? {}), "X-Partner-Key": KEY },
  });
}

export function clientIp(h: Headers): string {
  return (h.get("x-forwarded-for")?.split(",")[0] ?? h.get("x-real-ip") ?? "").trim();
}
