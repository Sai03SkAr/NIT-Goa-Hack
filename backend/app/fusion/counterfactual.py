"""What would change this decision? Analyst-only.

After the counterfactual analysis in IDRBT's fraud XAI work (Vivek, Ravi et al., arXiv 2211.10595), restricted to what
an applicant can actually change: a greedy search over the behaviour and graph features (typing, timing, devices,
velocity, links), using values genuine applicants really have. Evidence an applicant cannot fake (signed documents,
face, registries) is never searched; it is listed as what blocks approval.

The answer is a per-decision robustness margin:
- held or rejected, and nothing the applicant controls can get it approved  -> robust
- held or rejected, but changing applicant-controlled signals would approve it -> fragile, look closer
- approved, and how little it would take to push it into review                -> margin to the line

Never shown to applicants or partners: it would tell an attacker what to change."""
import numpy as np

from app import policy
from app.fusion import model, profile

FIXED = {"cor_comp_face_edges", "cor_id_names"}  # as in eval/adaptive_attacker: your own face, a shared ID


def controllable(names: list[str]) -> list[str]:
    return [c for c in names if c.startswith("beh_") or (c.startswith("cor_") and c not in FIXED)]


def explain(feats: dict, bands=None, max_steps: int = 8) -> dict:
    loaded, P = model.load(), profile.load()
    if loaded is None or model.stale() or P is None or P.get("quantiles") is None:
        return {"available": False, "reason": "model or genuine profile not built"}
    m, cal, _, names = loaded

    def prob(f: dict) -> float:
        return float(cal.predict([float(m.predict_proba(model.vectorize(f, names))[0, 1])])[0])

    def band(f: dict, p: float) -> dict:
        return policy.decide(f, {"prob": p, "status": "ok"}, bands)

    base_p = prob(feats)
    base = band(feats, base_p)
    idx = {f: i for i, f in enumerate(P["features"])}
    ctrl = [c for c in controllable(names) if c in idx]
    cands = {c: sorted({round(float(P["quantiles"][q][idx[c]]), 4) for q in (0.1, 0.5, 0.9)}) for c in ctrl}
    want_down = base["band"] != "APPROVE"  # held/rejected: can it be approved? approved: how close to review?

    f, p, changes = dict(feats), base_p, []
    for _ in range(max_steps):
        best = None
        for c in ctrl:
            for v in cands[c]:
                if f.get(c) == v:
                    continue
                g = dict(f)
                g[c] = v
                q = prob(g)
                gain = (p - q) if want_down else (q - p)
                if gain > 1e-4 and (best is None or gain > best[0]):
                    best = (gain, c, v, q)
        if best is None:
            break
        _, c, v, p = best
        changes.append({"feature": c, "from": None if not np.isfinite(feats.get(c, np.nan)) else round(float(feats[c]), 3),
                        "to": v, "risk_after": round(p, 3)})
        f[c] = v
        if band(f, p)["band"] != base["band"]:
            break
    reached = band(f, p)
    blocking = [{"check": c, "label": policy.REQUIRED[c][0], "status": base["checks"][c]} for c in base["unresolved"]]
    flips = reached["band"] != base["band"]
    if want_down:
        verdict = ("fragile" if reached["band"] == "APPROVE" else "robust")
        text = ("Changing only things the applicant controls would get this approved. Look closer before trusting "
                "the signals listed below." if verdict == "fragile" else
                "Nothing the applicant controls can get this approved. The decision rests on "
                + ("evidence they cannot fake: " + "; ".join(b["label"] for b in blocking) if blocking
                   else "the model's risk, which stays high whatever behaviour they show") + ".")
    else:
        verdict = "close to the line" if flips and len(changes) <= 2 else "comfortable"
        text = (f"Approved with risk {base_p:.2f} (cut-off {(bands or policy.BANDS)['approve_below']:.2f}). "
                + (f"{len(changes)} applicant-controlled change(s) would push it into review." if flips
                   else "No applicant-controlled change pushes it into review."))
    return {"available": True, "band": base["band"], "risk": round(base_p, 3), "verdict": verdict, "summary": text,
            "applicant_controllable": {"reachable_band": reached["band"], "best_risk": round(p, 3), "flips": flips,
                                       "changes": changes, "searched_features": len(ctrl)},
            "blocking_evidence": blocking}
