"""Attack Lab precompute (D5). Perturbs real test-split cards/selfies, re-runs the real document + biometric
extraction, re-scores with the trained fusion, and compares single modules vs fused.
Output: precomputed/attacks.json  (the Attack Lab page only displays this; one attack runs live in the demo)."""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import GEN, PRE  # noqa: E402

RNG = np.random.default_rng(1)


from app.attacks import blur, brightness, jpeg, noise, recapture  # noqa: E402


SWEEPS = {
    "jpeg": {"name": "JPEG compression sweep", "target": "Document", "fn": jpeg, "levels": [95, 75, 55, 40, 30],
             "x": "JPEG quality", "defense": "Semantic + signed-QR checks don't degrade with pixel quality"},
    "noise": {"name": "Gaussian noise sweep", "target": "Document, face", "fn": noise, "levels": [0, 6, 12, 20, 30],
              "x": "noise sigma", "defense": "Fusion holds when pixel evidence weakens"},
    "blur": {"name": "Blur sweep", "target": "Document, face", "fn": blur, "levels": [0, 0.8, 1.5, 2.2, 3.0],
             "x": "blur sigma", "defense": "Fusion holds"},
    "brightness": {"name": "Brightness / contrast", "target": "Document, face", "fn": brightness,
                   "levels": [1.0, 0.85, 0.7, 0.55, 1.3], "x": "contrast factor", "defense": "Augmented thresholds"},
    "recapture": {"name": "Screen recapture (perspective + moire)", "target": "Document, liveness", "fn": recapture,
                  "levels": [0, 0.5, 1.0, 1.5], "x": "strength", "defense": "QR stays readable; passive checks"},
}


def _features_for(args):
    """Re-extract doc + bio on perturbed images; return replaced feature dict."""
    app, attack, level, base = args
    from datetime import datetime
    from app.modules.biometric import agent as bio
    from app.modules.document import agent as doc
    from app.modules.registry.mocks import registry_face
    fn = SWEEPS[attack]["fn"]
    card = fn(cv2.imread(str(GEN / app["card_path"])), level)
    selfie = fn(cv2.imread(str(GEN / app["selfie_path"])), level)
    d = doc.assess(doc.extract(card), app["form"], datetime.fromisoformat(app["ts"]).date())
    b_ext = bio.extract(selfie, doc.normalize(card))
    reuse = {"diff_name": base.get("bio_face_reuse_diff_name", 0), "max_sim": base.get("bio_face_reuse_max_sim", 0)}
    b = bio.assess(b_ext, registry_face(app["form"]["id_number"]), app["liveness"], app["device"]["camera_labels"], reuse,
                   active_camera=app["device"].get("active_camera"))
    return {**base, **d.features, **b.features}


def score_rows(rows):
    from app.fusion.model import decide
    out = []
    for f in rows:
        d = decide(f)
        out.append({"prob": d["prob"], "band": d["band"], "doc_risk": f["doc_risk"], "pixel": f["doc_forensic"],
                    "bio_risk": f["bio_risk"]})
    return out


def summarize(y, scored):
    y = np.asarray(y)
    flag = np.array([s["band"] != "APPROVE" for s in scored])
    doc = np.array([s["doc_risk"] for s in scored])
    pix = np.array([s["pixel"] for s in scored])
    fused = np.array([max(s["prob"], .95) if s["band"] == "REJECT" else s["prob"] for s in scored])
    auc = lambda s: round(float(roc_auc_score(y, s)), 4) if len(set(y)) > 1 else None
    bands = np.array([s["band"] for s in scored])
    return {"fused_recall": round(float(flag[y == 1].mean()), 4), "fused_fpr": round(float(flag[y == 0].mean()), 4),
            "genuine_rejected": round(float((bands[y == 0] == "REJECT").mean()), 4),
            "fraud_approved": round(float((bands[y == 1] == "APPROVE").mean()), 4),
            "fused_auc": auc(fused), "doc_only_recall": round(float((doc[y == 1] >= .5).mean()), 4),
            "doc_only_auc": auc(doc), "pixel_only_auc": auc(pix)}


def main(workers=4, n_genuine=100):
    apps = {a["app_id"]: a for a in json.loads((GEN / "population.json").read_text())}
    df = pd.read_csv(PRE / "features.csv")
    te = df[df.day >= 20]
    sample = pd.concat([te[te.label == 1], te[te.label == 0].sample(min(n_genuine, (te.label == 0).sum()), random_state=0)])
    feat_cols = [c for c in df.columns if c.split("_")[0] in ("doc", "bio", "beh", "reg", "cor")]
    base = {r.app_id: {c: (np.nan if pd.isna(getattr(r, c)) else getattr(r, c)) for c in feat_cols} for r in sample.itertuples()}
    y = sample.label.values
    results = []
    with ProcessPoolExecutor(workers) as ex:
        for key, cfg in SWEEPS.items():
            pts = []
            for lv in cfg["levels"]:
                rows = list(ex.map(_features_for, [(apps[i], key, lv, base[i]) for i in sample.app_id], chunksize=8))
                pts.append({"level": lv, **summarize(y, score_rows(rows))})
                print(key, lv, pts[-1], flush=True)
            results.append({"id": key, "kind": "sweep", "name": cfg["name"], "target": cfg["target"], "x": cfg["x"],
                            "defense": cfg["defense"], "points": pts})
    hero = hero_attack(apps, te, workers)
    results += hero
    results += behavioural(df, apps)
    adaptive = PRE / "adaptive.json"
    if adaptive.exists():
        results.append(json.loads(adaptive.read_text()))
    (PRE / "attacks.json").write_text(json.dumps({"n_sample": int(len(sample)), "n_fraud": int(y.sum()),
                                                  "attacks": results}, indent=1, default=float))
    print("wrote attacks.json")


def _hero_one(app):
    """DeepID 'fine edit': Poisson-blend a new DOB onto a GENUINE card, form uses the edited DOB."""
    from datetime import datetime, timedelta
    from PIL import Image
    from app.modules.document import agent as doc
    from app.modules.document.card import poisson_edit
    from app.modules.document.dates import parse
    card = Image.open(GEN / app["card_path"]).convert("RGB").resize((1000, 630))
    new_dob = (parse(app["form"]["dob"]) - timedelta(days=1461)).strftime("%d/%m/%Y")
    edited = cv2.cvtColor(np.array(poisson_edit(card, "dob", new_dob)), cv2.COLOR_RGB2BGR)
    form = {**app["form"], "dob": new_dob}
    today = datetime.fromisoformat(app["ts"]).date()
    before = doc.assess(doc.extract(cv2.cvtColor(np.array(card), cv2.COLOR_RGB2BGR)), app["form"], today)
    after = doc.assess(doc.extract(edited), form, today)
    codes = {r.code for r in after.reasons}
    return {"pixel_before": before.features["doc_forensic"], "pixel_after": after.features["doc_forensic"],
            "qr_ocr_caught": "DOC_QR_OCR_MISMATCH" in codes, "form_caught": "DOC_FORM_MISMATCH" in codes,
            "forensic_flag": "DOC_FORENSIC_ANOMALY" in codes}


def hero_trufor(gen, apps, n=40):
    """TruFor on clean vs Poisson-edited cards: does it flag the edit, and does its heatmap point at the DOB field?"""
    from datetime import timedelta
    from PIL import Image
    from app.modules.document import trufor
    from app.modules.document.agent import normalize
    from app.modules.document.card import FIELD_BOXES, PORTRAIT, poisson_edit
    from app.modules.document.dates import parse
    if not trufor.available():
        return [{"detector": "TruFor", "value": "not installed (./scripts/setup_trufor.sh)"}]
    box_mean = lambda h, b: float(h[b[1]:b[3], b[0]:b[2]].mean())
    sc, se, dob_heat, portrait_heat = [], [], [], []
    for i in list(gen.app_id)[:n]:
        a = apps[i]
        clean = normalize(cv2.imread(str(GEN / a["card_path"])))
        new_dob = (parse(a["form"]["dob"]) - timedelta(days=1461)).strftime("%d/%m/%Y")
        pil = Image.fromarray(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB))
        edited = cv2.cvtColor(np.array(poisson_edit(pil, "dob", new_dob)), cv2.COLOR_RGB2BGR)
        s0, _ = trufor.infer(clean)
        s1, h1 = trufor.infer(edited)
        sc.append(s0); se.append(s1)
        dob_heat.append(box_mean(h1, FIELD_BOXES["dob"])); portrait_heat.append(box_mean(h1, PORTRAIT))
    yy = np.r_[np.zeros(len(sc)), np.ones(len(se))]
    print(f"trufor: clean mean {np.mean(sc):.3f} edited mean {np.mean(se):.3f}")
    return [{"detector": "TruFor score AUC, clean vs edited (0.5 = chance)", "value": round(float(roc_auc_score(yy, np.r_[sc, se])), 3)},
            {"detector": "TruFor flags edited cards (score >= 0.5)", "value": round(float(np.mean(np.array(se) >= 0.5)), 3)},
            {"detector": "TruFor flags CLEAN cards too (score >= 0.5)", "value": round(float(np.mean(np.array(sc) >= 0.5)), 3)},
            {"detector": "TruFor heat on the edited DOB field (mean, 0-1)", "value": round(float(np.mean(dob_heat)), 3)},
            {"detector": "TruFor heat on the untouched photo (mean, 0-1)", "value": round(float(np.mean(portrait_heat)), 3)}]


def hero_attack(apps, te, workers):
    gen = te[te.label == 0].sample(min(60, (te.label == 0).sum()), random_state=2)
    with ProcessPoolExecutor(workers) as ex:
        res = list(ex.map(_hero_one, [apps[i] for i in gen.app_id]))
    pb = np.array([r["pixel_before"] for r in res]); pa = np.array([r["pixel_after"] for r in res])
    yy = np.r_[np.zeros(len(pb)), np.ones(len(pa))]
    out = {"id": "poisson_dob", "kind": "single", "name": "Poisson-blended DOB edit (DeepID hero attack)",
           "target": "Document", "defense": "Signed QR <-> OCR mismatch catches what pixel forensics miss",
           "n": len(res),
           "rows": [{"detector": "Pixel forensics (edge/font/noise) AUC, clean vs edited",
                     "value": round(float(roc_auc_score(yy, np.r_[pb, pa])), 3)},
                    {"detector": "Pixel forensics flag rate on edited cards", "value": round(float(np.mean([r["forensic_flag"] for r in res])), 3)},
                    *hero_trufor(gen, apps),
                    {"detector": "Signed QR <-> OCR mismatch catch rate", "value": round(float(np.mean([r["qr_ocr_caught"] for r in res])), 3)}]}
    print("hero:", out["rows"])
    return [out]


def behavioural(df, apps):
    """Attacks scored from the seeded data itself (no re-extraction needed)."""
    ts = pd.read_csv(PRE / "test_scores.csv").set_index("app_id")
    te = df[df.day >= 20].set_index("app_id").join(ts[["band"]])
    flag = te.band != "APPROVE"
    out = []
    ring = te[te.fraud_type == "ring"]
    out.append({"id": "slow_low", "kind": "single", "name": "Slow-and-low ring (spread over time & devices)",
                "target": "Behavior / correlation", "defense": "Keystroke + face links still connect them",
                "rows": [{"detector": f"Ring recall: {s}", "value": round(float(flag[ring.index[ring["sub"] == s]].mean()), 3)}
                         for s in ("fast", "slow") if (ring["sub"] == s).any()]})
    bots = te[te.fraud_type == "bot"]
    hum = bots.beh_fill_time > 20
    out.append({"id": "humanized_bot", "kind": "single", "name": "Humanized bot (random delays)", "target": "Behavior",
                "defense": "Velocity + graph + liveness",
                "rows": [{"detector": "Scripted bot recall", "value": round(float(flag[bots.index[~hum]].mean()), 3) if (~hum).any() else None},
                         {"detector": "Humanized bot recall", "value": round(float(flag[bots.index[hum]].mean()), 3) if hum.any() else None}]})
    vc = te[te.bio_virtual_cam == 1]
    out.append({"id": "virtual_cam", "kind": "single", "name": "Virtual camera injection", "target": "Liveness",
                "defense": "Device-label hard flag",
                "rows": [{"detector": "Virtual-camera sessions blocked", "value": round(float(flag[vc.index].mean()), 3) if len(vc) else None},
                         {"detector": "n sessions", "value": int(len(vc))}]})
    rp = te[(te.bio_liveness_pass == 0)]
    out.append({"id": "replay", "kind": "single", "name": "Replay selfie (static photo / video)", "target": "Liveness",
                "defense": "Random challenge fails + moire/blur passive check",
                "rows": [{"detector": "Liveness-failed sessions flagged", "value": round(float(flag[rp.index].mean()), 3) if len(rp) else None},
                         {"detector": "n sessions", "value": int(len(rp))}]})
    sp = te[(te["sub"].isin(["stolen_id", "name_face_edit"]))]
    out.append({"id": "face_splice", "kind": "single", "name": "Face splice on a real card", "target": "Document, biometric",
                "defense": "Registry face mismatch + face reuse",
                "rows": [{"detector": "Spliced-portrait cases flagged", "value": round(float(flag[sp.index].mean()), 3) if len(sp) else None},
                         {"detector": "Registry face mismatch rate", "value": round(float((sp.bio_sim_registry < json.loads((Path(__file__).resolve().parents[1] / 'models/face_threshold.json').read_text())['threshold']).mean()), 3) if len(sp) else None}]})
    hn = te[te.fraud_type == "hard_negative"]
    tr = hn[hn["sub"] == "translit"]
    out.append({"id": "perturbation", "kind": "single", "name": "Attribute perturbation (typos, transliteration)",
                "target": "Correlation", "defense": "rapidfuzz + Indian-name normalisation",
                "rows": [{"detector": "Transliterated genuine names matching registry (fuzzy >= 0.8)",
                          "value": round(float((tr.reg_name_sim >= .8).mean()), 3) if len(tr) else None},
                         {"detector": "Same names under exact matching", "value": 0.0 if len(tr) else None}]})
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
