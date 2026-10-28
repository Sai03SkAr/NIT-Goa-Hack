"""Score every seeded application with the trained fusion (same decide/fraud-type/summary code as live)
and load them into SQLite for the analyst console."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import db, policy  # noqa: E402
from app.config import DB_PATH, GEN, LIVE_HISTORY, PRE  # noqa: E402
from app.fusion import fraud_type, model  # noqa: E402
from app.graph.pipeline import jsonable  # noqa: E402
from app.llm.summary import template  # noqa: E402


def main():
    for stale in (DB_PATH, LIVE_HISTORY):  # a fresh seed starts with no live applicants
        if stale.exists():
            stale.unlink()
    db.init()
    apps = {a["app_id"]: a for a in json.loads((GEN / "population.json").read_text())}
    with db.session() as s, open(PRE / "modules.jsonl") as fh:
        for line in fh:
            row = json.loads(line)
            a, mods = apps[row["app_id"]], row["modules"]
            feats = {}
            for m in mods:
                feats.update({k: (float("nan") if v is None else v) for k, v in m["features"].items()})
            d = model.decide(feats)
            ft = fraud_type.classify(feats) if d["band"] != "APPROVE" else "none"
            act = fraud_type.action(ft)
            case = {"band": d["band"], "prob": d["prob"], "fraud_label": act["label"], "action": act["action"],
                    "modules": mods, "shap": d["shap"],
                    "rule_codes_ev": [c for c in d["rule_codes"] if c.startswith("EV_") or c == "MODEL_UNAVAILABLE"]}
            s.add(db.Application(
                app_id=a["app_id"], ts=a["ts"], source="seed", name=a["form"]["name"],
                id_last4=a["form"]["id_number"][-4:], form_masked=db.mask_form(a["form"]), prob=d["prob"],
                band=d["band"], forced=d["forced"], rule_codes=d["rule_codes"], fraud_type=ft, fraud_label=act["label"],
                action=act["action"], modules=jsonable(mods), shap=d["shap"], summary=template(case),
                evidence=policy.evidence_list(feats), model_status=d["model_status"], policy_version=d["policy_version"],
                card_path=a["card_path"], selfie_path=a["selfie_path"], truth_label=a["label"], truth_type=a["fraud_type"]))
        s.commit()
    print("seeded", len(apps))


if __name__ == "__main__":
    main()
