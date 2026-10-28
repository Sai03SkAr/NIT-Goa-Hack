export const API = process.env.NEXT_PUBLIC_API ?? ""; // same origin: proxied to FastAPI by next.config.ts
// SSE goes direct: proxies can buffer event streams. 127.0.0.1, not "localhost", to avoid an IPv6 (::1) miss.
export const STREAM_API = process.env.NEXT_PUBLIC_STREAM_API ?? "http://127.0.0.1:8000";

// optional analyst API key (backend TRUEID_API_KEY); images can't send headers, so they carry it as ?key=
const KEY = process.env.NEXT_PUBLIC_API_KEY;
const auth = (): Record<string, string> => (KEY ? { "X-API-Key": KEY } : {});
export const withKey = (u: string) => (KEY ? `${u}${u.includes("?") ? "&" : "?"}key=${encodeURIComponent(KEY)}` : u);

export const fileUrl = (p?: string | null) => (!p ? "" : p.startsWith("http") || p.startsWith("data:") ? p : withKey(`${API}${p}`));

export async function get<T = any>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store", headers: auth() });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function post<T = any>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: body instanceof FormData ? auth() : { "Content-Type": "application/json", ...auth() },
    body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function del<T = any>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { method: "DELETE", headers: auth() });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export type Band = "APPROVE" | "REVIEW" | "REJECT";

export type Reason = { code: string; text: string; weight: number };
export type ModuleResult = {
  module: string; risk: number; confidence: number; reasons: Reason[];
  evidence: Record<string, any>; features: Record<string, number | null>; simulated: boolean; latency_ms: number;
};

export type AppRow = {
  app_id: string; ts: string; source: string; name: string; id_last4: string; prob: number; band: Band;
  forced: string | null; rule_codes: string[]; fraud_type: string; fraud_label: string; action: string;
  stepped_up: boolean; status: string; card_path: string; selfie_path: string;
  truth_label: number | null; truth_type: string | null;
};

export type CaseDetail = AppRow & {
  modules: ModuleResult[]; shap: { feature: string; value: number | null; shap: number }[];
  summary: string; form_masked: Record<string, string>; audit: { ts: string; actor: string; action: string; note: string }[];
};
