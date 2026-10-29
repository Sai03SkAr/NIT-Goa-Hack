"""Digital-footprint agent: does what the applicant's consented online footprint says agree with their KYC details?

One-sided by design. Only a contradiction counts: a linked account in someone else's name, a profile picture of a
different person, an email address older than its owner's childhood. Having no footprint, a new email or few
accounts is never held against anyone: first-time digital users, older and rural applicants and people who keep
their accounts private would otherwise be pushed out of KYC. Informational: shown to analysts, never decides."""
import time
from datetime import date

from app import policy as P
from app.modules.biometric import face
from app.modules.correlation.fuzzy import name_sim, tokens
from app.modules.document.dates import parse
from app.modules.footprint import provider
from app.schemas import ModuleResult, reason

NOTE = "Informational: shown to analysts, never approves or rejects. Having no footprint never counts against anyone."


def _days(iso: str | None, today: date) -> int | None:
    return None if not iso else max(0, (today - date.fromisoformat(iso)).days)


def depth(email_days, email_services, phone_services, linked_days) -> str:
    services = (email_services or 0) + (phone_services or 0)
    if email_days is None and linked_days is None and not services:
        return "none"
    if (email_days or 0) >= 730 and services >= 3 or (linked_days or 0) >= 730:
        return "established"
    return "thin" if (email_days or 0) < 365 and services < 3 and linked_days is None else "moderate"


def _result(status: str, reasons=(), evidence=None, t0=0.0) -> ModuleResult:
    return ModuleResult(module="footprint", risk=0.0, reasons=list(reasons), features={"ev_footprint": P.CODE[status]},
                        evidence={"policy": NOTE, **(evidence or {})}, latency_ms=int((time.time() - t0) * 1000))


def assess(form: dict, consented: bool, selfie_emb, today: date) -> ModuleResult:
    t0 = time.time()
    if not consented:
        return _result(P.NOT_PROVIDED, evidence={"status": "not consented", "score": None, "checks": []}, t0=t0)
    try:
        fp = provider.lookup(form.get("email"), form.get("phone"))
    except provider.FootprintUnavailable as e:
        return _result(P.UNAVAILABLE, [reason("FP_UNAVAILABLE", 0.0)],
                       {"status": "unavailable", "detail": str(e), "score": None, "checks": []}, t0)
    em, ph, ln = fp["email"], fp["phone"], fp["linked"]
    checks, R = [], []

    def add(check, label, result, detail, code=None):
        checks.append({"check": check, "label": label, "result": result, "detail": detail})
        if result == "contradiction" and code:
            R.append(reason(code, 0.0))

    dob = parse(form.get("dob"))
    if em and dob:  # an address cannot be older than its owner's 10th birthday
        first = date.fromisoformat(em["first_seen"])
        ok = first.year - dob.year - ((first.month, first.day) < (dob.month, dob.day)) >= 10
        add("email_timeline", "Email address is younger than its owner", "consistent" if ok else "contradiction",
            f"first seen {em['first_seen']}, applicant born {dob.isoformat()}", "FP_EMAIL_PREDATES_APPLICANT")
    if ln:
        s = name_sim(form["name"], ln["name"])
        kyc, own = tokens(form["name"]), tokens(ln["name"])
        partial = 0 < len(own) < len(kyc) and all(any(k == o or (len(o) == 1 and k[0] == o) for k in kyc) for o in own)
        add("linked_name", f"Name on the linked {ln['provider'].title()} account matches the KYC name",
            "consistent" if s >= 0.8 else "partial" if partial else "contradiction",
            f"account name '{ln['name']}' (similarity {s:.2f})", "FP_LINKED_NAME_MISMATCH")
        if ln.get("photo_emb") is not None and selfie_emb is not None:
            fs = face.sim(selfie_emb, ln["photo_emb"])
            add("linked_photo", "Profile picture on the linked account is the person in the selfie",
                "consistent" if fs >= face.threshold() else "contradiction",
                f"face similarity {fs:.2f} (match at {face.threshold():.2f})", "FP_LINKED_PHOTO_MISMATCH")

    ran = [c for c in checks if c["result"] != "partial"]
    bad = [c for c in ran if c["result"] == "contradiction"]
    e_days, l_days = _days(em and em["first_seen"], today), _days(ln and ln.get("created"), today)
    facts = {"email_age_days": e_days, "email_services": em and em["services"],
             "phone_age_days": _days(ph and ph["first_seen"], today), "phone_services": ph and ph["services"],
             "linked": ln and {"provider": ln["provider"], "name": ln["name"], "account_age_days": l_days,
                               "has_photo": ln.get("photo_emb") is not None}}
    notes = []
    if e_days is not None and e_days < 30:
        notes.append("Email address first seen in the last 30 days. Context only: many genuine applicants create one to apply.")
    if l_days is not None and l_days < 30:
        notes.append("Linked account created in the last 30 days. Context only.")
    status = P.FAIL if bad else (P.PASS if ran else P.NOT_PROVIDED)
    return _result(status, R, {
        "status": "consented" if (em or ph or ln) else "no record", "provider": "simulated",
        "score": round(100 * (len(ran) - len(bad)) / len(ran)) if ran else None,
        "depth": depth(e_days, em and em["services"], ph and ph["services"], l_days),
        "checks": checks, "contradictions": len(bad), "facts": facts, "notes": notes}, t0)
