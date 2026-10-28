/** Server-side gateway to TrueID Shield. Identical in both client sites; lib/partner.ts says who we are.
 *
 * TRUEID_MODE (in .env.local):
 *   auto    (default) use the real backend at TRUEID_API_URL when it answers, otherwise demo mode
 *   remote  always use the real backend; fail loudly if it's down
 *   local   always use the built-in demo engine (lib/trueid-local.ts)
 * The partner key stays on this server. The browser never sees it. */
import { PARTNER } from "./partner";
import { localGet, localList, localSubmit, lookupId, lookupPan, DEMO_IDENTITIES, type Payload } from "./trueid-local";

export const TRUEID = (process.env.TRUEID_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const KEY = process.env.TRUEID_PARTNER_KEY ?? PARTNER.defaultKey;
const MODE = (process.env.TRUEID_MODE ?? "auto").toLowerCase();

let probe: { at: number; up: boolean } | null = null;

/** Which engine answers right now. In auto mode the backend is re-checked every 5 seconds. */
export async function mode(): Promise<"remote" | "local"> {
  if (MODE === "remote") return "remote";
  if (MODE === "local") return "local";
  if (probe && Date.now() - probe.at < 5000) return probe.up ? "remote" : "local";
  let up = false;
  try {
    const r = await fetch(`${TRUEID}/api/health`, { cache: "no-store", signal: AbortSignal.timeout(1200) });
    up = r.ok;
  } catch { up = false; }
  probe = { at: Date.now(), up };
  return up ? "remote" : "local";
}

async function remote(path: string, init: RequestInit = {}) {
  return fetch(`${TRUEID}${path}`, { ...init, cache: "no-store", headers: { ...(init.headers ?? {}), "X-Partner-Key": KEY } });
}

export type Result = { status: number; body: Record<string, unknown> };

/** POST /api/partner/v1/applications. `files` are the card, selfie and liveness frames. */
export async function submitApplication(payload: Payload, files: { card: Blob; selfie: Blob; frames: Blob[] }): Promise<Result> {
  if ((await mode()) === "local") {
    const r = localSubmit(PARTNER, payload);
    return "error" in r ? { status: 422, body: { detail: r.error } } : { status: 200, body: r };
  }
  const fd = new FormData();
  fd.append("payload", JSON.stringify(payload));
  fd.append("card", files.card, "card.jpg");
  fd.append("selfie", files.selfie, "selfie.jpg");
  files.frames.forEach((f, i) => fd.append("frames", f, `frame${i}.jpg`));
  const r = await remote("/api/partner/v1/applications", { method: "POST", body: fd });
  return { status: r.status, body: await r.json() };
}

export async function getApplication(id: string): Promise<Result> {
  if ((await mode()) === "local") {
    const v = localGet(PARTNER.id, id);
    return v ? { status: 200, body: v } : { status: 404, body: { detail: "unknown application" } };
  }
  const r = await remote(`/api/partner/v1/applications/${encodeURIComponent(id)}`);
  return { status: r.status, body: await r.json() };
}

export async function listApplications(): Promise<Result> {
  const m = await mode();
  if (m === "local") return { status: 200, body: { ...localList(PARTNER.id, PARTNER.name), mode: m } };
  const r = await remote("/api/partner/v1/applications?limit=100");
  return { status: r.status, body: { ...(await r.json()), mode: m, backend: TRUEID } };
}

/** Simulated government sources (NSDL PAN, DigiLocker). Connected mode asks TrueID's mock registries; demo mode
 * uses the demo identities. In production the bank would call NSDL / DigiLocker itself. */
export async function registry<T>(kind: "pan" | "uidai", key: string): Promise<T | null> {
  if ((await mode()) === "local") return (kind === "pan" ? lookupPan(key) : lookupId(key)) as T | null;
  try {
    const r = await fetch(`${TRUEID}/mock/${kind}/${encodeURIComponent(key)}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as T) : null;
  } catch { return null; }
}

/** Test identities to type in, only in demo mode (connected mode uses TrueID's own test kit). */
export async function demoIdentities() {
  return (await mode()) === "local" ? DEMO_IDENTITIES : [];
}

export function clientIp(h: Headers): string {
  return (h.get("x-forwarded-for")?.split(",")[0] ?? h.get("x-real-ip") ?? "").trim();
}
