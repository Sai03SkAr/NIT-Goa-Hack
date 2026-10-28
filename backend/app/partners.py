"""Partner (client) API: lets a bank or wallet run its OWN onboarding form and send the evidence to TrueID Shield.

    POST /api/partner/v1/applications          multipart: payload (JSON) + card + selfie [+ frames]
    GET  /api/partner/v1/applications          this partner's applications, newest first
    GET  /api/partner/v1/applications/{id}     verdict for one application (status=processing until done)

Every call carries `X-Partner-Key`. Keys live server-side only (the partner's own backend calls us; a browser never
sees the key). Local-demo keys are below; override with TRUEID_PARTNER_KEYS='{"northstar": "...", "paylite": "..."}'.

`partner_checks` records what the PARTNER says it verified (OTP, DigiLocker, liveness...). They are shown to the
partner's operations team as their own controls and never count as TrueID evidence: an unverified client claim cannot
lower risk. What does change TrueID's evidence is `liveness.performed = false`: a partner that never ran a live
selfie check cannot be auto-approved (see BIO_LIVENESS_NOT_PERFORMED in fusion.model.hard_rules).
"""
import hmac
import json
import os
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel, select

from app import db
from app.schemas import REASONS

router = APIRouter(prefix="/api/partner/v1", tags=["partner API"])

PARTNERS: dict[str, dict] = {
    "northstar": {"name": "Northstar Bank", "profile": "full_kyc", "key": "ns_test_7f3c9a2e5b81",
                  "prefix": "N"},
    "paylite": {"name": "PayLite Wallet", "profile": "minimum_kyc", "key": "pl_test_41d8e0c6aa27",
                "prefix": "P"},
}
_override = os.environ.get("TRUEID_PARTNER_KEYS")
if _override:
    for pid, key in json.loads(_override).items():
        if pid in PARTNERS:
            PARTNERS[pid]["key"] = key

FAILED: dict[str, str] = {}  # app_id -> pipeline error, so a partner is not left polling forever
REQUIRED = ("name", "dob", "gender", "id_number", "phone", "email")


class PartnerApplication(SQLModel, table=True):
    app_id: str = Field(primary_key=True)
    partner_id: str = Field(index=True)
    reference: str = ""                       # the partner's own application number
    created: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    profile: str = ""
    partner_checks: dict = Field(default_factory=dict, sa_column=Column(JSON))
    capture: dict = Field(default_factory=dict, sa_column=Column(JSON))
    applicant: dict = Field(default_factory=dict, sa_column=Column(JSON))   # masked, for the partner's console


def _partner(key: str | None) -> str:
    for pid, p in PARTNERS.items():
        if key and hmac.compare_digest(key.encode(), p["key"].encode()):
            return pid
    raise HTTPException(401, "missing or invalid X-Partner-Key")


def _client_ip(request: Request, claimed: str | None) -> str:
    """The partner's backend forwards the applicant IP it observed; fall back to the socket peer."""
    return (claimed or (request.client.host if request.client else "") or "").strip()


@router.post("/applications")
async def create(request: Request, payload: str = Form(...), card: UploadFile = File(...),
                 selfie: UploadFile = File(...), frames: list[UploadFile] = File(default=[]),
                 x_partner_key: str | None = Header(default=None)):
    pid = _partner(x_partner_key)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(422, "payload must be JSON")
    form = data.get("form") or {}
    missing = [k for k in REQUIRED if not str(form.get(k) or "").strip()]
    if missing:
        raise HTTPException(422, f"form fields required: {', '.join(missing)}")
    if len(frames) > 8:
        raise HTTPException(422, "at most 8 liveness frames")

    liveness = dict(data.get("liveness") or {})
    liveness.setdefault("performed", bool(frames) or bool(liveness.get("challenges")))
    if not liveness["performed"]:
        liveness["passed"] = False
    device = dict(data.get("device") or {})
    device["ip"] = _client_ip(request, device.get("ip"))
    device.setdefault("camera_labels", [])

    from app.main import start_job  # late import: main imports this module
    app_id = start_job({"form": form, "device": device, "telemetry": data.get("telemetry") or {},
                        "liveness": liveness, "source": f"partner:{pid}"},
                       await card.read(), await selfie.read(), [await f.read() for f in frames],
                       prefix=PARTNERS[pid]["prefix"],
                       extra={"partner": {"id": pid, "reference": data.get("reference", "")}})
    with db.session() as s:
        s.add(PartnerApplication(app_id=app_id, partner_id=pid, reference=str(data.get("reference", ""))[:64],
                                 profile=PARTNERS[pid]["profile"], partner_checks=data.get("partner_checks") or {},
                                 capture=data.get("capture") or {}, applicant=db.mask_form(form)))
        s.commit()
    return {"application_id": app_id, "status": "processing",
            "status_url": f"/api/partner/v1/applications/{app_id}"}


def _verdict(pa: PartnerApplication, app: db.Application | None) -> dict:
    out = {"application_id": pa.app_id, "reference": pa.reference, "partner": pa.partner_id,
           "submitted_at": pa.created, "profile": pa.profile, "partner_checks": pa.partner_checks,
           "capture": pa.capture, "applicant": pa.applicant}
    if app is None:
        if pa.app_id in FAILED:
            return out | {"status": "error", "error": FAILED[pa.app_id]}
        return out | {"status": "processing"}
    reasons, modules = [], []
    for m in app.modules or []:
        modules.append({"module": m["module"], "risk": m.get("risk", 0), "simulated": m.get("simulated", False)})
        for r in m.get("reasons", []):
            reasons.append({"module": m["module"], "code": r["code"], "text": r.get("text") or REASONS.get(r["code"], r["code"]),
                            "weight": r.get("weight", 0)})
    reasons.sort(key=lambda r: -r["weight"])
    return out | {
        "status": "completed", "evaluated_at": app.ts,
        "decision": app.band,                       # APPROVE | REVIEW | REJECT
        "risk_score": round(app.prob, 4),
        "decision_rules": app.rule_codes or [],     # hard rules that fixed the band, if any
        "fraud_type": app.fraud_type, "fraud_label": app.fraud_label, "recommended_action": app.action,
        "reasons": reasons, "modules": modules, "summary": app.summary,
        "analyst_status": app.status,
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
