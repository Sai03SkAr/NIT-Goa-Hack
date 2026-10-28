"""Fusion scoring: calibrated XGBoost -> SHAP top-5. The decision itself is app/policy.py."""
import json
from functools import lru_cache

import joblib
import numpy as np

from app import policy
from app.config import FEATURE_SCHEMA_VERSION, MODELS, POLICY_VERSION

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


def score(feats: dict) -> dict:
    """Model probability only. No trained model, or a model trained under a different policy/feature schema,
    is reported as such; it is never replaced by an average of module risks dressed up as a probability."""
    loaded = load()
    if loaded is None:
        return {"prob": None, "raw": None, "shap": [], "status": "unavailable"}
    if stale():
        return {"prob": None, "raw": None, "shap": [], "status": "stale"}
    m, cal, expl, names = loaded
    x = vectorize(feats, names)
    raw = float(m.predict_proba(x)[0, 1])
    prob = float(cal.predict([raw])[0])
    sv = expl.shap_values(x)[0]
    top = np.argsort(-np.abs(sv))[:5]
    return {"prob": prob, "raw": raw, "base": float(np.ravel(expl.expected_value)[0]), "status": "ok",
            "shap": [{"feature": names[i], "value": None if np.isnan(x[0, i]) else round(float(x[0, i]), 3),
                      "shap": round(float(sv[i]), 3)} for i in top]}


@lru_cache(maxsize=1)
def manifest() -> dict | None:
    p = MODELS / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


def stale() -> bool:
    m = manifest()
    return m is None or m.get("feature_schema_version") != FEATURE_SCHEMA_VERSION \
        or m.get("policy_version") != POLICY_VERSION or m.get("features") != feature_names()


def decide(feats: dict, bands=None) -> dict:
    """Score, then let the shared policy pick the band. Same function for live, seeding, Attack Lab and evaluation."""
    s = score(feats)
    return {**s, **policy.decide(feats, s, bands)}
