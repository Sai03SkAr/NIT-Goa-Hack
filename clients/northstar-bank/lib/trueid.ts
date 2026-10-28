/** Server-side client for the TrueID Shield partner API. The partner key never reaches the browser. */

export const TRUEID = process.env.TRUEID_API_URL ?? "http://127.0.0.1:8000";
const KEY = process.env.TRUEID_PARTNER_KEY ?? "ns_test_7f3c9a2e5b81";

export async function trueid(path: string, init: RequestInit = {}) {
  return fetch(`${TRUEID}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...(init.headers ?? {}), "X-Partner-Key": KEY },
  });
}

/** Simulated government sources (NSDL PAN, DigiLocker). For the demo they are answered by TrueID's mock registries;
 * in production the bank would call NSDL / DigiLocker directly. */
export async function registry<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`${TRUEID}/mock${path}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

export function clientIp(h: Headers): string {
  return (h.get("x-forwarded-for")?.split(",")[0] ?? h.get("x-real-ip") ?? "").trim();
}
