/* KYC replica server. No dependencies: `node server.js`. Identical in both kyc-* folders; partner.json says who we are.
 *
 * It serves the KYC pages in public/ and is the only thing that talks to TrueID Shield, so the partner key never
 * reaches the browser.
 *
 *   TRUEID_MODE        auto (default): the real backend at TRUEID_API_URL when it answers, otherwise demo mode
 *                      remote: always the real backend     local: always the built-in demo engine
 *   TRUEID_API_URL     default http://127.0.0.1:8000
 *   TRUEID_PARTNER_KEY default: partner.json defaultKey (matches backend/app/partners.py)
 *   PORT               default: partner.json port
 *   OPS_PASSCODE       default: partner.json opsPasscode
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = __dirname;
const PARTNER = JSON.parse(fs.readFileSync(path.join(ROOT, "partner.json"), "utf8"));
loadEnv(path.join(ROOT, ".env.local"));

const TRUEID = (process.env.TRUEID_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const KEY = process.env.TRUEID_PARTNER_KEY || PARTNER.defaultKey;
const MODE = (process.env.TRUEID_MODE || "auto").toLowerCase();
const PORT = Number(process.env.PORT || PARTNER.port);
const OPS = process.env.OPS_PASSCODE || PARTNER.opsPasscode;

function loadEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

// ---------- engine switch ----------
let probe = null;
async function mode() {
  if (MODE === "remote" || MODE === "local") return MODE;
  if (probe && Date.now() - probe.at < 5000) return probe.up ? "remote" : "local";
  let up = false;
  try { up = (await fetch(`${TRUEID}/api/health`, { signal: AbortSignal.timeout(1200) })).ok; } catch { up = false; }
  probe = { at: Date.now(), up };
  return up ? "remote" : "local";
}
const remote = (p, init = {}) => fetch(`${TRUEID}${p}`, { ...init, headers: { ...(init.headers || {}), "X-Partner-Key": KEY } });

// ---------- demo engine (same rules and JSON as clients/*/lib/trueid-local.ts) ----------
const DEMO_IDENTITIES = [
  { name: "Riya Kamat", dob: "04/09/1999", gender: "F", id_number: "234567890124", pan: "ABCPK1234Z", phone: "9822001122", address: "14 Altinho Road, Panaji, Goa 403001",
    employer: "Konkan Software Pvt Ltd", net_pay: "68400", bank: "Harbour Co-operative Bank", account_no: "40021187650", ifsc: "HRBR0000412", consumer_no: "610233457781" },
  { name: "Arjun Naik", dob: "17/02/1994", gender: "M", id_number: "345678901238", pan: "BNKPN5521K", phone: "9890456712", address: "B-302 Sea Breeze, Margao, Goa 403601",
    employer: "Mandovi Logistics Ltd", net_pay: "54250", bank: "Harbour Co-operative Bank", account_no: "40021190331", ifsc: "HRBR0000415", consumer_no: "610245118020" },
  { name: "Meera Desai", dob: "29/11/1988", gender: "F", id_number: "456789012341", pan: "CDQPD7781M", phone: "9765123480", address: "7 Hill View Lane, Kothrud, Pune 411038",
    employer: "Sahyadri Health Services", net_pay: "92300", bank: "Western Ghats Bank", account_no: "71200034478", ifsc: "WGTB0002201", consumer_no: "170044582913" },
  { name: "Karthik Prabhu", dob: "08/06/2001", gender: "M", id_number: "567890123458", pan: "DPLPP3304R", phone: "9923345671", address: "22 MG Road, Mangaluru, Karnataka 575001",
    employer: "Netravati Foods Pvt Ltd", net_pay: "38900", bank: "Western Ghats Bank", account_no: "71200051296", ifsc: "WGTB0003117", consumer_no: "560078120344" },
];
const REASONS = {
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
const TYPES = {
  first_party: ["First-party / Frankenstein", "Verify via issuer OTP / face authentication"],
  third_party: ["Third-party fabricated", "Require DigiLocker-fetched document or assisted video KYC"],
  ring: ["Synthetic ring", "Freeze linked applications, escalate to the fraud team"],
  bot: ["Bot / scripted", "Block device, step-up challenge"],
  injection: ["Injection / replay", "Assisted video KYC"],
  incomplete: ["Verification incomplete", "Run a live selfie (liveness) check before granting full access"],
  none: ["No fraud pattern", "Proceed"],
};
// Aadhaar numbers end in a Verhoeff check digit (same as backend/app/modules/document/checksums.py)
const VD = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
  [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]];
const VP = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],
  [4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]];
const verhoeff = (num) => [...String(num)].reverse().reduce((c, d, i) => VD[c][VP[i % 8][+d]], 0) === 0;
const lookupPan = (p) => { const i = DEMO_IDENTITIES.find((x) => x.pan === String(p).toUpperCase()); return i ? { name: i.name, dob: i.dob, id_last4: i.id_number.slice(-4) } : null; };
const lookupId = (id) => { const i = DEMO_IDENTITIES.find((x) => x.id_number === id); return i ? { name: i.name, dob: i.dob, gender: i.gender, address: i.address } : null; };

const STORE_FILE = path.join(ROOT, ".trueid-local.json");
let store;
try { store = fs.existsSync(STORE_FILE) ? JSON.parse(fs.readFileSync(STORE_FILE, "utf8")) : { apps: [] }; } catch { store = { apps: [] }; }
const save = () => fs.writeFile(STORE_FILE, JSON.stringify(store), () => {});
const lower = (s) => String(s || "").trim().toLowerCase();

function evaluate(p, history) {
  const f = p.form, t = p.telemetry || {}, live = p.liveness || {};
  const codes = [];
  const reg = lookupId(f.id_number);
  if (!reg) codes.push("REG_ID_NOT_FOUND");
  else {
    if (lower(reg.name) !== lower(f.name)) codes.push("REG_NAME_MISMATCH");
    if (reg.dob !== f.dob) codes.push("REG_DOB_MISMATCH");
    if (f.pan) { const pn = lookupPan(f.pan); if (!pn || pn.id_last4 !== f.id_number.slice(-4)) codes.push("REG_PAN_LINK_MISMATCH"); }
  }
  if (history.some((h) => h.applicant._id_full === f.id_number && h.applicant._name_l !== lower(f.name))) codes.push("COR_SHARED_ID");
  const day = Date.now() - 864e5;
  if (p.device?.device_id && history.filter((h) => h.applicant._device === p.device.device_id && Date.parse(h.submitted_at) > day).length >= 3) codes.push("BEH_VELOCITY_DEVICE");
  if (history.some((h) => h.applicant._phone === f.phone && h.applicant._name_l !== lower(f.name))) codes.push("BEH_VELOCITY_PHONE");
  if (typeof t.fill_time === "number" && t.fill_time > 0 && t.fill_time < 20) codes.push("BEH_FAST_FILL");
  if ((t.paste_fields || 0) >= 5) codes.push("BEH_PASTE_HEAVY");
  if (t.iki_mean && t.iki_std !== undefined && t.iki_std / Math.max(t.iki_mean, 1) < 0.15) codes.push("BEH_ROBOTIC_TIMING");
  const performed = live.performed !== false;
  if (live.virtual_camera) codes.push("BIO_VIRTUAL_CAMERA");
  if (!performed) codes.push("BIO_LIVENESS_NOT_PERFORMED");
  else if (!live.passed) codes.push("BIO_LIVENESS_FAIL");

  const reasons = codes.map((c) => ({ module: REASONS[c][0], code: c, text: REASONS[c][1], weight: REASONS[c][2] })).sort((a, b) => b.weight - a.weight);
  const has = (c) => codes.includes(c);
  const type = has("BIO_VIRTUAL_CAMERA") ? "injection"
    : has("COR_SHARED_ID") || has("BEH_VELOCITY_DEVICE") ? "ring"
    : has("BEH_ROBOTIC_TIMING") || (has("BEH_FAST_FILL") && has("BEH_PASTE_HEAVY")) ? "bot"
    : has("REG_ID_NOT_FOUND") ? "third_party"
    : has("REG_NAME_MISMATCH") || has("REG_DOB_MISMATCH") || has("REG_PAN_LINK_MISMATCH") ? "first_party"
    : has("BIO_LIVENESS_FAIL") ? "injection"
    : has("BIO_LIVENESS_NOT_PERFORMED") ? "incomplete" : "none";
  const modRisk = { document: 0.05, biometric: 0.08, behavior: 0.06, registry: 0.04, correlation: 0.02 };
  for (const r of reasons) modRisk[r.module] = Math.min(1, Math.max(modRisk[r.module], 0.15) + r.weight);
  const risk = Math.min(0.97, 0.03 + reasons.reduce((s, r) => s + r.weight, 0) * 0.75);
  const hardReject = ["BIO_VIRTUAL_CAMERA", "COR_SHARED_ID", "REG_NAME_MISMATCH", "REG_DOB_MISMATCH"].some(has);
  const decision = hardReject || risk >= 0.7 ? "REJECT" : risk >= 0.3 || reasons.length ? "REVIEW" : "APPROVE";
  const ft = decision === "APPROVE" ? "none" : type;
  return {
    status: "completed", evaluated_at: new Date().toISOString().slice(0, 19), decision, risk_score: +risk.toFixed(4),
    decision_rules: codes.filter((c) => c === "BIO_LIVENESS_NOT_PERFORMED" || c === "BIO_LIVENESS_FAIL"),
    fraud_type: ft, fraud_label: TYPES[ft][0], recommended_action: TYPES[ft][1], reasons,
    modules: Object.entries(modRisk).map(([module, r]) => ({ module, risk: +r.toFixed(3), simulated: true })),
    summary: "Demo mode: sample verdict from simple rules. Images were not analysed.", analyst_status: "open",
  };
}

function mask(f) {
  const m = { name: f.name, dob: f.dob, gender: f.gender };
  if (f.phone) m.phone = "XXXXXX" + String(f.phone).slice(-4);
  if (f.email) m.email = String(f.email).replace(/^(.).*(@.*)$/, "$1***$2");
  if (f.id_number) m.id_number = "XXXX XXXX " + String(f.id_number).slice(-4);
  if (f.pan) m.pan = f.pan.slice(0, 2) + "XXXXX" + f.pan.slice(-3);
  return m;
}

function localSubmit(p) {
  const id = PARTNER.prefix + crypto.randomBytes(4).toString("hex").toUpperCase();
  store.apps.unshift({
    application_id: id, reference: p.reference || "", partner: PARTNER.id, submitted_at: new Date().toISOString().slice(0, 19),
    profile: PARTNER.profile, partner_checks: p.partner_checks || {}, capture: p.capture || {},
    applicant: { ...mask(p.form), _id_full: p.form.id_number, _name_l: lower(p.form.name), _device: String(p.device?.device_id || ""), _phone: p.form.phone },
    ready_at: Date.now() + 3500, verdict: evaluate(p, store.apps),
  });
  store.apps = store.apps.slice(0, 500);
  save();
  return { application_id: id, status: "processing" };
}
function localView(r) {
  const applicant = Object.fromEntries(Object.entries(r.applicant).filter(([k]) => !k.startsWith("_")));
  const base = { application_id: r.application_id, reference: r.reference, partner: r.partner, submitted_at: r.submitted_at,
    profile: r.profile, partner_checks: r.partner_checks, capture: r.capture, applicant };
  return Date.now() < r.ready_at ? { ...base, status: "processing" } : { ...base, ...r.verdict };
}

// ---------- TrueID calls ----------
const REQUIRED = ["name", "dob", "gender", "id_number", "phone", "email"];
function dataUrlToBlob(u) {
  const m = /^data:([^;]+);base64,(.*)$/.exec(u || "");
  return m ? new Blob([Buffer.from(m[2], "base64")], { type: m[1] }) : null;
}

async function submit(body) {
  const p = body.payload || {};
  const missing = REQUIRED.filter((k) => !String(p.form?.[k] || "").trim());
  if (missing.length) return [422, { detail: `form fields required: ${missing.join(", ")}` }];
  p.device = { ...(p.device || {}), ip: body._ip };
  if ((await mode()) === "local") return [200, localSubmit(p)];
  const card = dataUrlToBlob(body.card), selfie = dataUrlToBlob(body.selfie);
  if (!card || !selfie) return [422, { detail: "card and selfie images are required" }];
  const fd = new FormData();
  fd.append("payload", JSON.stringify(p));
  fd.append("card", card, "card.jpg");
  fd.append("selfie", selfie, "selfie.jpg");
  (body.frames || []).slice(0, 40).map(dataUrlToBlob).filter(Boolean).forEach((b, i) => fd.append("frames", b, `frame${i}.jpg`));
  const r = await remote("/api/partner/v1/applications", { method: "POST", body: fd });
  return [r.status, await r.json()];
}

async function getApp(id) {
  if ((await mode()) === "local") {
    const r = store.apps.find((a) => a.application_id === id);
    return r ? [200, localView(r)] : [404, { detail: "unknown application" }];
  }
  const r = await remote(`/api/partner/v1/applications/${encodeURIComponent(id)}`);
  return [r.status, await r.json()];
}

async function listApps() {
  const m = await mode();
  if (m === "local") return [200, { partner: PARTNER.name, applications: store.apps.map(localView), mode: m }];
  const r = await remote("/api/partner/v1/applications?limit=100");
  return [r.status, { ...(await r.json()), mode: m, backend: TRUEID }];
}

/** Operations analytics. Connected: TrueID's GET /api/partner/v1/analytics (same JSON shape).
 * Demo: computed here from the local store; there is no per-check evidence in demo mode, so `checks` is empty. */
async function analytics(days) {
  const m = await mode();
  if (m === "remote") {
    const r = await remote(`/api/partner/v1/analytics?days=${days}`);
    return [r.status, { ...(await r.json()), mode: m, backend: TRUEID }];
  }
  const since = Date.now() - days * 864e5;
  const apps = store.apps.map(localView).filter((a) => Date.parse(a.submitted_at) >= since);
  const span = Array.from({ length: days }, (_, i) => new Date(Date.now() - (days - 1 - i) * 864e5).toISOString().slice(0, 10));
  const daily = Object.fromEntries(span.map((d) => [d, { APPROVE: 0, REVIEW: 0, REJECT: 0, processing: 0 }]));
  const decisions = { APPROVE: 0, REVIEW: 0, REJECT: 0 }, types = {}, reasons = {}, pchecks = {}, hist = Array(10).fill(0), risks = [];
  for (const a of apps) {
    for (const [k, v] of Object.entries(a.partner_checks || {})) pchecks[k] = (pchecks[k] || 0) + (v ? 1 : 0);
    const day = a.submitted_at.slice(0, 10);
    if (a.status !== "completed") { if (daily[day]) daily[day].processing++; continue; }
    decisions[a.decision]++; if (daily[day]) daily[day][a.decision]++;
    if (a.fraud_type !== "none") types[a.fraud_label] = (types[a.fraud_label] || 0) + 1;
    for (const r of a.reasons) if (r.weight > 0) reasons[r.code] = { code: r.code, text: r.text, count: (reasons[r.code]?.count || 0) + 1 };
    risks.push(a.risk_score); hist[Math.min(9, Math.floor(a.risk_score * 10))]++;
  }
  const done = decisions.APPROVE + decisions.REVIEW + decisions.REJECT, n = apps.length;
  const fraud = Object.entries(types).sort((x, y) => y[1] - x[1]).map(([label, count]) => ({ label, count }));
  return [200, {
    partner: PARTNER.name, days, submitted: n, completed: done, processing: n - done, decisions,
    approval_rate: done ? +(decisions.APPROVE / done).toFixed(4) : null, fraud_flagged: fraud.reduce((s, f) => s + f.count, 0),
    fraud_patterns: fraud, top_reasons: Object.values(reasons).sort((x, y) => y.count - x.count).slice(0, 8), checks: [],
    risk: { histogram: hist, mean: risks.length ? +(risks.reduce((s, x) => s + x, 0) / risks.length).toFixed(4) : null, n: risks.length },
    daily: span.map((d) => ({ date: d, ...daily[d] })), analyst_outcomes: {},
    partner_checks: n ? Object.fromEntries(Object.entries(pchecks).map(([k, v]) => [k, +(v / n).toFixed(4)])) : {}, mode: m,
  }];
}

/** Simulated government sources (NSDL PAN, DigiLocker). Connected mode asks TrueID's partner registry endpoints, which
 * answer from its mock registries; demo mode uses the demo identities. In production the bank calls NSDL itself. */
async function registry(kind, key) {
  if ((await mode()) === "local") return kind === "pan" ? lookupPan(key) : lookupId(key);
  try {
    const r = await remote(`/api/partner/v1/registry/${kind}/${encodeURIComponent(key)}`);
    if (r.status === 503 || r.status === 401) return { unavailable: true, why: (await r.json()).detail };
    return r.ok ? await r.json() : null;
  } catch { return { unavailable: true, why: `TrueID not reachable at ${TRUEID}` }; }
}

/** Head-turn liveness challenge, issued and later verified by TrueID (frames: neutral + one per step).
 * Demo mode makes one up locally; it is never verified there. */
async function challenge() {
  if ((await mode()) === "local") {
    const seq = Math.random() < 0.5 ? ["turn_left", "turn_right"] : ["turn_right", "turn_left"];
    return [200, { challenge_id: "local-" + crypto.randomBytes(8).toString("hex"), sequence: seq, expires_in: 900 }];
  }
  const r = await remote("/api/partner/v1/liveness/challenge", { method: "POST" });
  return [r.status, await r.json()];
}

/** Income Tax "Link Aadhaar status": is this PAN linked to exactly this Aadhaar? */
async function panLink(pan, idNumber) {
  if ((await mode()) === "local") {
    const i = DEMO_IDENTITIES.find((x) => x.pan === String(pan).toUpperCase());
    return { pan_found: !!i, linked: !!i && i.id_number === idNumber };
  }
  try {
    const r = await remote(`/api/partner/v1/registry/pan-link?pan=${encodeURIComponent(pan)}&id_number=${encodeURIComponent(idNumber)}`);
    return r.ok ? await r.json() : { pan_found: false, linked: false, unavailable: true };
  } catch { return { pan_found: false, linked: false, unavailable: true }; }
}

// Same lists as backend/app/modules/document/forensics.py
const GENAI = ["trainedalgorithmicmedia", "algorithmicmedia", "midjourney", "dall-e", "stable diffusion", "stablediffusion",
  "adobe firefly", "gpt-image", "imagen", "flux.1", "ideogram", "leonardo.ai"];
const EDITORS = ["photoshop", "gimp", "canva", "picsart", "snapseed", "pixlr"];

/** Check one uploaded document. Connected: TrueID's POST /api/partner/v1/documents/check (signed-QR check for the ID
 * card; metadata, re-use, legibility and OCR of typed values for the rest). Demo: only what can be done here without
 * TrueID (metadata markers, re-use within this site, the browser's legibility measurement); text checks and the card
 * signature are reported as unavailable, never as passed. */
async function docCheck({ kind, claims = {}, owner = "", file, quality = {} }) {
  const blob = dataUrlToBlob(file);
  if (!blob) return [422, { detail: "file must be an image" }];
  if ((await mode()) === "remote") {
    const fd = new FormData();
    fd.append("kind", kind); fd.append("claims", JSON.stringify(claims)); fd.append("owner", owner);
    fd.append("file", blob, "document.jpg");
    const r = await remote("/api/partner/v1/documents/check", { method: "POST", body: fd });
    return [r.status, await r.json()];
  }
  const raw = Buffer.from(await blob.arrayBuffer());
  const head = raw.subarray(0, 262144).toString("latin1").toLowerCase();
  const c = (check, label, status, detail = "") => ({ check, label, status, detail });
  const checks = [];
  if (kind !== "id_card") {
    const ok = (quality.w || 0) >= 500 && (quality.h || 0) >= 500 && (quality.sharp ?? 999) >= 40;
    checks.push(c("legible", "Clear enough to read", ok ? "PASS" : "FAIL", ok ? "" : "Please retake in good light"));
  } else {
    checks.push(c("doc_signature", "Issuer signature on the card's QR is valid", "UNAVAILABLE", "Demo mode: TrueID checks the card"));
  }
  const gm = GENAI.find((m) => head.includes(m)), ed = EDITORS.find((m) => head.includes(m));
  checks.push(c("ai_marker", "No AI-generator marker in the file", gm ? "FAIL" : "PASS", gm ? `Marker found: ${gm}` : "Metadata checked. Absence is not proof."));
  checks.push(c("editor_tag", "Not saved by photo-editing software", ed ? "FAIL" : "PASS", ed ? `Saved by ${ed}` : ""));
  const sha = crypto.createHash("sha256").update(raw).digest("hex"), who = lower(owner);
  store.docs ??= [];
  const prior = store.docs.find((d) => d.sha === sha && d.owner !== who);
  checks.push(c("reuse", "Not already used by another applicant", prior ? "FAIL" : "PASS", prior ? `Identical image submitted for someone else on ${prior.ts.slice(0, 10)}` : ""));
  if (!store.docs.some((d) => d.sha === sha && d.owner === who)) { store.docs.push({ sha, owner: who, kind, ts: new Date().toISOString() }); save(); }
  for (const [k, v] of Object.entries(claims)) {
    if (kind !== "id_card" && String(v || "").trim()) checks.push(c(`text_${k}`, `${k.replace(/_/g, " ")} printed on the document`, "UNAVAILABLE", "Demo mode: text reading needs TrueID"));
  }
  return [200, { kind, checks, ocr: false, demo: true }];
}

/** What the applicant is allowed to see: never the score or the reasons. */
function applicantView(v) {
  if (v.status !== "completed") return { status: v.status || "processing" };
  return { status: "completed", outcome: v.decision === "APPROVE" ? "approved" : v.decision === "REJECT" ? "declined" : "review" };
}

// ---------- HTTP ----------
const TYPES_MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".ico": "image/x-icon", ".json": "application/json" };
const json = (res, status, obj) => { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }); res.end(JSON.stringify(obj)); };
const readBody = (req) => new Promise((ok, fail) => {
  const chunks = []; let n = 0;
  req.on("data", (c) => { n += c.length; if (n > 25e6) { fail(new Error("too large")); req.destroy(); } else chunks.push(c); });
  req.on("end", () => { try { ok(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}")); } catch (e) { fail(e); } });
  req.on("error", fail);
});
const opsOk = (req) => {
  const a = Buffer.from(String(req.headers["x-ops-passcode"] || "")), b = Buffer.from(OPS);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
};

const PAN_RE = /^[A-Z]{3}P[A-Z]\d{4}[A-Z]$/;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const p = url.pathname;
  try {
    if (p === "/api/mode") return json(res, 200, { mode: await mode(), backend: TRUEID, partner: PARTNER.name });
    // the same test people exist in TrueID once clients/kyc-homeloan/tools/enrol_in_trueid.py has run
    if (p === "/api/demo-identities") return json(res, 200, DEMO_IDENTITIES);

    if (p === "/api/verify/pan" && req.method === "POST") {
      const { pan, dob } = await readBody(req);
      const v = String(pan || "").toUpperCase().trim();
      if (!PAN_RE.test(v)) return json(res, 200, { ok: false, error: "Enter a valid individual PAN, e.g. ABCPK1234Z." });
      const rec = await registry("pan", v);
      if (rec?.unavailable) return json(res, 200, { ok: false, error: `Verification service unavailable: ${rec.why}` });
      if (!rec) return json(res, 200, { ok: false, error: "This PAN is not found in Income Tax records." });
      if (dob && rec.dob !== dob) return json(res, 200, { ok: false, error: "Date of birth does not match PAN records." });
      return json(res, 200, { ok: true, name: rec.name, dob: rec.dob, id_last4: rec.id_last4 });
    }
    if (p === "/api/verify/aadhaar" && req.method === "POST") {
      const { id_number } = await readBody(req);
      const v = String(id_number || "").replace(/\s/g, "");
      if (!/^[2-9]\d{11}$/.test(v)) return json(res, 200, { ok: false, error: "Enter a valid 12-digit Aadhaar number." });
      if (!verhoeff(v)) return json(res, 200, { ok: false, error: "This isn't a valid Aadhaar number (the check digit doesn't match)." });
      const rec = await registry("uidai", v);
      if (rec?.unavailable) return json(res, 200, { ok: false, error: `Verification service unavailable: ${rec.why}` });
      if (!rec) return json(res, 200, { ok: false, error: "Aadhaar number not found." });
      return json(res, 200, { ok: true, name: rec.name, dob: rec.dob, gender: rec.gender, address: rec.address || "" });
    }
    if (p === "/api/liveness/challenge" && req.method === "POST") { const [s, v] = await challenge(); return json(res, s, v); }
    if (p === "/api/verify/pan-link" && req.method === "POST") {
      const { pan, id_number } = await readBody(req);
      return json(res, 200, await panLink(String(pan || "").toUpperCase().trim(), String(id_number || "").replace(/\s/g, "")));
    }
    if (p === "/api/docs/check" && req.method === "POST") { const [s, v] = await docCheck(await readBody(req)); return json(res, s, v); }
    if (p === "/api/kyc/submit" && req.method === "POST") {
      const body = await readBody(req);
      body._ip = String(req.headers["x-forwarded-for"] || req.socket.remoteAddress || "").split(",")[0].trim();
      const [s, out] = await submit(body);
      return json(res, s, s === 200 ? { application_id: out.application_id, status: out.status } : out);
    }
    const st = p.match(/^\/api\/kyc\/status\/([A-Za-z0-9_-]+)$/);
    if (st) { const [s, v] = await getApp(st[1]); return json(res, s, s === 200 ? applicantView(v) : v); }

    if (p.startsWith("/api/ops/")) {
      if (!opsOk(req)) return json(res, 401, { detail: "wrong passcode" });
      if (p === "/api/ops/applications") { const [s, v] = await listApps(); return json(res, s, v); }
      if (p === "/api/ops/analytics") {
        const [s, v] = await analytics(Math.max(1, Math.min(90, parseInt(url.searchParams.get("days") || "14", 10) || 14)));
        return json(res, s, v);
      }
      const one = p.match(/^\/api\/ops\/applications\/([A-Za-z0-9_-]+)$/);
      if (one) { const [s, v] = await getApp(one[1]); return json(res, s, v); }
    }

    if (req.method !== "GET") return json(res, 405, { detail: "method not allowed" });
    let file = path.normalize(path.join(ROOT, "public", p === "/" ? "index.html" : p === "/ops" ? "ops.html" : p));
    if (!file.startsWith(path.join(ROOT, "public"))) return json(res, 403, { detail: "forbidden" });
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");  // a folder's own page
    if (!fs.existsSync(file)) file = path.join(ROOT, "public", "index.html");
    res.writeHead(200, { "Content-Type": TYPES_MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    json(res, 502, { detail: `TrueID unreachable or bad request: ${e.message}` });
  }
});

server.listen(PORT, () => {
  console.log(`${PARTNER.name} KYC replica on http://localhost:${PORT}  (ops console: /ops, passcode ${OPS})`);
  mode().then((m) => console.log(m === "remote" ? `Connected to TrueID Shield at ${TRUEID}` : `Demo mode (TrueID not reachable at ${TRUEID})`));
});
