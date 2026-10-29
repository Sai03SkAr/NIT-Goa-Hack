"""Genuine-applicant profile: explainable one-class rules, learnt from GENUINE applicants only.

After IDRBT's "Explainable One Class Classification for ATM Fraud Detection" (Vivek, Ravi, Mane, Naidu, COMSNETS 2025):
cluster legitimate cases with K-Means and keep one bounding-box rule per cluster (here the 1st-99th percentile of each
feature, which is robust to outliers). A case that falls outside its nearest cluster's box is "unlike any genuine
applicant", and the features that broke the box are the explanation. It needs no fraud labels, so it also works for a
bank that has never labelled a fraud, and it catches fraud TYPES the supervised model never saw (docs/IDRBT_INNOVATION.md).

federate(): one-shot federated version after IDRBT's FedPNN (Prasad, Vivek, Ravi, arXiv 2304.04147): each institution
clusters its own genuine customers and shares only cluster summaries (centre, size, per-cluster bounds); the server
meta-clusters the centres in a single round. No customer row leaves a bank.

The profile explains and monitors. It never approves or rejects: it is informational evidence (policy.INFORMATIONAL)."""
from functools import lru_cache

import joblib
import numpy as np

from app.config import MODELS

PATH = MODELS / "profile.joblib"


def _robust(G: np.ndarray, med: np.ndarray) -> np.ndarray:
    """Per-feature spread: IQR, else standard deviation, else 1 (a constant feature)."""
    q1, q3 = np.nanpercentile(G, 25, axis=0), np.nanpercentile(G, 75, axis=0)
    s = q3 - q1
    sd = np.nanstd(G, axis=0)
    s = np.where(s > 0, s, np.where(np.isfinite(sd) & (sd > 0), sd, 1.0))
    return s


def _fill(X: np.ndarray, med: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(X), X, med)


def fit(G: np.ndarray, features: list[str], k: int = 8, lo: float = 0.01, hi: float = 0.99, seed: int = 0) -> dict:
    """G: genuine rows (n x d), columns in `features` order. Returns the profile as a plain dict (joblib-safe)."""
    from sklearn.cluster import KMeans
    G = np.asarray(G, dtype=float)
    med = np.nan_to_num(np.nanmedian(G, axis=0), nan=0.0)
    Gf = _fill(G, med)
    scale = _robust(Gf, med)
    km = KMeans(k, n_init=10, random_state=seed).fit((Gf - med) / scale)
    lab = km.labels_
    lo_b = np.vstack([np.quantile(Gf[lab == c], lo, axis=0) for c in range(k)])
    hi_b = np.vstack([np.quantile(Gf[lab == c], hi, axis=0) for c in range(k)])
    return {"features": list(features), "med": med, "scale": scale, "centroids": km.cluster_centers_,
            "lo": lo_b, "hi": hi_b, "sizes": np.bincount(lab, minlength=k), "threshold": None, "source": "central",
            "quantiles": {q: np.quantile(Gf, q, axis=0) for q in (0.1, 0.5, 0.9)}, "n_genuine": int(len(Gf))}


def score(P: dict, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(novelty score, nearest cluster, per-feature exceedance in spread units) for rows X (n x d)."""
    Xf = _fill(np.asarray(X, dtype=float), P["med"])
    Z = (Xf - P["med"]) / P["scale"]
    c = np.argmin(((Z[:, None, :] - P["centroids"][None, :, :]) ** 2).sum(-1), axis=1)
    lo, hi = P["lo"][c], P["hi"][c]
    exceed = (np.maximum(lo - Xf, 0) + np.maximum(Xf - hi, 0)) / P["scale"]
    return exceed.sum(1), c, exceed


def explain(P: dict, feats: dict, top: int = 5) -> dict:
    """One case: is it inside the genuine profile, and which learnt rules does it break (feature, value, genuine range)."""
    x = np.array([[feats.get(f, np.nan) for f in P["features"]]], dtype=float)
    s, c, ex = score(P, x)
    order = [i for i in np.argsort(-ex[0]) if ex[0, i] > 0][:top]
    raw = x[0]
    rules = [{"feature": P["features"][i], "value": None if not np.isfinite(raw[i]) else round(float(raw[i]), 3),
              "low": round(float(P["lo"][c[0], i]), 3), "high": round(float(P["hi"][c[0], i]), 3),
              "excess": round(float(ex[0, i]), 2)} for i in order]
    thr = P.get("threshold")
    return {"score": round(float(s[0]), 2), "threshold": None if thr is None else round(float(thr), 2),
            "outside": bool(thr is not None and s[0] > thr), "cluster": int(c[0]),
            "broken_rules": int((ex[0] > 0).sum()), "rules": rules, "source": P.get("source", "central")}


# ------------------------------------------------------------------ one-shot federation (FedPNN pattern)
def summarise(G: np.ndarray, med: np.ndarray, scale: np.ndarray, k_local: int = 6, seed: int = 0) -> list[dict]:
    """What ONE institution shares: per local cluster its centre, size and 1st/99th percentile box. No rows."""
    from sklearn.cluster import KMeans
    Gf = _fill(np.asarray(G, dtype=float), med)
    k_local = max(1, min(k_local, len(Gf) // 3))
    km = KMeans(k_local, n_init=10, random_state=seed).fit((Gf - med) / scale)
    out = []
    for c in range(k_local):
        M = Gf[km.labels_ == c]
        if len(M) >= 3:  # tiny clusters would expose individual customers; drop them
            out.append({"centre": M.mean(0), "n": int(len(M)), "lo": np.quantile(M, 0.01, axis=0),
                        "hi": np.quantile(M, 0.99, axis=0)})
    return out


def federate(summaries: list[dict], features: list[str], med: np.ndarray, scale: np.ndarray, k_global: int = 8,
             seed: int = 0) -> dict:
    """Server side, one round: weighted K-Means over the shared centres; each global rule is the union of its members'
    boxes. `med` and `scale` are the normaliser the members agreed on (shared statistics, not data)."""
    from sklearn.cluster import KMeans
    C = np.array([(s["centre"] - med) / scale for s in summaries])
    w = np.array([s["n"] for s in summaries], dtype=float)
    k_global = max(1, min(k_global, len(C)))
    mk = KMeans(k_global, n_init=10, random_state=seed).fit(C, sample_weight=w)
    groups = [np.where(mk.labels_ == g)[0] for g in range(k_global)]
    lo = np.vstack([np.min([summaries[i]["lo"] for i in g], axis=0) for g in groups])
    hi = np.vstack([np.max([summaries[i]["hi"] for i in g], axis=0) for g in groups])
    return {"features": list(features), "med": med, "scale": scale, "centroids": mk.cluster_centers_, "lo": lo,
            "hi": hi, "sizes": np.array([w[g].sum() for g in groups]), "threshold": None, "source": "federated",
            "quantiles": None, "n_genuine": int(w.sum())}


def calibrate(P: dict, G_cal: np.ndarray, q: float = 0.98) -> dict:
    """Threshold = the q-quantile of novelty scores of held-out GENUINE applicants (about 2% of genuine fall outside)."""
    s, _, _ = score(P, G_cal)
    P["threshold"] = float(np.quantile(s, q))
    return P


# ------------------------------------------------------------------ live use
@lru_cache(maxsize=1)
def load() -> dict | None:
    return joblib.load(PATH) if PATH.exists() else None


def save(P: dict):
    joblib.dump(P, PATH)
    load.cache_clear()


def assess(feats: dict) -> dict | None:
    """The live check, or None when no profile has been trained yet (then the case simply shows no profile)."""
    P = load()
    if P is None or P.get("threshold") is None:
        return None
    return explain(P, feats)
