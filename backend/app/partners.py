"""Partner (client) API: lets a bank or wallet run its OWN onboarding form and send the evidence to TrueID Shield.

    POST /api/partner/v1/liveness/challenge    a one-time head-turn challenge (same as the applicant flow)
    POST /api/partner/v1/applications          multipart: payload (JSON) + card + selfie [+ frames]
    GET  /api/partner/v1/applications          this partner's applications, newest first
    GET  /api/partner/v1/applications/{id}     verdict for one application (status=processing until done)
    GET  /api/partner/v1/registry/pan/{pan}    simulated NSDL PAN lookup (mock registry)
    GET  /api/partner/v1/registry/uidai/{id}   simulated DigiLocker / e-KYC lookup (mock registry)
    GET  /api/partner/v1/registry/pan-link     is this PAN linked to this Aadhaar (Income Tax link status)
    POST /api/partner/v1/documents/check       check one document as it is uploaded (ID card or supporting document)
    GET  /api/partner/v1/analytics             this partner's operations analytics
    POST /api/partner/v1/consortium/check      cross-institution check with locally hashed identifiers (no PII)
    POST /api/partner/v1/consortium/report     share an outcome for locally hashed identifiers
    GET  /api/partner/v1/consortium/stats      network size (members, signals)

Every call carries `X-Partner-Key` (checked in security.py, deny by default). Keys live server-side only: the partner's
own backend calls us, a browser never sees the key. Local-demo keys are below; override with
TRUEID_PARTNER_KEYS='{"northstar": "...", "tideway": "..."}'.

Liveness is decided exactly as for /api/apply (app/policy.py): only frames answering a challenge this server issued
count. A partner that sends no challenge_id (an uploaded selfie, or its own client-side check) gets liveness
NOT_PROVIDED, so the case can never be auto-approved. `partner_checks` records what the PARTNER says it verified
(OTP, DigiLocker...). They are shown back to the partner's operations team and never count as TrueID evidence."""
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from pydantic import Field as PField
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, select

from app import consortium, db, learning, liveness_sessions
from app.modules.document import supporting  # noqa: F401  registers the DocPrint table before db.init()
from app.config import MAX_PAYLOAD_BYTES, PARTNER_CHALLENGE_TTL_S
from app.schemas import code_text

router = APIRouter(prefix="/api/partner/v1", tags=["partner API"])

PARTNERS: dict[str, dict] = {
    "northstar": {"name": "Northstar Bank", "profile": "full_kyc", "key": "ns_test_7f3c9a2e5b81",
                  "prefix": "N"},
    "paylite": {"name": "PayLite Wallet", "profile": "minimum_kyc", "key": "pl_test_41d8e0c6aa27",
                "prefix": "P"},
    # KYC-only replicas (clients/kyc-zerodha-style, clients/kyc-hdfc-insta-style)
    "tideway": {"name": "Tideway Securities", "profile": "full_kyc", "key": "tw_test_9c2e61b07d4a",
                "prefix": "T"},
    "meridian": {"name": "Meridian Bank", "profile": "limited_kyc", "key": "mb_test_5a17f3c8e260",
                 "prefix": "M"},
    # home-loan KYC (clients/kyc-homeloan): the most documents in one journey
    "kestrel": {"name": "Kestrel Home Finance", "profile": "lending_full_kyc", "key": "kh_test_3e8d14b9c702",
                "prefix": "K"},
}
_override = os.environ.get("TRUEID_PARTNER_KEYS")
if _override:
    for pid, key in json.loads(_override).items():
        if pid in PARTNERS:
            PARTNERS[pid]["key"] = key


class PartnerApplication(SQLModel, table=True):
    app_id: str = Field(primary_key=True)
    partner_id: str = Field(index=True)
    reference: str = ""                       # the partner's own application number
    created: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    profile: str = ""
    partner_checks: dict = Field(default_factory=dict, sa_column=Column(JSON))
    capture: dict = Field(default_factory=dict, sa_column=Column(JSON))
    applicant: dict = Field(default_factory=dict, sa_column=Column(JSON))   # masked, for the partner's console


def partner_of(key: str | None) -> str | None:
    for pid, p in PARTNERS.items():
        if key and hmac.compare_digest(key.encode(), p["key"].encode()):
            return pid
    return None


def _partner(key: str | None) -> str:
    pid = partner_of(key)
    if pid is None:
        raise HTTPException(401, "missing or invalid X-Partner-Key")
    return pid


def _session(pid: str) -> str:
    """Liveness challenges are bound to a session; a partner's backend is one session per partner."""
    return f"partner:{pid}"


@router.post("/liveness/challenge")
def challenge(x_partner_key: str | None = Header(default=None)):
    return liveness_sessions.issue(_session(_partner(x_partner_key)), PARTNER_CHALLENGE_TTL_S)


def _geo(M, data: dict) -> dict | None:
    """RBI V-CIP geo-tag, same shape as /api/apply ({lat, lng, accuracy, ts}). Accepts it at the top level, or as
    device.geo {lat, lon|lng, acc|accuracy} as the partner sites send it. Informational in the policy, never gating."""
    g = data.get("geo") or (data.get("device") or {}).get("geo")
    if not g:
        return None
    g = {"lat": g.get("lat"), "lng": g.get("lng", g.get("lon")), "accuracy": g.get("accuracy", g.get("acc")), "ts": g.get("ts")}
    return M.Geo.model_validate(g).model_dump()


@router.post("/applications")
async def create(request: Request, payload: str = Form(..., max_length=MAX_PAYLOAD_BYTES), card: UploadFile = File(...),
                 selfie: UploadFile = File(...), frames: list[UploadFile] = File(default=[]),
                 x_partner_key: str | None = Header(default=None)):
    from app import main as M  # late import: main imports this module
    pid = _partner(x_partner_key)
    try:
        data = json.loads(payload)
        form = M.FormIn.model_validate(data.get("form") or {})
        device = M.DeviceIn.model_validate(data.get("device") or {})
        tele = M.TelemetryIn.model_validate(data.get("telemetry") or {})
        geo = _geo(M, data)
    except json.JSONDecodeError:
        raise HTTPException(422, "payload must be JSON")
    except ValidationError as e:
        raise HTTPException(422, [{"field": ".".join(map(str, x["loc"])), "msg": x["msg"]} for x in e.errors()][:10])
    if len(frames) > M.MAX_FRAMES:
        raise HTTPException(422, f"at most {M.MAX_FRAMES} liveness frames")
    with M._jobs_lock:
        M._sweep_jobs()
        if M._active() >= M.MAX_ACTIVE_JOBS:
            return JSONResponse({"detail": "busy: too many checks running, retry shortly"}, status_code=503,
                                headers={"Retry-After": "10"})
    card_raw, card_img = await M._read_image(card, "card")
    selfie_raw, selfie_img = await M._read_image(selfie, "selfie")
    frame_imgs = [(await M._read_image(f, "liveness frame"))[1] for f in frames]
    challenge = None
    if data.get("challenge_id"):  # consumed exactly once, even if the frames turn out to be bad
        c, st = liveness_sessions.consume(str(data["challenge_id"])[:64], _session(pid))
        challenge = {"status": st, "sequence": c["sequence"] if c else []}

    app_id = PARTNERS[pid]["prefix"] + uuid.uuid4().hex[:8].upper()
    (M.UPLOADS / f"{app_id}_card.jpg").write_bytes(card_raw)
    (M.UPLOADS / f"{app_id}_selfie.jpg").write_bytes(selfie_raw)
    now = datetime.now().isoformat(timespec="seconds")
    claimed_ip = str((data.get("device") or {}).get("ip") or "")[:45] or None  # the partner's backend saw the applicant
    a = {"app_id": app_id, "ts": now, "source": f"partner:{pid}",
         "form": form.model_dump(), "device": device.model_dump() | {"ip": claimed_ip},
         "telemetry": {k: v for k, v in tele.model_dump().items() if v is not None},
         "challenge": challenge, "consent": {"accepted": True, "by": f"partner:{pid}", "ts": now}, "geo": geo,
         "card_sha256": hashlib.sha256(card_raw).hexdigest(), "selfie_sha256": hashlib.sha256(selfie_raw).hexdigest(),
         "card_path": f"/uploads/{app_id}_card.jpg", "selfie_path": f"/uploads/{app_id}_selfie.jpg",
         "partner": {"id": pid, "reference": str(data.get("reference", ""))[:64]}}
    job = M.Job(app_id, _session(pid))
    with M._jobs_lock:
        M.JOBS[app_id] = job
    with db.session() as s:
        s.add(PartnerApplication(app_id=app_id, partner_id=pid, reference=a["partner"]["reference"],
                                 profile=PARTNERS[pid]["profile"], partner_checks=data.get("partner_checks") or {},
                                 capture=data.get("capture") or {}, applicant=db.mask_form(a["form"])))
        s.commit()
    M.EXECUTOR.submit(M.run_job, job, {"app": a, "card_bgr": card_img, "card_raw": card_raw, "selfie_bgr": selfie_img,
                                       "selfie_raw": selfie_raw, "frames": frame_imgs})
    return {"application_id": app_id, "status": "processing",
            "status_url": f"/api/partner/v1/applications/{app_id}"}


def _verdict(pa: PartnerApplication, app: db.Application | None) -> dict:
    out = {"application_id": pa.app_id, "reference": pa.reference, "partner": pa.partner_id,
           "submitted_at": pa.created, "profile": pa.profile, "partner_checks": pa.partner_checks,
           "capture": pa.capture, "applicant": pa.applicant}
    if app is None:
        from app.main import JOBS
        job = JOBS.get(pa.app_id)
        err = next((e for e in (job.events if job else []) if e.get("node") == "error"), None)
        if err or (job is None or job.done):  # finished without a stored decision, or lost on restart
            return out | {"status": "error", "error": (err or {}).get("error", "check did not complete")}
        return out | {"status": "processing"}
    reasons, modules = [], []
    for m in app.modules or []:
        modules.append({"module": m["module"], "risk": m.get("risk", 0), "simulated": m.get("simulated", False)})
        for r in m.get("reasons", []):
            reasons.append({"module": m["module"], "code": r["code"], "text": r.get("text") or code_text(r["code"]),
                            "weight": r.get("weight", 0)})
    reasons.sort(key=lambda r: -r["weight"])
    return out | {
        "status": "completed", "evaluated_at": app.ts,
        "decision": app.band,                       # APPROVE | REVIEW | REJECT
        "risk_score": None if app.prob is None else round(app.prob, 4),
        "decision_rules": app.rule_codes or [],     # policy codes that fixed the band, if any
        "fraud_type": app.fraud_type, "fraud_label": app.fraud_label, "recommended_action": app.action,
        "reasons": reasons, "modules": modules, "summary": app.summary,
        "evidence": [{k: e.get(k) for k in ("check", "label", "status", "required", "source")} for e in app.evidence or []],
        "model_status": app.model_status, "policy_version": app.policy_version,
        "analyst_status": app.status,
        # safe to show the applicant: fixable issues only, never fraud signals (see app/learning.py)
        "applicant_coaching": learning.tips_for(app),
    }


@router.get("/applications/{app_id}")
def get_one(app_id: str, x_partner_key: str | None = Header(default=None)):
    pid = _partner(x_partner_key)
    with db.session() as s:
        pa = s.get(PartnerApplication, app_id)
        if pa is None or pa.partner_id != pid:  # never reveal another partner's applications
            raise HTTPException(404, "unknown application")
        return _verdict(pa, s.get(db.Application, app_id))


@router.get("/applications")
def list_mine(limit: int = 50, x_partner_key: str | None = Header(default=None)):
    pid = _partner(x_partner_key)
    with db.session() as s:
        rows = s.exec(select(PartnerApplication).where(PartnerApplication.partner_id == pid)
                      .order_by(PartnerApplication.created.desc()).limit(max(1, min(limit, 200)))).all()
        return {"partner": PARTNERS[pid]["name"], "applications": [_verdict(r, s.get(db.Application, r.app_id)) for r in rows]}


def analytics_of(rows: list[tuple["PartnerApplication", db.Application | None]], days: int) -> dict:
    """Aggregates for a partner's operations dashboard. Pure function over (partner row, decision row) pairs so the
    tests can feed it directly. Risk is the model probability (None when the model was unavailable)."""
    from collections import Counter
    from datetime import date, timedelta
    today = date.today()
    span = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    daily = {d: {"APPROVE": 0, "REVIEW": 0, "REJECT": 0, "processing": 0} for d in span}
    decisions, types, reasons, analyst, pchecks = Counter(), Counter(), Counter(), Counter(), Counter()
    reason_text, checks = {}, {}
    risks, n_done = [], 0
    for pa, app in rows:
        day = pa.created[:10]
        for k, v in (pa.partner_checks or {}).items():
            pchecks[k] += bool(v)
        if app is None:
            if day in daily:
                daily[day]["processing"] += 1
            continue
        n_done += 1
        decisions[app.band] += 1
        if day in daily:
            daily[day][app.band] += 1
        if app.fraud_type not in ("none", ""):
            types[app.fraud_label or app.fraud_type] += 1
        analyst[app.status] += 1
        if app.prob is not None:
            risks.append(float(app.prob))
        for m in app.modules or []:
            for r in m.get("reasons", []):
                if r.get("weight", 0) > 0:
                    reasons[r["code"]] += 1
                    reason_text[r["code"]] = r.get("text") or code_text(r["code"])
        for e in app.evidence or []:
            c = checks.setdefault(e["check"], {"check": e["check"], "label": e.get("label", e["check"]), "PASS": 0, "FAIL": 0, "OTHER": 0})
            c[e["status"] if e.get("status") in ("PASS", "FAIL") else "OTHER"] += 1
    hist = [0] * 10
    for p in risks:
        hist[min(9, int(p * 10))] += 1
    n = len(rows)
    return {
        "days": days, "submitted": n, "completed": n_done, "processing": n - n_done,
        "decisions": {b: decisions[b] for b in ("APPROVE", "REVIEW", "REJECT")},
        "approval_rate": round(decisions["APPROVE"] / n_done, 4) if n_done else None,
        "fraud_flagged": sum(types.values()),  # completed cases TrueID tied to a fraud pattern (incl. incomplete evidence)
        "fraud_patterns": [{"label": k, "count": v} for k, v in types.most_common()],
        "top_reasons": [{"code": k, "text": reason_text[k], "count": v} for k, v in reasons.most_common(8)],
        "checks": sorted(checks.values(), key=lambda c: -(c["FAIL"] + c["OTHER"])),
        "risk": {"histogram": hist, "mean": round(sum(risks) / len(risks), 4) if risks else None, "n": len(risks)},
        "daily": [{"date": d, **v} for d, v in daily.items()],
        "analyst_outcomes": dict(analyst),
        "partner_checks": {k: round(v / n, 4) for k, v in pchecks.items()} if n else {},
    }


@router.get("/analytics")
def analytics(days: int = 14, x_partner_key: str | None = Header(default=None)):
    """Operations analytics for this partner only: decisions, fraud patterns, top reasons, check pass rates, risk."""
    from datetime import date, timedelta
    pid = _partner(x_partner_key)
    days = max(1, min(days, 90))
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    with db.session() as s:
        rows = s.exec(select(PartnerApplication).where(PartnerApplication.partner_id == pid,
                                                       PartnerApplication.created >= since)).all()
        pairs = [(r, s.get(db.Application, r.app_id)) for r in rows]
        return {"partner": PARTNERS[pid]["name"]} | analytics_of(pairs, days)


# ------------------------------------------------------------------ cross-institution fraud network (app/consortium.py)
# For members that run their own KYC: they hash identifiers locally with the consortium key (scripts/consortium_client.py)
# and send only tokens. Applications sent through /applications are checked and recorded automatically.
_TOKEN = re.compile(r"^[0-9a-f]{40}$")


class NetTokens(BaseModel):
    tokens: dict[str, str] = PField(default_factory=dict)
    name_token: str = PField(default="", max_length=40)
    outcome: str = PField(default="", pattern=r"^(|APPROVE|REVIEW|REJECT)$")
    ref: str = PField(default="", max_length=64)

    def clean(self) -> dict:
        bad = [k for k, v in self.tokens.items() if k not in consortium.KINDS or not _TOKEN.match(v)]
        if bad or (self.name_token and not _TOKEN.match(self.name_token)):
            raise HTTPException(422, f"tokens must be 40-hex HMACs for kinds {', '.join(consortium.KINDS)}; bad: {bad}")
        return self.tokens


@router.post("/consortium/check")
def consortium_check(body: NetTokens, x_partner_key: str | None = Header(default=None)):
    """Counts only: never which institution matched, nor anything it submitted."""
    return consortium.check(_partner(x_partner_key), body.clean(), body.name_token)


@router.post("/consortium/report")
def consortium_report(body: NetTokens, x_partner_key: str | None = Header(default=None)):
    consortium.record(_partner(x_partner_key), body.clean(), body.name_token, outcome=body.outcome, ref=body.ref)
    return {"recorded": True}


@router.get("/consortium/stats")
def consortium_stats(x_partner_key: str | None = Header(default=None)):
    _partner(x_partner_key)
    return consortium.stats()


# ------------------------------------------------------------------ simulated government sources for partners
# In production the bank calls NSDL / DigiLocker itself. Here they answer from TrueID's mock registries, returning only
# what those services would give the bank (no issuer photo, no other registries).
def _lookup(fn, key: str):
    """A registry that has not been built is an outage (503), never 'not found'."""
    from app.modules.registry import mocks
    try:
        return fn(key)
    except mocks.RegistryUnavailable:
        raise HTTPException(503, "TrueID's mock registries are not built yet (run the build, then the partner enrolment)")


@router.get("/registry/pan/{pan}")
def registry_pan(pan: str, x_partner_key: str | None = Header(default=None)):
    from app.modules.registry import mocks
    _partner(x_partner_key)
    r = _lookup(mocks.pan, pan)
    if not r:
        raise HTTPException(404, "not found")
    # NSDL's verification response says whether the PAN is Aadhaar-seeded; the last 4 digits stand in for that here
    return {"name": r["name"], "dob": r["dob"], "id_last4": str(r.get("subject", ""))[-4:] or None}


@router.get("/registry/pan-link")
def registry_pan_link(pan: str, id_number: str, x_partner_key: str | None = Header(default=None)):
    """Income Tax 'Link Aadhaar status': is this PAN linked to exactly this Aadhaar number?"""
    from app.modules.registry import mocks
    _partner(x_partner_key)
    r = _lookup(mocks.pan, pan)
    return {"pan_found": r is not None, "linked": bool(r) and r.get("subject") == id_number}


@router.post("/documents/check")
async def documents_check(kind: str = Form(...), claims: str = Form("{}", max_length=4096), owner: str = Form("", max_length=120),
                          file: UploadFile = File(...), x_partner_key: str | None = Header(default=None)):
    """Check one document at the step where the applicant uploads it.
    kind=id_card: TrueID's document module (signed QR, QR vs print, card vs claims {name, dob, id_number, pan}).
    Other kinds (electricity_bill, salary_slip, bank_statement, cheque): metadata integrity, re-use by another
    applicant, legibility, and OCR presence of each claimed value. `owner` is the applicant's name (for re-use)."""
    from starlette.concurrency import run_in_threadpool
    from app import main as M
    from app.modules.document import supporting as SD
    pid = _partner(x_partner_key)
    if kind != "id_card" and kind not in SD.KINDS:
        raise HTTPException(422, f"kind must be id_card or one of {', '.join(SD.KINDS)}")
    try:
        c = json.loads(claims or "{}")
        assert isinstance(c, dict)
    except (json.JSONDecodeError, AssertionError):
        raise HTTPException(422, "claims must be a JSON object")
    raw, img = await M._read_image(file, KIND_LABEL.get(kind, "document"))
    who = SD.owner_key(owner)
    if kind == "id_card":
        form = {"name": str(c.get("name", "")), "dob": str(c.get("dob", "")), "id_number": str(c.get("id_number", "")),
                "pan": str(c.get("pan", ""))}
        return await run_in_threadpool(SD.check_id_card, raw, img, form, who, pid)
    return await run_in_threadpool(SD.check_supporting, kind, raw, img, {k: str(v)[:80] for k, v in c.items()}, who, pid)


KIND_LABEL = {"id_card": "ID card", "electricity_bill": "electricity bill", "salary_slip": "salary slip",
              "bank_statement": "bank statement", "cheque": "cheque"}


@router.get("/registry/uidai/{id_number}")
def registry_uidai(id_number: str, x_partner_key: str | None = Header(default=None)):
    from app.modules.registry import mocks
    _partner(x_partner_key)
    r = _lookup(mocks.uidai, id_number)
    if not r:
        raise HTTPException(404, "not found")
    return {k: r[k] for k in ("name", "dob", "gender", "address") if k in r}
