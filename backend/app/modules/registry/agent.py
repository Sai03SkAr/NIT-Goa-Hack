"""Registry agent (D1): synthetic identities look clean on paper but have no history."""
import time
from datetime import date

import numpy as np

from app import policy as P
from app.modules.correlation.fuzzy import name_sim
from app.modules.document.dates import age_on, parse
from app.modules.registry import mocks
from app.schemas import ModuleResult, reason


def assess(form: dict, today: date) -> ModuleResult:
    t0 = time.time()
    R, f = [], {}
    try:
        u = mocks.uidai(form["id_number"])
        p = mocks.pan(form.get("pan", ""))
        available = True
    except mocks.RegistryUnavailable:  # an outage is not the same thing as "identity not found"
        u = p = None
        available = False
        R.append(reason("REG_UNAVAILABLE", 0.0))
    f["reg_id_found"] = float(u is not None)
    if not available:
        f["reg_name_sim"] = f["reg_dob_match"] = np.nan
        ev_id = P.UNAVAILABLE
    elif u is None:
        R.append(reason("REG_ID_NOT_FOUND", 0.5))
        f["reg_name_sim"], f["reg_dob_match"] = 0.0, 0.0
        ev_id = P.FAIL
    else:
        f["reg_name_sim"] = name_sim(form["name"], u["name"])
        f["reg_dob_match"] = float(parse(form["dob"]) is not None and parse(form["dob"]) == parse(u["dob"]))
        if f["reg_name_sim"] < 0.8:
            R.append(reason("REG_NAME_MISMATCH", 0.35))
        if not f["reg_dob_match"]:
            R.append(reason("REG_DOB_MISMATCH", 0.3))
        ev_id = P.PASS if f["reg_name_sim"] >= 0.8 and f["reg_dob_match"] else P.FAIL
    f["ev_registry_identity"] = P.CODE[ev_id]

    # PAN must belong to this exact subject (full ID, not a 4-digit suffix that collides across people)
    f["reg_pan_found"] = float(p is not None)
    subject_ok = p is not None and p.get("subject") == form["id_number"]
    person_ok = p is not None and name_sim(form["name"], p["name"]) >= 0.8 and parse(p["dob"]) == parse(form["dob"])
    f["reg_pan_link_ok"] = float(subject_ok and person_ok)
    if not available:
        ev_pan = P.UNAVAILABLE
    elif p is None:
        R.append(reason("REG_PAN_NOT_FOUND", 0.2)); ev_pan = P.FAIL
    elif not subject_ok:
        R.append(reason("REG_PAN_LINK_MISMATCH", 0.3)); ev_pan = P.FAIL
    elif not person_ok:
        R.append(reason("REG_PAN_PERSON_MISMATCH", 0.25)); ev_pan = P.FAIL
    else:
        ev_pan = P.PASS
    f["ev_pan_link"] = P.CODE[ev_pan]

    if not available:  # contextual sources unknown: no fabricated "clean" history
        for k in ("reg_sim_age_days", "reg_sim_name_sim", "reg_ckyc", "reg_accounts", "reg_oldest_months",
                  "reg_inquiries", "reg_file_age_ratio", "reg_age"):
            f[k] = np.nan
        f["reg_risk"] = 0.0
        return ModuleResult(module="registry", risk=0.0, confidence=0.0, reasons=R, features=f,
                            latency_ms=int((time.time() - t0) * 1000), evidence={"status": "unavailable"})
    t = mocks.telecom(form.get("phone", ""))
    sim_days = max(0, (today - parse(t["activated"])).days) if t else -1  # registry is a later snapshot
    f["reg_sim_age_days"] = float(sim_days)
    f["reg_sim_name_sim"] = name_sim(form["name"], t["subscriber"]) if t else 0.0
    if 0 <= sim_days < 30:
        R.append(reason("REG_SIM_NEW", 0.25))
    if t and f["reg_sim_name_sim"] < 0.8:
        R.append(reason("REG_SIM_NAME_MISMATCH", 0.1))

    c = mocks.ckyc(form["id_number"])
    f["reg_ckyc"] = float(c is not None)
    if c is None:
        R.append(reason("REG_NO_CKYC", 0.15))

    dob = parse(form["dob"])
    age = age_on(dob, today) if dob else 0.0
    b = mocks.bureau(form["id_number"])
    f["reg_age"] = age
    f["reg_accounts"] = float(b["accounts"]) if b else 0.0
    f["reg_oldest_months"] = float(b["oldest_months"]) if b else 0.0
    f["reg_inquiries"] = float(b["inquiries_90d"]) if b else 0.0
    f["reg_file_age_ratio"] = f["reg_oldest_months"] / max(12 * (age - 18), 12)
    if age > 28 and (b is None or b["oldest_months"] < 24):
        R.append(reason("REG_THIN_FILE", 0.2))
    if b and b["inquiries_90d"] >= 4:
        R.append(reason("REG_INQUIRY_BURST", 0.25))

    risk = min(1.0, sum(r.weight for r in R))
    f["reg_risk"] = risk
    return ModuleResult(module="registry", risk=round(risk, 3), reasons=R, features=f,
                        latency_ms=int((time.time() - t0) * 1000),
                        evidence={"status": "mock registry", "uidai": u, "pan": p, "telecom": t, "ckyc": c, "bureau": b})
