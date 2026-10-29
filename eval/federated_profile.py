"""One-shot federated genuine profile (after IDRBT's FedPNN, Prasad, Vivek, Ravi, arXiv 2304.04147).

Three institutions each cluster their OWN genuine customers and share only cluster summaries (centre, size, per-cluster
1st/99th percentile box). The server meta-clusters the centres in one round. We compare it with pooling all the data
(what no bank is allowed to do) and with a bank working alone.

Output: precomputed/federated.json (shown on the Evaluation page)."""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import train as T  # noqa: E402
from app.config import PRE  # noqa: E402
from app.fusion import profile  # noqa: E402


def evaluate(P, ca, te, feats):
    profile.calibrate(P, ca[ca.label == 0][feats].astype(float).values)
    s, _, _ = profile.score(P, te[feats].astype(float).values)
    y, out = te.label.values, s > P["threshold"]
    return {"roc_auc": round(roc_auc_score(y, s), 4), "genuine_outside": round(float(out[y == 0].mean()), 4),
            "fraud_outside": round(float(out[y == 1].mean()), 4)}


def main():
    df, feats = T.load()
    tr, ca, te = T.split(df)
    G = tr[tr.label == 0].sample(frac=1, random_state=0)
    n = len(G)
    banks = {"similar customers (random split)": [G.iloc[:n // 3], G.iloc[n // 3:2 * n // 3], G.iloc[2 * n // 3:]]}
    q1, q2 = G.reg_age.quantile([1 / 3, 2 / 3])  # each bank serves a different age group: a realistic non-IID split
    banks["different customers (split by age)"] = [G[G.reg_age < q1], G[(G.reg_age >= q1) & (G.reg_age < q2)], G[G.reg_age >= q2]]
    rows = [{"setting": "pooled data (not allowed in practice)", "rows_shared": n, "summaries_shared": 0,
             **evaluate(profile.fit(G[feats].astype(float).values, feats), ca, te, feats)}]
    for name, shards in banks.items():
        Xs = [s[feats].astype(float).values for s in shards]
        # the agreed normaliser: median of the banks' medians and mean of their spreads (statistics, not rows)
        meds = [np.nan_to_num(np.nanmedian(x, axis=0)) for x in Xs]
        med = np.median(meds, axis=0)
        scale = np.mean([profile._robust(profile._fill(x, med), med) for x in Xs], axis=0)
        summaries = [sm for x in Xs for sm in profile.summarise(x, med, scale)]
        P = profile.federate(summaries, feats, med, scale)
        rows.append({"setting": f"federated, 3 banks, {name}", "rows_shared": 0, "summaries_shared": len(summaries),
                     **evaluate(P, ca, te, feats)})
        rows.append({"setting": f"one bank alone, {name}", "rows_shared": 0, "summaries_shared": 0,
                     **evaluate(profile.fit(Xs[0], feats), ca, te, feats)})
    out = {"method": "one-shot federated one-class profile (local K-Means -> share cluster summaries -> server "
                     "meta-clustering), after IDRBT FedPNN", "rows": rows,
           "note": "Summaries are cluster centres and per-cluster percentile boxes, not customer rows. They are not "
                   "differentially private; production would add noise or secure aggregation."}
    (PRE / "federated.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        print(f"{r['setting']:<58} AUC {r['roc_auc']:.3f}  genuine outside {r['genuine_outside']:.3f}  fraud outside {r['fraud_outside']:.3f}")


if __name__ == "__main__":
    main()
