export const API = process.env.NEXT_PUBLIC_API ?? ""; // same origin: proxied to FastAPI by next.config.ts
// No credentials here: analysts sign in for an HttpOnly cookie, applicants get a session cookie. Nothing secret
// may ever live in a NEXT_PUBLIC_* variable, because it ships to every browser.

export const fileUrl = (p?: string | null) => (!p ? "" : p.startsWith("http") || p.startsWith("data:") ? p : `${API}${p}`);

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function check(path: string, r: Response) {
  if (r.ok) return r.json();
  let detail = await r.text();
  try {
    const j = JSON.parse(detail).detail;
    detail = Array.isArray(j) ? j.map((x: any) => (x.field ? `${x.field}: ${x.msg}` : JSON.stringify(x))).join("; ") : String(j);
  } catch {}
  throw new ApiError(r.status, detail || `${path}: ${r.status}`);
}

export async function get<T = any>(path: string): Promise<T> {
  return check(path, await fetch(`${API}${path}`, { cache: "no-store", credentials: "same-origin" }));
}

export async function post<T = any>(path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const form = body instanceof FormData;
  return check(path, await fetch(`${API}${path}`, {
    method: "POST", credentials: "same-origin",
    headers: form ? headers : { "Content-Type": "application/json", ...headers },
    body: form ? body : JSON.stringify(body ?? {}),
  }));
}

export async function del<T = any>(path: string): Promise<T> {
  return check(path, await fetch(`${API}${path}`, { method: "DELETE", credentials: "same-origin" }));
}

export type Band = "APPROVE" | "REVIEW" | "REJECT";

export type Reason = { code: string; text: string; weight: number };
export type ModuleResult = {
  module: string; risk: number; confidence: number; reasons: Reason[];
  evidence: Record<string, any>; features: Record<string, number | null>; simulated: boolean; latency_ms: number;
};

export type AppRow = {
  app_id: string; ts: string; source: string; name: string; id_last4: string; prob: number | null; band: Band;
  forced: string | null; rule_codes: string[]; fraud_type: string; fraud_label: string; action: string;
  stepped_up: boolean; status: string; card_path: string; selfie_path: string;
  model_status?: string; policy_version?: string;
  truth_label: number | null; truth_type: string | null;
};

export type CaseDetail = AppRow & {
  modules: ModuleResult[]; shap: { feature: string; value: number | null; shap: number }[];
  summary: string; form_masked: Record<string, string>; audit: { ts: string; actor: string; action: string; note: string; hash?: string }[];
  evidence: EvidenceCheck[]; rule_texts?: Record<string, string>;
  context?: { geo?: { lat: number; lng: number; accuracy?: number; ts?: string } | null; ip?: string | null; consent?: { version?: string; ts?: string }; ts?: string }; step_up?: { voice?: number; simulated?: boolean; affects_decision?: boolean };
};

export type EvidenceStatus = "PASS" | "FAIL" | "UNAVAILABLE" | "NOT_PROVIDED" | "SIMULATED";
export type EvidenceCheck = { check: string; label: string; source?: string; status: EvidenceStatus; required: boolean };
