"""Registry agent (D1): synthetic identities look clean on paper but have no history."""
import time
from datetime import date

from app.modules.correlation.fuzzy import name_sim
from app.modules.document.dates import age_on, parse
from app.modules.registry import mocks
from app.schemas import ModuleResult, reason


def assess(form: dict, today: date) -> ModuleResult:
    t0 = time.time()
    R, f = [], {}
    u = mocks.uidai(form["id_number"])
    f["reg_id_found"] = float(u is not None)
    if u is None:
        R.append(reason("REG_ID_NOT_FOUND", 0.5))
        f["reg_name_sim"], f["reg_dob_match"] = 0.0, 0.0
    else:
        f["reg_name_sim"] = name_sim(form["name"], u["name"])
        f["reg_dob_match"] = float(form["dob"] == u["dob"])
        if f["reg_name_sim"] < 0.8:
            R.append(reason("REG_NAME_MISMATCH", 0.35))
        if not f["reg_dob_match"]:
            R.append(reason("REG_DOB_MISMATCH", 0.3))

    p = mocks.pan(form.get("pan", ""))
    f["reg_pan_found"] = float(p is not None)
    f["reg_pan_link_ok"] = float(p is not None and p["id_last4"] == form["id_number"][-4:])
    if p is None or not f["reg_pan_link_ok"]:
        R.append(reason("REG_PAN_LINK_MISMATCH", 0.2))

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
                        evidence={"uidai": u, "pan": p, "telecom": t, "ckyc": c, "bureau": b})
