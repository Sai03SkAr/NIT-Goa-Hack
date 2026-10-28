"""Fusion: hard rules -> calibrated XGBoost -> SHAP top-5 -> band -> fraud type + recommended action."""
import json
from functools import lru_cache

import joblib
import numpy as np

from app.config import BANDS, MODELS

GROUPS = {"document": "doc_", "biometric": "bio_", "behavior": "beh_", "registry": "reg_", "correlation": "cor_"}


def feature_names() -> list[str]:
    return json.loads((MODELS / "features.json").read_text())


@lru_cache(maxsize=1)
def load():
    import xgboost as xgb
    if not (MODELS / "xgb.json").exists():
        return None
    m = xgb.XGBClassifier()
    m.load_model(MODELS / "xgb.json")
    cal = joblib.load(MODELS / "calibrator.joblib")
    import shap
    return m, cal, shap.TreeExplainer(m), feature_names()


def vectorize(feats: dict, names: list[str]) -> np.ndarray:
    return np.array([[feats.get(n, np.nan) for n in names]], dtype=np.float32)


# ------------------------------------------------------------------ hard rules (deterministic, auditable)
def hard_rules(feats: dict) -> tuple[str | None, list[str]]:
    rej, rev = [], []
    if feats.get("doc_sig_invalid") == 1: rej.append("DOC_QR_SIG_INVALID")
    if feats.get("doc_checksum_ok") == 0: rej.append("DOC_CHECKSUM_FAIL")
    if feats.get("bio_virtual_cam") == 1: rej.append("BIO_VIRTUAL_CAMERA")
    if feats.get("doc_qr_missing") == 0 and feats.get("doc_sig_invalid") == 0 and \
            (feats.get("doc_qr_ocr_dob") == 0 or feats.get("doc_qr_ocr_name", 1) < 0.8):
        rej.append("DOC_QR_OCR_MISMATCH")  # confidently read edit: the card was altered after signing
    if feats.get("doc_qr_ocr_unsure") == 1:
        rev.append("DOC_QR_OCR_MISMATCH")  # disagreement, but the printed text was barely readable: a human checks
    from app.modules.biometric.face import threshold
    t = threshold()
    card_miss = feats.get("bio_sim_card", 1) < t           # NaN compares False: a missing face is handled elsewhere
    reg_miss = feats.get("bio_sim_registry", 1) < t
    # a face mismatch can never be auto-approved; it is only a floor (a blurry genuine selfie fails both, so not REJECT)
    if card_miss: rev.append("BIO_CARD_FACE_MISMATCH")
    if reg_miss: rev.append("BIO_REGISTRY_FACE_MISMATCH")
    if feats.get("bio_liveness_pass") == 0: rev.append("BIO_LIVENESS_FAIL")
    if rej:
        return "REJECT", rej
    if rev:
        return "REVIEW", rev
    return None, []


def quality_low(f: dict) -> bool:
    """Quality gate: too blurry/noisy a selfie or a barely readable card means 'retake', never an automatic fraud verdict.
    Genuine training uploads: selfie sharpness p1 27.5, p99.5 660; card OCR confidence p1 0.77."""
    sharp, conf = f.get("bio_blur"), f.get("doc_ocr_conf")
    bad_selfie = sharp is not None and sharp == sharp and (sharp < 20 or sharp > 2000)
    bad_card = conf is not None and conf == conf and conf < 0.70
    return bad_selfie or bad_card


def band(p: float, bands=None) -> str:
    b = bands or BANDS
    return "APPROVE" if p < b["approve_below"] else ("REJECT" if p >= b["reject_at"] else "REVIEW")


def score(feats: dict) -> dict:
    loaded = load()
    if loaded is None:  # no trained model yet: mean of module risks
        risks = [feats.get(f"{p}risk", 0) for p in GROUPS.values()]
        return {"prob": float(np.nanmean(risks)), "raw": None, "shap": []}
    m, cal, expl, names = loaded
    x = vectorize(feats, names)
    raw = float(m.predict_proba(x)[0, 1])
    prob = float(cal.predict([raw])[0])
    sv = expl.shap_values(x)[0]
    top = np.argsort(-np.abs(sv))[:5]
    return {"prob": prob, "raw": raw, "base": float(np.ravel(expl.expected_value)[0]),
            "shap": [{"feature": names[i], "value": None if np.isnan(x[0, i]) else round(float(x[0, i]), 3),
                      "shap": round(float(sv[i]), 3)} for i in top]}


def decide(feats: dict, bands=None) -> dict:
    s = score(feats)
    forced, rule_codes = hard_rules(feats)
    b = band(s["prob"], bands)
    if forced == "REJECT" or (forced == "REVIEW" and b == "APPROVE"):
        b = forced
    if forced != "REJECT" and quality_low(feats):
        b, forced = "REVIEW", "REVIEW"
        rule_codes = rule_codes + ["IMG_QUALITY_LOW"]
    return {**s, "band": b, "forced": forced, "rule_codes": rule_codes}
