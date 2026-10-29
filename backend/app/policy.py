"""The single decision policy, shared by the live pipeline, seeding, the Attack Lab and offline evaluation.

Rule 1: APPROVE requires every required check to PASS. Missing, contradictory, unavailable or simulated evidence is
        never treated as a successful check.
Rule 2: model probability, evidence status, policy decision, analyst disposition and ground truth stay separate.
        The policy never edits the model probability; it only chooses the band.

Evidence statuses travel as `ev_*` features (excluded from the model) so every path computes them identically."""
import math

from app.config import BANDS, POLICY_VERSION

PASS, FAIL, UNAVAILABLE, NOT_PROVIDED, SIMULATED = "PASS", "FAIL", "UNAVAILABLE", "NOT_PROVIDED", "SIMULATED"
CODE = {PASS: 1.0, FAIL: 0.0, UNAVAILABLE: -1.0, NOT_PROVIDED: -2.0, SIMULATED: -3.0}
STATUS = {v: k for k, v in CODE.items()}

# check -> (plain description, source). Every one of these must PASS before automatic approval.
REQUIRED = {
    "doc_signature": ("Issuer signature on the card's QR", "server"),
    "doc_consistency": ("Signed QR agrees with the printed card", "server"),
    "form_consistency": ("Form agrees with the card", "server"),
    "id_format": ("ID number checksum", "server"),
    "face_card": ("Selfie matches the card photo", "server"),
    "face_registry": ("Selfie matches the issuer's photo", "mock registry"),
    "liveness": ("Server-verified head-turn challenge", "server"),
    "registry_identity": ("Identity found and consistent in the issuer registry", "mock registry"),
    "pan_link": ("Tax ID linked to this identity", "mock registry"),
    "capture_quality": ("Photos clear enough to judge", "server"),
    "camera_hint": ("No virtual camera reported", "client-reported"),
    "media_integrity": ("Photos are new and carry no AI-generator marker", "server"),
    "device_network": ("Device has not onboarded several other people this week", "server"),
}
INFORMATIONAL = {"voice": ("Voice step-up", "simulated"),
                 "location": ("GPS location captured for the session (RBI V-CIP geo-tag)", "client-reported"),
                 "ip_region": ("Applicant network location", "server"),
                 "network": ("No conflict in the cross-institution fraud network (hashed identifiers)", "consortium"),
                 # explains and monitors, never decides (docs/IDRBT_INNOVATION.md: as a gate it held more genuine
                 # applicants without catching more fraud, so it stays outside the decision rules and POLICY_VERSION)
                 "profile": ("Inside the patterns learnt from genuine applicants (one-class rules)", "server")}


def status(feats: dict, check: str) -> str:
    v = feats.get(f"ev_{check}")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return NOT_PROVIDED  # an absent check is incomplete evidence, never success
    return STATUS.get(float(v), UNAVAILABLE)


def finite(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def band_of(p: float, bands=None) -> str:
    b = bands or BANDS
    return "APPROVE" if p < b["approve_below"] else ("REJECT" if p >= b["reject_at"] else "REVIEW")


def capture_quality(f: dict) -> str:
    """Too blurry/noisy a selfie or a barely readable card means 'retake', never an automatic fraud verdict.
    Genuine training uploads: selfie sharpness p1 27.5, p99.5 660; card OCR confidence p1 0.77."""
    sharp, conf = f.get("bio_blur"), f.get("doc_ocr_conf")
    if not finite(sharp) and not finite(conf):
        return NOT_PROVIDED
    bad_selfie = finite(sharp) and (float(sharp) < 20 or float(sharp) > 2000)
    bad_card = finite(conf) and float(conf) < 0.70
    return FAIL if (bad_selfie or bad_card) else PASS


def media_integrity(f: dict) -> str:
    if f.get("meta_genai_card") == 1 or f.get("meta_genai_selfie") == 1:
        return FAIL
    reuse = f.get("bio_media_reuse")
    if not finite(reuse):
        return NOT_PROVIDED
    return FAIL if float(reuse) > 0 else PASS


def device_network(f: dict) -> str:
    """Mule herding: one device bringing several different real people in a week. Holds for a human; never rejects."""
    n = f.get("cor_device_people_7d")
    if not finite(n):
        return NOT_PROVIDED
    return FAIL if float(n) >= 2 else PASS


def derive(f: dict) -> dict:
    """Checks computed from several modules' features, identical for live, seeding and evaluation."""
    return {**f, "ev_capture_quality": CODE[capture_quality(f)], "ev_media_integrity": CODE[media_integrity(f)],
            "ev_device_network": CODE[device_network(f)]}


def decide(feats: dict, model_result: dict, bands=None) -> dict:
    """model_result: {'prob': float|None, 'status': 'ok'|'unavailable'|'stale', ...}. Returns the policy decision."""
    feats = derive(feats)
    checks = {c: status(feats, c) for c in REQUIRED}
    rule_codes: list[str] = []

    # 1. high-confidence evidence-integrity failures (documented demo policy for SPECIMEN cards)
    hard_reject = []
    if checks["doc_signature"] == FAIL:
        hard_reject.append("DOC_QR_SIG_INVALID")
    if checks["doc_consistency"] == FAIL:
        hard_reject.append("DOC_QR_OCR_MISMATCH")

    # 2. everything else that is not PASS blocks automatic approval
    unresolved = [c for c, s in checks.items() if s != PASS]
    rule_codes += [f"EV_{c.upper()}_{checks[c]}" for c in unresolved]

    prob = model_result.get("prob")
    model_ok = model_result.get("status") == "ok" and finite(prob)
    if not model_ok:
        rule_codes.append("MODEL_UNAVAILABLE")

    # 3. a conflict in the cross-institution network (app/consortium.py) holds the case for a person; it never rejects
    #    on its own. Only present on live cases, so seeding/evaluation (and POLICY_VERSION) are unaffected.
    network_conflict = "ev_network" in feats and status(feats, "network") == FAIL
    if network_conflict:
        rule_codes.append("EV_NETWORK_FAIL")

    eligible = not unresolved and not hard_reject and model_ok and not network_conflict
    if hard_reject:
        band = "REJECT"
    elif not model_ok:
        band = "REVIEW"
    else:
        band = band_of(float(prob), bands)
        if not eligible and band == "APPROVE":
            band = "REVIEW"
        # photos too poor to judge: the model is outside its data, so it may not reject on its own
        if band == "REJECT" and checks["capture_quality"] != PASS:
            band = "REVIEW"
    return {"band": band, "approval_eligible": eligible, "rule_codes": hard_reject + rule_codes,
            "unresolved": unresolved, "checks": checks, "forced": "REJECT" if hard_reject else ("REVIEW" if band == "REVIEW" and (unresolved or not model_ok or network_conflict) else None),
            "prob": float(prob) if model_ok else None, "model_status": model_result.get("status", "unavailable"),
            "policy_version": POLICY_VERSION}


def context_codes(app: dict) -> dict:
    """Evidence codes for the session context. Informational: recorded and shown, never gating (we cannot validate
    a self-reported GPS fix, and on localhost there is no public IP to geolocate).
    shortcut: production plugs an India/allow-list geoIP here to enforce RBI's non-India/spoofed-IP block."""
    geo = app.get("geo")
    loc = PASS if (geo and finite(geo.get("accuracy"))) else NOT_PROVIDED
    region = PASS if app.get("device", {}).get("ip") else UNAVAILABLE  # loopback / behind the dev proxy: cannot geolocate
    return {"ev_location": CODE[loc], "ev_ip_region": CODE[region]}


def evidence_list(feats: dict) -> list[dict]:
    """For the UI: every check with its status and where the evidence came from."""
    feats = derive(feats)
    out = [{"check": c, "label": d, "source": src, "status": status(feats, c), "required": True} for c, (d, src) in REQUIRED.items()]
    absent = lambda src: SIMULATED if src == "simulated" else NOT_PROVIDED  # noqa: E731  only voice is simulated
    out += [{"check": c, "label": d, "source": src, "status": status(feats, c) if f"ev_{c}" in feats else absent(src),
             "required": False} for c, (d, src) in INFORMATIONAL.items()]
    return out
