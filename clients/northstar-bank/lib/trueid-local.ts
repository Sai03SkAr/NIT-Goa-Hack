/** Demo mode: a stand-in for TrueID Shield that runs inside this site, so the flow can be tested without the
 * Python backend. It returns the SAME response shape as the real partner API (/api/partner/v1/*), so switching to
 * the real backend changes no UI code.
 *
 * What it does NOT do: look at images, match faces, read QR codes, score with the trained model. Verdicts come from
 * a few transparent rules over the typed details, the session signals and what the partner says it checked.
 * The operations console labels every verdict from here as a sample. Identical copy in both client sites. */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export type Identity = { name: string; dob: string; gender: string; id_number: string; pan: string; phone: string };

/** Mock issuer registry (stands in for UIDAI / NSDL). Valid Verhoeff ID numbers, fictional people. */
export const DEMO_IDENTITIES: Identity[] = [
  { name: "Riya Kamat", dob: "04/09/1999", gender: "F", id_number: "234567890124", pan: "ABCPK1234Z", phone: "9822001122" },
  { name: "Arjun Naik", dob: "17/02/1994", gender: "M", id_number: "345678901238", pan: "BNKPN5521K", phone: "9890456712" },
  { name: "Meera Desai", dob: "29/11/1988", gender: "F", id_number: "456789012341", pan: "CDQPD7781M", phone: "9765123480" },
  { name: "Karthik Prabhu", dob: "08/06/2001", gender: "M", id_number: "567890123458", pan: "DPLPP3304R", phone: "9923345671" },
];

export function lookupPan(pan: string) {
  const p = DEMO_IDENTITIES.find((i) => i.pan === pan.toUpperCase());
  return p ? { name: p.name, dob: p.dob, id_last4: p.id_number.slice(-4) } : null;
}
export function lookupId(id: string) {
  const p = DEMO_IDENTITIES.find((i) => i.id_number === id);
  return p ? { name: p.name, dob: p.dob, gender: p.gender } : null;
}

const REASONS: Record<string, [string, string, number]> = {
  REG_ID_NOT_FOUND: ["registry", "ID number not found in the identity registry", 0.5],
  REG_NAME_MISMATCH: ["registry", "Name differs from the identity registry", 0.45],
  REG_DOB_MISMATCH: ["registry", "Date of birth differs from the identity registry", 0.45],
  REG_PAN_LINK_MISMATCH: ["registry", "PAN is not linked to this ID number", 0.35],
  COR_SHARED_ID: ["correlation", "ID number used by another applicant", 0.5],
  BEH_VELOCITY_DEVICE: ["behavior", "This device submitted many applications recently", 0.3],
  BEH_VELOCITY_PHONE: ["behavior", "This phone number is on several recent applications", 0.2],
  BEH_FAST_FILL: ["behavior", "Form filled faster than a human plausibly can", 0.3],
  BEH_PASTE_HEAVY: ["behavior", "Most fields were pasted, not typed", 0.25],
  BEH_ROBOTIC_TIMING: ["behavior", "Keystroke timing is near-constant (scripted)", 0.3],
  BIO_VIRTUAL_CAMERA: ["biometric", "A virtual camera (injection tool) was detected", 0.6],
  BIO_LIVENESS_FAIL: ["biometric", "Active liveness challenge failed", 0.5],
  BIO_LIVENESS_NOT_PERFORMED: ["biometric", "No live selfie check was run; the selfie is an uploaded photo", 0.25],
};
const TYPES: Record<string, [string, string]> = {
  first_party: ["First-party / Frankenstein", "Verify via issuer OTP / face authentication"],
  third_party: ["Third-party fabricated", "Require DigiLocker-fetched document or assisted video KYC"],
  ring: ["Synthetic ring", "Freeze linked applications, escalate to the fraud team"],
  bot: ["Bot / scripted", "Block device, step-up challenge"],
  injection: ["Injection / replay", "Assisted video KYC"],
  incomplete: ["Verification incomplete", "Run a live selfie (liveness) check before granting full access"],
  none: ["No fraud pattern", "Proceed"],
};

type Rec = {
  application_id: string; reference: string; partner: string; submitted_at: string; profile: string;
  partner_checks: Record<string, boolean>; capture: Record<string, string>; applicant: Record<string, string>;
  ready_at: number; verdict: Record<string, unknown>;
};
type Store = { apps: Rec[] };

const FILE = join(process.cwd(), ".trueid-local.json");
const g = globalThis as unknown as { __trueidLocal?: Store };
function store(): Store {
  if (!g.__trueidLocal) {
    try { g.__trueidLocal = existsSync(FILE) ? JSON.parse(readFileSync(FILE, "utf8")) : { apps: [] }; }
    catch { g.__trueidLocal = { apps: [] }; }
  }
  return g.__trueidLocal!;
}
function save() { try { writeFileSync(FILE, JSON.stringify(store())); } catch { /* demo store is best-effort */ } }

function mask(f: Record<string, string>) {
  const m = { ...f };
  if (f.id_number) m.id_number = "XXXX XXXX " + f.id_number.slice(-4);
  if (f.pan) m.pan = f.pan.slice(0, 2) + "XXXXX" + f.pan.slice(-3);
  if (f.phone) m.phone = "XXXXXX" + f.phone.slice(-4);
  return m;
}

/** Transparent rules standing in for TrueID's five modules + fusion. */
function evaluate(p: Payload, history: Rec[]) {
  const f = p.form, t = p.telemetry ?? {}, live = p.liveness ?? {};
  const codes: string[] = [];
  const reg = lookupId(f.id_number);
  if (!reg) codes.push("REG_ID_NOT_FOUND");
  else {
    if (reg.name.toLowerCase() !== String(f.name).trim().toLowerCase()) codes.push("REG_NAME_MISMATCH");
    if (reg.dob !== f.dob) codes.push("REG_DOB_MISMATCH");
    if (f.pan) { const pn = lookupPan(f.pan); if (!pn || pn.id_last4 !== f.id_number.slice(-4)) codes.push("REG_PAN_LINK_MISMATCH"); }
  }
  const others = history.filter((h) => h.applicant._id_full === f.id_number && h.applicant._name_l !== String(f.name).trim().toLowerCase());
  if (others.length) codes.push("COR_SHARED_ID");
  const day = Date.now() - 864e5;
  if (p.device?.device_id && history.filter((h) => h.applicant._device === p.device!.device_id && Date.parse(h.submitted_at) > day).length >= 3) codes.push("BEH_VELOCITY_DEVICE");
  if (history.filter((h) => h.applicant._phone === f.phone && h.applicant._name_l !== String(f.name).trim().toLowerCase()).length) codes.push("BEH_VELOCITY_PHONE");
  if (typeof t.fill_time === "number" && t.fill_time > 0 && t.fill_time < 20) codes.push("BEH_FAST_FILL");
  if ((t.paste_fields ?? 0) >= 5) codes.push("BEH_PASTE_HEAVY");
  if (t.iki_mean && t.iki_std !== undefined && t.iki_std / Math.max(t.iki_mean, 1) < 0.15) codes.push("BEH_ROBOTIC_TIMING");
  const performed = live.performed !== false;
  if (live.virtual_camera) codes.push("BIO_VIRTUAL_CAMERA");
  if (!performed) codes.push("BIO_LIVENESS_NOT_PERFORMED");
  else if (!live.passed) codes.push("BIO_LIVENESS_FAIL");

  const reasons = codes.map((c) => ({ module: REASONS[c][0], code: c, text: REASONS[c][1], weight: REASONS[c][2] }))
    .sort((a, b) => b.weight - a.weight);
  const has = (c: string) => codes.includes(c);
  const type = has("BIO_VIRTUAL_CAMERA") ? "injection"
    : has("COR_SHARED_ID") || has("BEH_VELOCITY_DEVICE") ? "ring"
    : has("BEH_ROBOTIC_TIMING") || (has("BEH_FAST_FILL") && has("BEH_PASTE_HEAVY")) ? "bot"
    : has("REG_ID_NOT_FOUND") ? "third_party"
    : has("REG_NAME_MISMATCH") || has("REG_DOB_MISMATCH") || has("REG_PAN_LINK_MISMATCH") ? "first_party"
    : has("BIO_LIVENESS_FAIL") ? "injection"
    : has("BIO_LIVENESS_NOT_PERFORMED") ? "incomplete" : "none";
  const modRisk: Record<string, number> = { document: 0.05, biometric: 0.08, behavior: 0.06, registry: 0.04, correlation: 0.02 };
  for (const r of reasons) modRisk[r.module] = Math.min(1, Math.max(modRisk[r.module], 0.15) + r.weight);
  const raw = 0.03 + reasons.reduce((s, r) => s + r.weight, 0) * 0.75;
  const risk = Math.min(0.97, raw);
  const hardReject = ["BIO_VIRTUAL_CAMERA", "COR_SHARED_ID", "REG_NAME_MISMATCH", "REG_DOB_MISMATCH"].some(has);
  const decision = hardReject || risk >= 0.7 ? "REJECT" : risk >= 0.3 || reasons.length ? "REVIEW" : "APPROVE";
  return {
    status: "completed", evaluated_at: new Date().toISOString().slice(0, 19), decision, risk_score: +risk.toFixed(4),
    decision_rules: codes.filter((c) => ["BIO_LIVENESS_NOT_PERFORMED", "BIO_LIVENESS_FAIL"].includes(c)),
    fraud_type: decision === "APPROVE" ? "none" : type, fraud_label: TYPES[decision === "APPROVE" ? "none" : type][0],
    recommended_action: TYPES[decision === "APPROVE" ? "none" : type][1], reasons,
    modules: Object.entries(modRisk).map(([module, r]) => ({ module, risk: +r.toFixed(3), simulated: true })),
    summary: "Demo mode: sample verdict from simple rules. Images were not analysed.", analyst_status: "open",
  };
}

export type Payload = {
  reference?: string; form: Record<string, string>; device?: { device_id?: string; ip?: string; [k: string]: unknown };
  telemetry?: { fill_time?: number; paste_fields?: number; iki_mean?: number; iki_std?: number; [k: string]: unknown };
  liveness?: { performed?: boolean; passed?: boolean; virtual_camera?: boolean; [k: string]: unknown };
  capture?: Record<string, string>; partner_checks?: Record<string, boolean>;
};

const REQUIRED = ["name", "dob", "gender", "id_number", "phone", "email"];

export function localSubmit(partner: { id: string; prefix: string; profile: string }, p: Payload) {
  const missing = REQUIRED.filter((k) => !String(p.form?.[k] ?? "").trim());
  if (missing.length) return { error: `form fields required: ${missing.join(", ")}` };
  const s = store();
  const history = s.apps;
  const id = partner.prefix + Math.random().toString(16).slice(2, 10).toUpperCase();
  const rec: Rec = {
    application_id: id, reference: p.reference ?? "", partner: partner.id, submitted_at: new Date().toISOString().slice(0, 19),
    profile: partner.profile, partner_checks: p.partner_checks ?? {}, capture: p.capture ?? {},
    applicant: { ...mask(p.form), _id_full: p.form.id_number, _name_l: String(p.form.name).trim().toLowerCase(),
      _device: String(p.device?.device_id ?? ""), _phone: p.form.phone },
    ready_at: Date.now() + 3500, // the real pipeline takes a few seconds; keep the "checking" state visible
    verdict: evaluate(p, history),
  };
  s.apps.unshift(rec);
  s.apps = s.apps.slice(0, 500);
  save();
  return { application_id: id, status: "processing", status_url: `/api/partner/v1/applications/${id}` };
}

function view(r: Rec) {
  const applicant = Object.fromEntries(Object.entries(r.applicant).filter(([k]) => !k.startsWith("_")));
  const base = { application_id: r.application_id, reference: r.reference, partner: r.partner, submitted_at: r.submitted_at,
    profile: r.profile, partner_checks: r.partner_checks, capture: r.capture, applicant };
  return Date.now() < r.ready_at ? { ...base, status: "processing" } : { ...base, ...r.verdict };
}

export function localGet(partnerId: string, id: string) {
  const r = store().apps.find((a) => a.application_id === id && a.partner === partnerId);
  return r ? view(r) : null;
}

export function localList(partnerId: string, name: string) {
  return { partner: name, applications: store().apps.filter((a) => a.partner === partnerId).slice(0, 100).map(view) };
}
