"""Run every module over the seeded population, exactly as the live pipeline would, in time order.

Stage 1 (parallel, cached in precomputed/extract/): QR, OCR, forensics, face embeddings, passive checks.
Stage 2 (sequential, as-of-time): face-threshold calibration, behaviour IsolationForest, then the five agents
with a growing History so no application ever sees the future.
Output: precomputed/features.csv, precomputed/modules.jsonl
"""
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import FACE_THRESHOLD_FILE, GEN, MODELS, PRE  # noqa: E402

EXT = PRE / "extract"
EXT.mkdir(parents=True, exist_ok=True)
TRAIN_DAYS = 20


def _extract_one(app: dict) -> str:
    from app.modules.biometric import agent as bio
    from app.modules.document import agent as doc
    out = EXT / f"{app['app_id']}.pkl"
    if out.exists():
        return app["app_id"]
    t0 = time.time()
    raw = (GEN / app["card_path"]).read_bytes()
    card = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    selfie = cv2.imread(str(GEN / app["selfie_path"]))
    d = doc.extract(card, raw)
    b = bio.extract(selfie, doc.normalize(card))
    out.write_bytes(pickle.dumps({"doc": d, "bio": b, "extract_ms": int((time.time() - t0) * 1000)}))
    return app["app_id"]


def _registry_emb(items):
    from app.modules.biometric.face import embed
    res = {}
    for idn, path in items:
        e = embed(cv2.imread(str(GEN / path)))
        if e is not None:
            res[idn] = e["emb"]
    return res


def stage1(apps, reg, workers):
    todo = [a for a in apps if not (EXT / f"{a['app_id']}.pkl").exists()]
    print(f"stage1: {len(todo)} apps to extract with {workers} workers")
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for k, _ in enumerate(ex.map(_extract_one, todo, chunksize=8)):
            if k % 100 == 0:
                print(f"  {k}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    rp = PRE / "registry_emb.npz"
    if not rp.exists():
        items = [(k, v["face"]) for k, v in reg["uidai"].items()]
        chunks = [items[i::workers] for i in range(workers)]
        emb = {}
        with ProcessPoolExecutor(workers) as ex:
            for r in ex.map(_registry_emb, chunks):
                emb.update(r)
        np.savez(rp, **emb)
    print(f"stage1 done in {time.time() - t0:.0f}s")


def calibrate_face(apps, reg_emb, ext):
    """EER threshold on genuine (selfie vs registry photo of same person) vs impostor pairs, train days only."""
    rng = np.random.default_rng(0)
    gen, s_list, r_list = [], [], []
    for a in apps:
        if a["label"] or a["day"] >= TRAIN_DAYS:
            continue
        s = ext[a["app_id"]]["bio"]["selfie"]
        r = reg_emb.get(a["form"]["id_number"])
        if s is None or r is None:
            continue
        gen.append(float(s["emb"] @ r))
        s_list.append(s["emb"]); r_list.append(r)
    S, Rm = np.stack(s_list), np.stack(r_list)
    perm = rng.permutation(len(S))
    imp = [float(S[i] @ Rm[j]) for i, j in zip(range(len(S)), perm) if i != j]
    gen, imp = np.array(gen), np.array(imp)
    eer = min(np.linspace(0, 0.8, 161), key=lambda t: abs((gen < t).mean() - (imp >= t).mean()))
    # 1:1 verification runs at FAR 0.1% (KYC operating point), not at EER (~2% impostor accepts): measured on
    # selfie vs every OTHER person's registry photo
    cross = (S @ Rm.T)[~np.eye(len(S), dtype=bool)]
    best = float(np.quantile(cross, 1 - 1e-3))
    # 1:N reuse search compares against every prior face, so it needs a far lower FAR than 1:1 verification
    allimp = (S @ S.T)[~np.eye(len(S), dtype=bool)]
    # every search compares against the whole history: keep expected false hits per search <= 0.03
    reuse = float(np.quantile(allimp, 1 - 0.03 / len(apps)))
    info = {"threshold": round(float(best), 3), "threshold_far": 1e-3, "eer_threshold": round(float(eer), 3),
            "reuse_threshold": round(reuse, 3),
            "reuse_far": round(float((allimp >= reuse).mean()), 6), "reuse_frr": round(float((gen < reuse).mean()), 4),
            "n_reuse_impostor_pairs": int(allimp.size), "frr": round(float((gen < best).mean()), 4),
            "far": round(float((imp >= best).mean()), 4), "n_genuine": len(gen), "n_impostor": len(imp),
            "genuine_mean": round(float(gen.mean()), 3), "impostor_mean": round(float(imp.mean()), 3)}
    FACE_THRESHOLD_FILE.write_text(json.dumps(info, indent=1))
    print("face threshold:", info)


def train_iforest(apps):
    import joblib
    from sklearn.ensemble import IsolationForest
    from app.modules.behavior.agent import tele_vector
    X = np.stack([tele_vector(a["telemetry"]) for a in apps if a["label"] == 0 and a["day"] < TRAIN_DAYS])
    m = IsolationForest(n_estimators=200, random_state=0).fit(X)
    joblib.dump(m, MODELS / "behavior_iforest.joblib")


def stage2(apps, ext):
    from app.modules.behavior import agent as beh
    from app.modules.biometric import agent as bio
    from app.modules.biometric.face import reuse_threshold
    from app.modules.correlation import agent as cor
    from app.modules.correlation.history import History
    from app.modules.document import agent as doc
    from app.modules.registry import agent as regm
    from app.modules.registry.mocks import registry_face, registry_face_url
    from datetime import datetime

    hist = History(reuse_threshold())
    rows, mods = [], []
    t0 = time.time()
    for a in apps:
        e = ext[a["app_id"]]
        today = datetime.fromisoformat(a["ts"]).date()
        sel = e["bio"]["selfie"]
        rec = History.record(a, sel["emb"] if sel else None)
        d = doc.assess(e["doc"], a["form"], today)
        reuse = hist.face_matches(rec["face"], rec["name"])
        b = bio.assess(e["bio"], registry_face(a["form"]["id_number"]), a["liveness"], a["device"]["camera_labels"], reuse,
                       registry_face_url(a["form"]["id_number"]), a["device"].get("active_camera"))
        be = beh.assess(a, rec, hist)
        r = regm.assess(a["form"], today)
        c = cor.assess(rec, hist, commit=True)
        feats = {}
        for m in (d, b, be, r, c):
            feats.update(m.features)
        rows.append({"app_id": a["app_id"], "day": a["day"], "label": a["label"], "fraud_type": a["fraud_type"],
                     "sub": a["meta"].get("sub", ""), "group": a["group"], "extract_ms": e["extract_ms"],
                     "assess_ms": sum(m.latency_ms for m in (d, b, be, r, c)), **feats})
        mods.append({"app_id": a["app_id"], "modules": [m.model_dump() for m in (d, b, be, r, c)]})
    print(f"stage2: {len(apps)} apps in {time.time() - t0:.1f}s")
    pd.DataFrame(rows).to_csv(PRE / "features.csv", index=False)
    with open(PRE / "modules.jsonl", "w") as fh:
        for m in mods:
            fh.write(json.dumps(m, default=float) + "\n")


def main(workers=4):
    apps = json.loads((GEN / "population.json").read_text())
    reg = json.loads((GEN / "registry.json").read_text())
    stage1(apps, reg, workers)
    ext = {a["app_id"]: pickle.loads((EXT / f"{a['app_id']}.pkl").read_bytes()) for a in apps}
    reg_emb = dict(np.load(PRE / "registry_emb.npz"))
    calibrate_face(apps, {k: reg_emb[k] for k in reg_emb}, ext)
    from app.modules.biometric import face
    face.threshold.cache_clear(); face.reuse_threshold.cache_clear()
    train_iforest(apps)
    stage2(apps, ext)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
