"""Training-time augmentation. Synthetic cards are pixel-perfect, so without this the model learns that any
degradation (an unreadable QR, a slightly different card photo) means fraud, and rejects genuine people who upload a
blurry or recaptured photo. We add degraded copies of TRAINING-period applications (days 0-15 only) with real
re-extraction of the document and face features; behaviour, registry and graph features stay those of the original.
Calibration and test splits are never augmented, so reported metrics stay honest.

Output: precomputed/augmented.csv (train.py appends it to the training split when present)."""
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import run_attacks as ra  # noqa: E402
from app.config import GEN, PRE  # noqa: E402

# levels a real upload can plausibly have; the Attack Lab sweeps go further than this on purpose
RANGES = {"jpeg": (30, 70), "noise": (4, 22), "blur": (0.5, 1.6), "brightness": (0.6, 1.3), "recapture": (0.3, 1.2)}


def main(n_genuine=360, n_fraud=120, workers=5, seed=3):
    rng = random.Random(seed)
    apps = {a["app_id"]: a for a in json.loads((GEN / "population.json").read_text())}
    df = pd.read_csv(PRE / "features.csv")
    tr = df[df.day < 16]
    pick = pd.concat([tr[tr.label == 0].sample(min(n_genuine, (tr.label == 0).sum()), random_state=seed),
                      tr[tr.label == 1].sample(min(n_fraud, (tr.label == 1).sum()), random_state=seed)])
    cols = [c for c in df.columns if c.split("_")[0] in ("doc", "bio", "beh", "reg", "cor", "ev", "meta")]  # ev_/meta_: policy evidence, kept for the decision
    jobs, meta = [], []
    for r in pick.itertuples():
        attack = rng.choice(list(RANGES))
        lo, hi = RANGES[attack]
        level = round(rng.uniform(lo, hi), 2)
        base = {c: (np.nan if pd.isna(getattr(r, c)) else getattr(r, c)) for c in cols}
        jobs.append((apps[r.app_id], attack, level, base))
        meta.append({"app_id": f"{r.app_id}~{attack}{level}", "day": r.day, "label": r.label, "fraud_type": r.fraud_type,
                     "sub": r.sub, "group": r.group, "extract_ms": r.extract_ms, "assess_ms": r.assess_ms})
    print(f"augmenting {len(jobs)} training applications with {workers} workers")
    with ProcessPoolExecutor(workers) as ex:
        feats = list(ex.map(ra._features_for, jobs, chunksize=6))
    out = pd.DataFrame([{**m, **f} for m, f in zip(meta, feats)])
    out.to_csv(PRE / "augmented.csv", index=False)
    print("wrote", len(out), "rows:", out.groupby("label").size().to_dict())


if __name__ == "__main__":
    main()
