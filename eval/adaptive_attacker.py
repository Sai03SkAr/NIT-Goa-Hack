"""Adaptive attacker (D5): greedy feature-space evasion that may ONLY change what a fraudster controls
(typing, email, device, IP, timing, graph links they can avoid). Face, registry history, QR signature, SIM age,
document content stay fixed. Reports how much recall survives. Writes precomputed/adaptive.json."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import PRE  # noqa: E402
from app.fusion.model import decide  # noqa: E402

FIXED_COR = {"cor_comp_face_edges", "cor_id_names"}  # can't un-reuse your own face or a shared ID


def controllable(cols):
    return [c for c in cols if c.startswith("beh_") or (c.startswith("cor_") and c not in FIXED_COR)]


def flagged(f):
    return decide(f)["band"] != "APPROVE"


def attack(f, ctrl, cands, max_steps=12):
    f = dict(f)
    p = decide(f)["prob"]
    for _ in range(max_steps):
        best = None
        for c in ctrl:
            for v in cands[c]:
                if f.get(c) == v:
                    continue
                g = dict(f); g[c] = v
                q = decide(g)["prob"]
                if q < p - 1e-4 and (best is None or q < best[0]):
                    best = (q, c, v)
        if best is None:
            break
        p, c, v = best
        f[c] = v
        if decide(f)["band"] == "APPROVE":
            break
    return f


def main():
    df = pd.read_csv(PRE / "features.csv")
    cols = [c for c in df.columns if c.split("_")[0] in ("doc", "bio", "beh", "reg", "cor", "ev", "meta")]  # ev_/meta_: policy evidence, kept for the decision
    ctrl = controllable(cols)
    gen_tr = df[(df.day < 20) & (df.label == 0)]
    cands = {c: sorted(set(np.nanquantile(gen_tr[c], [.1, .5, .9]).round(4))) for c in ctrl}
    te = df[(df.day >= 20) & (df.label == 1)]
    rows = []
    for r in te.itertuples():
        f = {c: (np.nan if pd.isna(getattr(r, c)) else getattr(r, c)) for c in cols}
        before = flagged(f)
        after = flagged(attack(f, ctrl, cands)) if before else False
        rows.append({"type": r.fraud_type, "before": before, "after": after})
    R = pd.DataFrame(rows)
    per = R.groupby("type").agg(before=("before", "mean"), after=("after", "mean"), n=("before", "size")).round(3)
    out = {"id": "adaptive", "kind": "adaptive", "name": "Adaptive attacker (greedy, attacker-controllable features only)",
           "target": "Fusion", "defense": "Can't fake history, cryptography or their own face",
           "controllable": ctrl, "n": int(len(R)),
           "recall_before": round(float(R.before.mean()), 3), "recall_after": round(float(R.after.mean()), 3),
           "per_type": per.reset_index().to_dict(orient="records")}
    (PRE / "adaptive.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("n", "recall_before", "recall_after")}), "\n", per)


if __name__ == "__main__":
    main()
