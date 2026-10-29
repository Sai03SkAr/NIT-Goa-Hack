"""Train fusion (XGBoost + isotonic calibration) on a TIME split and write every D7 metric + the ablation.

Split: days 0-15 train, 16-19 calibration, 20-29 test (no shuffling: fraud evolves over time).
Outputs: models/{xgb.json, calibrator.joblib, features.json, manifest.json},
         precomputed/{metrics.json, ablation.json, test_scores.csv}

Ranking metrics (ROC/PR AUC) are computed on the calibrated MODEL probability. Decision metrics (recall, FPR, band
counts) use the bands from app/policy.py, exactly as the live system decides. The two are never mixed.
"""
import hashlib
import subprocess
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import policy  # noqa: E402
from app.config import BANDS, FEATURE_SCHEMA_VERSION, MODELS, POLICY_VERSION, PRE  # noqa: E402
from app.fusion.model import GROUPS  # noqa: E402

PARAMS = dict(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              min_child_weight=2, eval_metric="logloss", random_state=0, n_jobs=4)
LEAK_SUSPECTS = ("jpeg", "width", "height", "scale", "quality", "extract_ms", "assess_ms")


def load():
    df = pd.read_csv(PRE / "features.csv")
    feats = [c for c in df.columns if c.split("_")[0] in ("doc", "bio", "beh", "reg", "cor")]
    assert not any(s in c for c in feats for s in LEAK_SUSPECTS), "leaky column in features"
    return df, feats


def split(df):
    return df[df.day < 16], df[(df.day >= 16) & (df.day < 20)], df[df.day >= 20]


def fit(tr, cols):
    pos = tr.label.mean()
    m = xgb.XGBClassifier(**PARAMS, scale_pos_weight=(1 - pos) / max(pos, 1e-3))
    m.fit(tr[cols].values.astype(np.float32), tr.label.values)
    return m


def proba(m, df, cols):
    return m.predict_proba(df[cols].values.astype(np.float32))[:, 1]


def policy_bands(df, p):
    """Bands from the shared policy on top of the model probability (what the live system does)."""
    out = [policy.decide(r.to_dict(), {"prob": float(pi), "status": "ok"}) for (_, r), pi in zip(df.iterrows(), p)]
    return [d["band"] for d in out], np.array([d["approval_eligible"] for d in out])


def topk_recall(y, s, frac):
    k = max(1, int(round(len(s) * frac)))
    idx = np.argsort(-s)[:k]
    return float(y[idx].sum() / max(y.sum(), 1))


FN_COST, FP_COST = float(os.getenv("TRUEID_FN_COST", "10")), 1.0  # cost of a missed fraud vs a false alarm; set from real loss data


def cost_curve(ca, p_ca, te, p_te):
    """Choose the APPROVE cut-off on the calibration split (never on test), report its cost on test.
    Cases the policy cannot approve (missing/failed evidence) are flagged whatever the cut-off."""
    (_, e_ca), (_, e_te) = policy_bands(ca, p_ca), policy_bands(te, p_te)
    y_ca, y_te = ca.label.values, te.label.values

    def cost(y, s, e, t):
        flag = ~e | (s >= t)
        return int(FN_COST * (~flag & (y == 1)).sum() + FP_COST * (flag & (y == 0)).sum())
    grid = np.round(np.linspace(0.02, 0.9, 45), 2)
    pts = [{"t": float(t), "cost_cal": cost(y_ca, p_ca, e_ca, t), "cost_test": cost(y_te, p_te, e_te, t)} for t in grid]
    best = min(pts, key=lambda p: (p["cost_cal"], abs(p["t"] - BANDS["approve_below"])))
    return {"fn_cost": FN_COST, "fp_cost": FP_COST, "points": pts, "chosen_on": "calibration split (days 16-19)",
            "recommended_approve_below": best["t"], "current_approve_below": BANDS["approve_below"],
            "test_cost_recommended": best["cost_test"], "test_cost_current": cost(y_te, p_te, e_te, BANDS["approve_below"])}


def bootstrap_ci(y, p, flag, n=300, seed=0):
    """95% percentile intervals: resample test applications with replacement."""
    rng = np.random.default_rng(seed)
    acc = {"roc_auc": [], "recall_fdr": [], "fpr": []}
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        yy, pp, ff = y[i], p[i], flag[i]
        if yy.min() == yy.max():
            continue
        acc["roc_auc"].append(roc_auc_score(yy, pp))
        acc["recall_fdr"].append(ff[yy == 1].mean())
        acc["fpr"].append(ff[yy == 0].mean())
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in acc.items()}


def metrics(y, s, bands, df):
    flag = np.array([b != "APPROVE" for b in bands]).astype(int)
    rej = np.array([b == "REJECT" for b in bands]).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, flag, labels=[0, 1]).ravel()
    per_type = {}
    for t, g in df.assign(flag=flag).groupby("fraud_type"):
        per_type[t] = {"n": int(len(g)), "flag_rate": round(float(g.flag.mean()), 3)}
    sub_hn = df.assign(flag=flag)[df.fraud_type == "hard_negative"].groupby("sub").flag.mean().round(3).to_dict()
    lat = (df.extract_ms + df.assess_ms).values
    return {
        "definition": "Fraud Detection Rate (FDR) = recall on the fraud class; flagged = REVIEW or REJECT",
        "n_test": int(len(y)), "n_fraud": int(y.sum()),
        "precision": round(precision_score(y, flag), 4), "recall_fdr": round(recall_score(y, flag), 4),
        "f1": round(f1_score(y, flag), 4), "fpr": round(fp / max(fp + tn, 1), 4),
        "reject_precision": round(precision_score(y, rej, zero_division=0), 4), "reject_recall": round(recall_score(y, rej), 4),
        "roc_auc": round(roc_auc_score(y, s), 4), "pr_auc": round(average_precision_score(y, s), 4),
        "ranking_metrics_on": "calibrated model probability (before policy)",
        "decision_metrics_on": f"policy bands ({POLICY_VERSION})",
        "ci95": bootstrap_ci(y, s, flag),
        "fdr_at_top3pct": round(topk_recall(y, s, .03), 4), "fdr_at_top5pct": round(topk_recall(y, s, .05), 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "per_type": per_type, "hard_negative_false_flag_by_sub": sub_hn,
        "band_counts": pd.Series(bands).value_counts().to_dict(),
        "latency_ms": {"p50": float(np.percentile(lat, 50)), "p95": float(np.percentile(lat, 95)),
                       "note": "per-application CPU time for all modules (seeded batch, excludes LLM)"},
    }


def manifest(feats, n_tr, n_ca, n_te):
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=Path(__file__).parent).stdout.strip() or None
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True,
                               cwd=Path(__file__).parent).stdout.strip()
        if commit and dirty:
            commit += " + uncommitted changes"
    except OSError:
        commit = None
    return {"policy_version": POLICY_VERSION, "feature_schema_version": FEATURE_SCHEMA_VERSION, "features": feats,
            "xgb_params": PARAMS, "seed": PARAMS["random_state"], "git_commit": commit, "fn_cost": FN_COST,
            "data": {"features.csv": sha(PRE / "features.csv"), "augmented.csv": sha(PRE / "augmented.csv")},
            "split": {"train": "days 0-15", "calibration": "days 16-19", "test": "days 20-29",
                      "n": {"train": n_tr, "calibration": n_ca, "test": n_te}},
            "evaluation_kind": "synthetic population (generated identities, LFW faces); liveness outcomes in these "
                               "rows are generator-labelled fixtures, not live camera sessions",
            "versions": {"xgboost": xgb.__version__, "numpy": np.__version__, "pandas": pd.__version__}}


def genuine_profile(tr, ca, te, feats):
    """IDRBT-style explainable one-class rules, learnt from genuine applicants only (app/fusion/profile.py), and the
    zero-day test: retrain the model without one fraud type, then see who catches that unseen type."""
    from app.fusion import profile
    G = tr[tr.label == 0][feats].astype(float).values
    P = profile.calibrate(profile.fit(G, feats), ca[ca.label == 0][feats].astype(float).values)
    profile.save(P)
    s_te, _, _ = profile.score(P, te[feats].astype(float).values)
    y = te.label.values
    out = s_te > P["threshold"]
    gp = {"roc_auc_no_fraud_labels": round(roc_auc_score(y, s_te), 4), "genuine_outside": round(float(out[y == 0].mean()), 4),
          "fraud_outside": round(float(out[y == 1].mean()), 4), "threshold": round(P["threshold"], 2), "clusters": len(P["sizes"]),
          "trained_on": f"{len(G)} genuine training applicants, no fraud labels",
          "role": "informational: explains and monitors, never decides"}
    zd = []
    for t in sorted(set(tr.fraud_type) - {"genuine", "hard_negative"}):
        trT, caT = tr[tr.fraud_type != t], ca[ca.fraud_type != t]
        mm = fit(trT, feats)
        pi = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(proba(mm, caT, feats), caT.label.values).predict(proba(mm, te, feats))
        bands, _ = policy_bands(te, pi)
        mT = (te.fraud_type == t).values
        if not mT.any():
            continue
        zd.append({"type": t, "n_test": int(mT.sum()), "model_only": round(float((pi[mT] >= BANDS["approve_below"]).mean()), 3),
                   "profile_only": round(float(out[mT].mean()), 3),
                   "live_system": round(float(np.mean([b != "APPROVE" for b, k in zip(bands, mT) if k])), 3)})
    print("genuine profile:", gp)
    print("zero-day (type unseen in training):", zd)
    return gp, zd


def main():
    df, feats = load()
    tr, ca, te = split(df)
    aug_path = PRE / "augmented.csv"
    if aug_path.exists():  # degraded copies of training-period apps only (eval/augment.py); cal/test stay clean
        aug = pd.read_csv(aug_path)
        aug = aug[aug.day < 16]
        tr = pd.concat([tr, aug[tr.columns.intersection(aug.columns)]], ignore_index=True)
        print(f"+ {len(aug)} augmented training rows")
    print(f"train {len(tr)} ({tr.label.sum()} fraud) | cal {len(ca)} | test {len(te)} ({te.label.sum()} fraud)")

    m = fit(tr, feats)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(proba(m, ca, feats), ca.label.values)
    p_te = iso.predict(proba(m, te, feats))
    s_te = p_te
    bands, eligible = policy_bands(te, p_te)
    res = metrics(te.label.values, s_te, bands, te)
    res["held_by_evidence"] = round(float((~eligible).mean()), 4)
    res["cost_curve"] = cost_curve(ca, iso.predict(proba(m, ca, feats)), te, p_te)

    gain = m.get_booster().get_score(importance_type="gain")
    top = sorted(((feats[int(k[1:])] if k.startswith("f") and k[1:].isdigit() else k, v) for k, v in gain.items()),
                 key=lambda x: -x[1])[:15]
    from app.fusion.fraud_type import classify
    caught = te.assign(band=bands)[te.label.values == 1]
    caught = caught[caught.band != "APPROVE"]
    pred = [classify(r.to_dict()) for _, r in caught.iterrows()]
    alias = {"injection": {"bot", "third_party", "ring"}}  # replay/virtual-cam is how bots and fabricators inject
    hit = [p == t or t in alias.get(p, ()) for p, t in zip(pred, caught.fraud_type)]
    res["fraud_type_accuracy"] = round(float(np.mean(hit)), 3) if hit else None
    res["fraud_type_accuracy_exact"] = round(float(np.mean([p == t for p, t in zip(pred, caught.fraud_type)])), 3) if hit else None
    res["fraud_type_note"] = "accuracy counts 'injection' as correct for bot/third-party/ring sessions; _exact does not"
    res["fraud_type_confusion"] = pd.crosstab(caught.fraud_type.values, np.array(pred)).to_dict()
    res["top_features"] = [{"feature": k, "gain": round(v, 2)} for k, v in top]
    res["leakage_check"] = "pass: no image-size/JPEG/timing columns among features" if not any(
        s in k for k, _ in top for s in LEAK_SUSPECTS) else "WARN"

    # ---- ablation: each module alone, all-but-one, fused, fused + rules
    abl = []
    def run(name, cols, rules=False):
        mm = fit(tr, cols)
        pi = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(proba(mm, ca, cols), ca.label.values).predict(proba(mm, te, cols))
        s, b = pi, (policy_bands(te, pi)[0] if rules else ["APPROVE" if x < BANDS["approve_below"] else "REVIEW" for x in pi])
        flag = np.array([x != "APPROVE" for x in b]).astype(int)
        y = te.label.values
        abl.append({"setting": name, "n_features": len(cols), "roc_auc": round(roc_auc_score(y, s), 4),
                    "pr_auc": round(average_precision_score(y, s), 4), "recall": round(recall_score(y, flag), 4),
                    "fpr": round(float(((flag == 1) & (y == 0)).sum() / max((y == 0).sum(), 1)), 4),
                    "f1": round(f1_score(y, flag), 4)})
    for g, pre in GROUPS.items():
        run(f"{g} only", [c for c in feats if c.startswith(pre)])
    for g, pre in GROUPS.items():
        run(f"all except {g}", [c for c in feats if not c.startswith(pre)])
    run("fused (all modules)", feats)
    run("fused + evidence policy", feats, rules=True)

    res["genuine_profile"], res["zero_day"] = genuine_profile(tr, ca, te, feats)

    m.save_model(MODELS / "xgb.json")
    joblib.dump(iso, MODELS / "calibrator.joblib")
    (MODELS / "features.json").write_text(json.dumps(feats))
    (MODELS / "manifest.json").write_text(json.dumps(manifest(feats, len(tr), len(ca), len(te)), indent=1))
    (PRE / "metrics.json").write_text(json.dumps(res, indent=1, default=float))
    (PRE / "ablation.json").write_text(json.dumps(abl, indent=1))
    te.assign(score=s_te, band=bands)[["app_id", "day", "label", "fraud_type", "sub", "score", "band"]].to_csv(
        PRE / "test_scores.csv", index=False)
    print(json.dumps({k: res[k] for k in ("precision", "recall_fdr", "f1", "fpr", "roc_auc", "pr_auc")}, indent=1))
    print("per type:", res["per_type"])
    print("hard negatives flagged:", res["hard_negative_false_flag_by_sub"])
    print(pd.DataFrame(abl).to_string(index=False))


if __name__ == "__main__":
    main()
