"""How the consented digital-footprint check behaves on the synthetic population -> precomputed/footprint_eval.json.

Compares our one-sided rule (only contradictions count) with the naive "social score" that also marks people down
for a thin or new footprint, to show what that would cost genuine applicants. The footprint data is simulated
(data/gen_footprint.py), so these numbers show the design's behaviour, not real-world accuracy."""
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import GEN, PRE  # noqa: E402
from app.fusion import model  # noqa: E402
from app.graph.pipeline import footprint_module  # noqa: E402
from app.modules.footprint.provider import seeded_consent  # noqa: E402


def naive_flag(ev: dict) -> bool:
    """What an absence-penalising social score does: no, thin or brand-new footprint counts as suspicious."""
    f = ev.get("facts") or {}
    return ev.get("contradictions", 0) > 0 or ev.get("depth") in ("none", "thin") or (f.get("email_age_days") or 0) < 90


def main():
    apps = {a["app_id"]: a for a in json.loads((GEN / "population.json").read_text())}
    by = defaultdict(Counter)
    with open(PRE / "modules.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            a = apps[row["app_id"]]
            kind = "genuine" if a["label"] == 0 else a["fraud_type"]
            c = by[kind]
            c["n"] += 1
            if not seeded_consent(a["app_id"]):
                continue
            ext = PRE / "extract" / f"{a['app_id']}.pkl"
            sel = pickle.loads(ext.read_bytes())["bio"]["selfie"] if ext.exists() else None
            ev = footprint_module({**a, "consent": {"footprint": True}}, sel and sel["emb"])["evidence"]
            feats = {k: (float("nan") if v is None else v) for m in row["modules"] for k, v in m["features"].items()}
            c["consented"] += 1
            c["contradiction"] += ev["contradictions"] > 0
            c["compared"] += ev["score"] is not None
            c["naive_flag"] += naive_flag(ev)
            c[f"depth_{ev['depth']}"] += 1
            if ev["contradictions"] and model.decide(feats)["band"] == "APPROVE":
                c["contradiction_but_approved"] += 1
    rows = []
    for kind, c in by.items():
        k = max(c["consented"], 1)
        rows.append({"type": kind, "applicants": c["n"], "consented": c["consented"],
                     "compared": c["compared"], "contradiction_rate": round(c["contradiction"] / k, 3),
                     "naive_flag_rate": round(c["naive_flag"] / k, 3), "thin_or_none": c["depth_thin"] + c["depth_none"],
                     "contradiction_but_approved": c["contradiction_but_approved"]})
    rows.sort(key=lambda r: (r["type"] != "genuine", r["type"]))
    g = next(r for r in rows if r["type"] == "genuine")
    fraud = [r for r in rows if r["type"] != "genuine"]
    fk = sum(r["consented"] for r in fraud) or 1
    out = {"rows": rows, "genuine_contradiction_rate": g["contradiction_rate"], "genuine_naive_flag_rate": g["naive_flag_rate"],
           "fraud_contradiction_rate": round(sum(r["contradiction_rate"] * r["consented"] for r in fraud) / fk, 3),
           "fraud_naive_flag_rate": round(sum(r["naive_flag_rate"] * r["consented"] for r in fraud) / fk, 3),
           "note": "Simulated footprint data: shows the rule's behaviour (fairness, coverage), not real-world accuracy."}
    (PRE / "footprint_eval.json").write_text(json.dumps(out, indent=1))
    for r in rows:
        print(r)
    print({k: v for k, v in out.items() if k != "rows"})


if __name__ == "__main__":
    main()
