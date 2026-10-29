"""Governed self-learning: TrueID improves from its own outcomes, but never changes its own decisions unsupervised.

The loop has four stages, each computed live from the application store:
  COLLECT  labels come from analyst dispositions only (plus generator truth on seeded rows). The system's own band is
           never a label: training on its own predictions would only teach it to agree with itself.
  MONITOR  score and feature drift (PSI, recent window vs reference), evidence-check health, analyst disagreement.
  PROPOSE  band recalibration from labelled outcomes, a retrained challenger model evaluated against the champion,
           advisories on noisy or under-used signals, and coaching gaps (fixable checks that hold genuine people).
  GOVERN   nothing is applied until an analyst approves it; every apply and rollback goes into the hash-chained audit
           log, and the previous state is kept so one click restores it. Required evidence rules are never learned
           away: changing them is a policy change (new POLICY_VERSION), so the loop can only advise on them.

Poisoning guards: minimum label counts, both classes present, a cap on how much of the feedback one analyst wrote,
and the existing four-eyes rule for approving what the system rejected.

Applicant tips come from the same data: which benign, fixable issues hold an applicant, ordered by what blocks
approval first and by how often people with that issue were approved after a retake. Fraud signals (linked
applications, device sharing, other banks, signature failures) are never explained to the applicant.
"""
import json
import shutil
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app import db, policy
from app.config import BANDS, MODELS, POLICY_VERSION, PRE

FN_COST, FP_COST = 10.0, 1.0          # a missed fraud costs ten false alarms (same as eval/train.py)
MIN_LABELS_BANDS = 30                  # labelled cases with a model score before bands may move
MIN_LABELS_RETRAIN = 50                # analyst labels before a challenger model is trained
MIN_PER_CLASS = 5
MAX_ANALYST_SHARE = 0.6                # above this, one person's judgement would dominate the change
LABELS_PER_CYCLE = 10                  # new analyst labels that trigger an automatic cycle
PSI_WATCH, PSI_DRIFT = 0.1, 0.25

# Checks an applicant can fix on their own. Everything else is a fraud signal and is never explained to them.
TIPS = {
    "capture_quality": ("Retake your photos in good light", [
        "Stand facing a window or a lamp, not with the light behind you.",
        "Lay the card flat on a dark surface and fill the frame with it.",
        "Hold still for a second before you capture, and avoid glare on the card."]),
    "doc_signature": ("Make the QR code on your card readable", [
        "Keep the whole card in the frame, including the QR code in the corner.",
        "Move closer until the QR code is sharp, and tilt the card slightly to remove glare."]),
    "form_consistency": ("Type your details exactly as printed on the card", [
        "Use the same spelling and order of your name as on the card.",
        "Enter your date of birth in the format shown on the card (DD/MM/YYYY)."]),
    "liveness": ("Complete the head-turn check", [
        "Keep your whole face inside the oval for the full check.",
        "Turn your head slowly when asked, then come back to face the camera.",
        "Remove sunglasses or a mask, and avoid strong backlight."]),
    "face_card": ("Retake your selfie so it can be matched to your card", [
        "Look straight at the camera with a neutral expression.",
        "Remove glasses, caps or anything covering your face.",
        "Use even lighting so both sides of your face are visible."]),
    "camera_hint": ("Use your phone's or laptop's built-in camera", [
        "Close apps that change or replace your camera feed (filters, virtual backgrounds).",
        "Allow camera access when the browser asks."]),
    "location": ("Allow location access for this session", [
        "Regulations require the location of a video KYC session.",
        "When the browser asks, choose Allow. It is used only for this check."]),
}
FIXABLE_STATUS = {"capture_quality": {"FAIL", "NOT_PROVIDED"}, "doc_signature": {"NOT_PROVIDED"},
                  "form_consistency": {"FAIL"}, "liveness": {"FAIL", "NOT_PROVIDED"}, "face_card": {"FAIL"},
                  "camera_hint": {"FAIL"}, "location": {"NOT_PROVIDED"}}


class Proposal(SQLModel, table=True):
    id: str = Field(primary_key=True)
    ts: str = Field(index=True)
    cycle: str = ""
    kind: str = ""                 # bands | retrain | advisory | health | coaching
    key: str = Field(default="", index=True)   # one open proposal per key; a newer cycle supersedes the older one
    title: str = ""
    rationale: str = ""
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON))
    change: dict = Field(default_factory=dict, sa_column=Column(JSON))
    impact: dict = Field(default_factory=dict, sa_column=Column(JSON))
    safeguards: list = Field(default_factory=list, sa_column=Column(JSON))
    applicable: bool = False       # advisories can only be acknowledged; they never change the system
    status: str = "proposed"       # proposed | applied | dismissed | acknowledged | rolled_back | superseded
    decided_by: str = ""
    decided_ts: str = ""
    previous: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Cycle(SQLModel, table=True):
    id: str = Field(primary_key=True)
    ts: str = Field(index=True)
    trigger: str = "manual"        # manual | labels | startup
    labels: int = 0
    proposals: int = 0
    duration_ms: int = 0
    summary: dict = Field(default_factory=dict, sa_column=Column(JSON))


_lock = threading.Lock()
_since_cycle = {"labels": 0}
now = lambda: datetime.now().isoformat(timespec="seconds")  # noqa: E731


# ------------------------------------------------------------------ collect
def _rows():
    with db.session() as s:
        return s.exec(db.select(db.Application).order_by(db.Application.ts)).all()


def _labellers() -> dict[str, str]:
    """app_id -> actor of the latest analyst disposition (from the hash-chained audit log)."""
    with db.session() as s:
        logs = s.exec(db.select(db.AuditLog).where(db.AuditLog.action.startswith("override:")).order_by(db.AuditLog.id)).all()
    return {a.app_id: a.actor for a in logs}


def label_of(r) -> tuple[int | None, str]:
    if r.status == "rejected":
        return 1, "analyst"
    if r.status == "approved":
        return 0, "analyst"
    if r.truth_label is not None and r.source == "seed":
        return int(r.truth_label), "seed truth"
    return None, ""


def features_of(r) -> dict:
    out = {}
    for m in r.modules or []:
        out.update({k: v for k, v in (m.get("features") or {}).items() if isinstance(v, (int, float)) and v is not None})
    return out


def feedback(rows=None) -> dict:
    rows = rows if rows is not None else _rows()
    who = _labellers()
    by_src, agree, actors, per_day = Counter(), defaultdict(Counter), Counter(), Counter()
    for r in rows:
        y, src = label_of(r)
        if y is None:
            continue
        by_src[src] += 1
        if src == "analyst":
            agree[r.band]["rejected" if y else "approved"] += 1
            actors[who.get(r.app_id, "unknown")] += 1
            per_day[r.ts[:10]] += 1
    n_an = sum(actors.values())
    known = Counter({k: v for k, v in actors.items() if k != "unknown"})  # imported labels have no author to weigh
    top = known.most_common(1)[0] if known else ("", 0)
    against = agree["APPROVE"]["rejected"] + agree["REJECT"]["approved"]  # resolving a REVIEW case overrules nothing
    return {"total": sum(by_src.values()), "by_source": dict(by_src), "analyst": n_an,
            "agreement": {b: dict(c) for b, c in agree.items()}, "against_automated": against,
            "analysts": len(known), "top_analyst_share": round(top[1] / sum(known.values()), 3) if known else 0.0,
            "per_day": [{"day": d, "n": n} for d, n in sorted(per_day.items())][-30:],
            "since_last_cycle": _since_cycle["labels"]}


# ------------------------------------------------------------------ monitor
def psi(ref, cur, bins=10) -> float | None:
    ref, cur = np.asarray(ref, float), np.asarray(cur, float)
    ref, cur = ref[~np.isnan(ref)], cur[~np.isnan(cur)]
    if len(ref) < 10 or len(cur) < 10:
        return None
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # near-constant feature: compare the share of the dominant value instead
        v = edges[0]
        a, b = max((ref == v).mean(), 1e-4), max((cur == v).mean(), 1e-4)
        return round(float((a - b) * np.log(a / b) + ((1 - a) - (1 - b)) * np.log(max(1 - a, 1e-4) / max(1 - b, 1e-4))), 4)
    edges[0], edges[-1] = -np.inf, np.inf
    a = np.histogram(ref, edges)[0] / len(ref)
    b = np.histogram(cur, edges)[0] / len(cur)
    a, b = np.clip(a, 1e-4, None), np.clip(b, 1e-4, None)
    return round(float(np.sum((a - b) * np.log(a / b))), 4)


def _status(p):
    return "unknown" if p is None else "drift" if p >= PSI_DRIFT else "watch" if p >= PSI_WATCH else "stable"


def windows(rows):
    """Recent = the last 7 days of applications (at least 20 of them); reference = everything before."""
    if not rows:
        return [], []
    end = datetime.fromisoformat(rows[-1].ts)
    cut = (end - timedelta(days=7)).isoformat()
    recent = [r for r in rows if r.ts >= cut]
    if len(recent) < 20 or len(recent) > 0.8 * len(rows):
        k = max(1, int(len(rows) * 0.3))
        recent = rows[-k:]
    ids = {r.app_id for r in recent}
    return [r for r in rows if r.app_id not in ids], recent


def drift(rows=None) -> dict:
    rows = rows if rows is not None else _rows()
    ref, cur = windows(rows)
    out = {"reference": {"n": len(ref), "from": ref[0].ts if ref else None, "to": ref[-1].ts if ref else None},
           "recent": {"n": len(cur), "from": cur[0].ts if cur else None, "to": cur[-1].ts if cur else None},
           "thresholds": {"watch": PSI_WATCH, "drift": PSI_DRIFT}}
    s = psi([r.prob for r in ref if r.prob is not None], [r.prob for r in cur if r.prob is not None])
    out["score"] = {"psi": s, "status": _status(s)}
    fr, fc = [features_of(r) for r in ref], [features_of(r) for r in cur]
    names = Counter(k for f in fr + fc for k in f)
    feats = []
    for n, c in names.items():
        if c < 0.5 * len(rows):
            continue
        p = psi([f.get(n, np.nan) for f in fr], [f.get(n, np.nan) for f in fc])
        if p is not None:
            feats.append({"feature": n, "psi": p, "status": _status(p)})
    out["features"] = sorted(feats, key=lambda x: -x["psi"])[:12]

    def mix(rs, attr):
        c = Counter(getattr(r, attr) for r in rs)
        return {k: round(v / max(len(rs), 1), 3) for k, v in c.items()}
    out["bands"] = {"reference": mix(ref, "band"), "recent": mix(cur, "band")}
    out["patterns"] = {"reference": mix(ref, "fraud_type"), "recent": mix(cur, "fraud_type")}
    out["checks"] = check_health(ref, cur)
    out["alerts"] = sum(x["status"] != "stable" for x in [out["score"], *out["features"]] if x["status"] != "unknown") \
        + sum(c["status"] != "ok" for c in out["checks"])
    return out


def _check_rates(rs):
    tot, fail, unav = Counter(), Counter(), Counter()
    for r in rs:
        for e in r.evidence or []:
            tot[e["check"]] += 1
            fail[e["check"]] += e["status"] == "FAIL"
            unav[e["check"]] += e["status"] == "UNAVAILABLE"
    return tot, fail, unav


def check_health(ref, cur):
    labels = {**policy.REQUIRED, **policy.INFORMATIONAL}
    t0, f0, u0 = _check_rates(ref)
    t1, f1, u1 = _check_rates(cur)
    out = []
    for c in sorted(set(t0) | set(t1)):
        fr0, fr1 = f0[c] / max(t0[c], 1), f1[c] / max(t1[c], 1)
        ur1 = u1[c] / max(t1[c], 1)
        status = "ok"
        if t1[c] >= 10 and ur1 > 0.05:
            status = "unavailable"          # the check itself is failing to run: infrastructure, not fraud
        elif t1[c] >= 10 and fr1 >= 0.05 and fr1 > 2 * fr0 + 0.02:
            status = "surge"                # many more failures than usual: a campaign or a broken capture flow
        out.append({"check": c, "label": labels.get(c, (c,))[0], "required": c in policy.REQUIRED,
                    "fail_ref": round(fr0, 3), "fail_recent": round(fr1, 3), "unavailable_recent": round(ur1, 3),
                    "n_recent": t1[c], "status": status})
    return sorted(out, key=lambda x: (x["status"] == "ok", -x["fail_recent"]))


# ------------------------------------------------------------------ propose
def _cost(lab, t):
    """Cost at approve cut-off t. Cases an evidence rule forced are flagged whatever the score."""
    c = 0.0
    for r, y in lab:
        flagged = bool(r.forced) or r.prob >= t
        c += FN_COST * (y == 1 and not flagged) + FP_COST * (y == 0 and flagged)
    return c


def _rates(lab, approve_below):
    fl = [(y, bool(r.forced) or r.prob >= approve_below) for r, y in lab]
    pos, neg = [f for y, f in fl if y == 1], [f for y, f in fl if y == 0]
    return {"recall": round(float(np.mean(pos)), 3) if pos else None, "false_alarms": round(float(np.mean(neg)), 3) if neg else None}


def propose_bands(rows, fb, current):
    lab = [(r, y) for r in rows for y, _ in [label_of(r)] if y is not None and r.prob is not None]
    n_pos = sum(y for _, y in lab)
    guards = [
        {"rule": f"At least {MIN_LABELS_BANDS} labelled cases with a score", "ok": len(lab) >= MIN_LABELS_BANDS, "value": len(lab)},
        {"rule": f"At least {MIN_PER_CLASS} fraud and {MIN_PER_CLASS} genuine", "ok": n_pos >= MIN_PER_CLASS and len(lab) - n_pos >= MIN_PER_CLASS,
         "value": f"{n_pos} / {len(lab) - n_pos}"},
        {"rule": f"No analyst wrote more than {int(MAX_ANALYST_SHARE * 100)}% of the feedback", "ok": fb["top_analyst_share"] <= MAX_ANALYST_SHARE or fb["analyst"] < 10,
         "value": f"{int(fb['top_analyst_share'] * 100)}%"},
        {"rule": "Required evidence rules are untouched", "ok": True, "value": "bands only"},
    ]
    if not all(g["ok"] for g in guards[:2]):
        return None, guards
    grid = [round(x, 2) for x in np.arange(0.05, 0.61, 0.05)]
    costs = {t: _cost(lab, t) for t in grid}
    best = min(grid, key=lambda t: (costs[t], abs(t - current["approve_below"])))
    cur_cost = _cost(lab, current["approve_below"])
    # Reject only where labelled cases above the cut-off are at least 95% fraud: genuine people are not auto-rejected.
    reject_at = current["reject_at"]
    for t in [round(x, 2) for x in np.arange(0.5, 0.96, 0.05)]:
        above = [y for r, y in lab if r.prob >= t]
        if len(above) >= 5 and np.mean(above) >= 0.95:
            reject_at = t
            break
    reject_at = max(reject_at, round(best + 0.1, 2))
    moved = abs(best - current["approve_below"]) >= 0.05 or abs(reject_at - current["reject_at"]) >= 0.05
    if not moved or (cur_cost > 0 and (cur_cost - costs[best]) / cur_cost < 0.1 and abs(reject_at - current["reject_at"]) < 0.05):
        return None, guards
    new = {"approve_below": best, "reject_at": reject_at}
    return {
        "kind": "bands", "key": "bands", "applicable": all(g["ok"] for g in guards),
        "title": f"Move the approve cut-off from {current['approve_below']} to {best}" + (
            f" and the reject cut-off to {reject_at}" if abs(reject_at - current["reject_at"]) >= 0.05 else ""),
        "rationale": f"On {len(lab)} labelled outcomes, a missed fraud costing {int(FN_COST)}× a false alarm, the total cost falls "
                     f"from {cur_cost:.0f} to {costs[best]:.0f}. The reject cut-off is the lowest score where labelled cases are at least 95% fraud.",
        "evidence": {"labels": len(lab), "fraud": n_pos, "curve": [{"t": t, "cost": costs[t]} for t in grid]},
        "change": {"bands": new},
        "impact": {"before": {"cost": cur_cost, **_rates(lab, current["approve_below"]), **current},
                   "after": {"cost": costs[best], **_rates(lab, best), **new}},
        "safeguards": guards,
    }, guards


def propose_advisories(rows):
    """Signals analysts keep overruling, and strong signals that still land in review."""
    stats = defaultdict(lambda: {"n": 0, "fraud": 0, "review": 0, "text": ""})
    for r in rows:
        y, src = label_of(r)
        if y is None or src != "analyst":
            continue
        for m in r.modules or []:
            for x in m.get("reasons", []):
                if x.get("weight", 0) <= 0:
                    continue
                s = stats[x["code"]]
                s["n"] += 1; s["fraud"] += y; s["review"] += r.band == "REVIEW"; s["text"] = x.get("text", x["code"])
    out = []
    for code, s in stats.items():
        if s["n"] < 8:
            continue
        rate = s["fraud"] / s["n"]
        if rate <= 0.2:
            out.append({"kind": "advisory", "key": f"noisy:{code}",
                        "title": f"“{s['text']}” is usually a false alarm",
                        "rationale": f"Analysts approved {s['n'] - s['fraud']} of {s['n']} cases this signal raised. Consider lowering its weight, "
                                     f"or better capture guidance if it comes from photo quality.",
                        "evidence": {"code": code, "n": s["n"], "fraud_rate": round(rate, 3)}})
        elif rate >= 0.9 and s["review"] / s["n"] >= 0.5:
            out.append({"kind": "advisory", "key": f"strong:{code}",
                        "title": f"“{s['text']}” is almost always fraud but goes to review",
                        "rationale": f"{s['fraud']} of {s['n']} cases with this signal were confirmed fraud, yet {s['review']} waited in the review queue. "
                                     f"Making it an evidence rule is a policy change ({POLICY_VERSION} → next) and needs sign-off.",
                        "evidence": {"code": code, "n": s["n"], "fraud_rate": round(rate, 3), "in_review": s["review"]}})
    return out


def propose_health(d):
    out = []
    for c in d["checks"]:
        if c["status"] == "unavailable":
            out.append({"kind": "health", "key": f"unavailable:{c['check']}", "title": f"“{c['label']}” could not run for {int(c['unavailable_recent'] * 100)}% of recent cases",
                        "rationale": "Cases where a required check cannot run are held for review, so the queue grows. Check the model files and services behind it.",
                        "evidence": c})
        elif c["status"] == "surge":
            out.append({"kind": "health", "key": f"surge:{c['check']}", "title": f"Failures of “{c['label']}” jumped from {int(c['fail_ref'] * 100)}% to {int(c['fail_recent'] * 100)}%",
                        "rationale": "A sudden rise usually means a coordinated attack or a broken capture step on a partner site. Look at recent cases failing this check.",
                        "evidence": c})
    if d["score"]["status"] == "drift":
        out.append({"kind": "health", "key": "drift:score", "title": "The fraud-score distribution has shifted",
                    "rationale": f"PSI {d['score']['psi']} between the reference and recent windows. Re-check the band cut-offs once enough labels arrive.",
                    "evidence": d["score"]})
    return out


def friction(rows=None):
    """Fixable checks that hold applicants, and how often those applicants turned out genuine."""
    rows = rows if rows is not None else _rows()
    acc = defaultdict(lambda: {"held": 0, "only": 0, "decided": 0, "approved": 0})
    for r in rows:
        bad = [e for e in r.evidence or [] if e.get("required") and e["status"] != "PASS"]
        for e in r.evidence or []:
            if e["check"] in FIXABLE_STATUS and e["status"] in FIXABLE_STATUS[e["check"]]:
                a = acc[e["check"]]
                a["held"] += 1
                a["only"] += len(bad) == 1 and bad[0]["check"] == e["check"]
                if r.status in ("approved", "rejected"):
                    a["decided"] += 1
                    a["approved"] += r.status == "approved"
    out = []
    for c, a in acc.items():
        out.append({"check": c, "title": TIPS[c][0], **a,
                    "resolution_rate": round(a["approved"] / a["decided"], 3) if a["decided"] else None})
    return sorted(out, key=lambda x: -x["held"])


def propose_coaching(rows):
    out = []
    for f in friction(rows):
        if f["held"] >= 10 and (f["resolution_rate"] or 0) >= 0.6:
            out.append({"kind": "coaching", "key": f"coach:{f['check']}",
                        "title": f"Better guidance on “{f['title'].lower()}” would unblock genuine people",
                        "rationale": f"{f['held']} applications were held by this fixable check ({f['only']} by it alone), and analysts approved "
                                     f"{int(f['resolution_rate'] * 100)}% of those they decided. In-flow guidance and the applicant tip are already live; "
                                     f"consider a real-time quality check before upload.",
                        "evidence": f})
    return out


def challenger_readiness(fb) -> dict:
    """Retraining needs the base model, its training table and enough analyst labels."""
    from app.fusion import model as F
    have_model = F.load() is not None
    have_data = (PRE / "features.csv").exists()
    need = max(0, MIN_LABELS_RETRAIN - fb["analyst"])
    ready = have_model and have_data and need == 0
    why = None if ready else ("The base model is not built on this machine (run scripts/build_all.sh)." if not have_model
                              else "The training table precomputed/features.csv is missing." if not have_data
                              else f"Waiting for {need} more analyst decisions.")
    return {"ready": ready, "why": why, "labels": fb["analyst"], "needed": MIN_LABELS_RETRAIN,
            "champion": (F.manifest() or {}).get("git_commit") if have_model else None}


def propose_retrain(rows, cycle_id):
    """Train a challenger on base training data + analyst feedback, compare it with the champion, never auto-promote."""
    import joblib
    import pandas as pd
    import xgboost as xgb
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import roc_auc_score
    from app.fusion import model as F

    champ, cal, _, names = F.load()
    df = pd.read_csv(PRE / "features.csv")
    tr, ca, te = df[df.day < 16], df[(df.day >= 16) & (df.day < 20)], df[df.day >= 20]
    fbk = [(features_of(r), y) for r in rows for y, src in [label_of(r)] if src == "analyst"]
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(fbk))
    hold = [fbk[i] for i in idx[: max(10, len(fbk) // 3)]]
    use = [fbk[i] for i in idx[max(10, len(fbk) // 3):]]
    X = lambda rs: np.array([[f.get(n, np.nan) for n in names] for f, _ in rs], dtype=np.float32)  # noqa: E731
    Xtr = np.vstack([tr[names].values.astype(np.float32), X(use)]) if use else tr[names].values.astype(np.float32)
    ytr = np.concatenate([tr.label.values, [y for _, y in use]])
    w = np.concatenate([np.ones(len(tr)), np.full(len(use), 3.0)])  # recent, human-confirmed outcomes count more
    params = {k: v for k, v in champ.get_params().items() if k in ("n_estimators", "max_depth", "learning_rate", "subsample",
                                                                   "colsample_bytree", "min_child_weight", "random_state")}
    pos = ytr.mean()
    m = xgb.XGBClassifier(**params, eval_metric="logloss", scale_pos_weight=(1 - pos) / max(pos, 1e-3), n_jobs=4)
    m.fit(Xtr, ytr, sample_weight=w)
    iso = IsotonicRegression(out_of_bounds="clip").fit(m.predict_proba(ca[names].values.astype(np.float32))[:, 1], ca.label.values)

    def auc(model, c, Xs, ys):
        return round(float(roc_auc_score(ys, c.predict(model.predict_proba(Xs)[:, 1]))), 4) if len(set(ys)) == 2 else None
    Xte, yte = te[names].values.astype(np.float32), te.label.values
    Xh, yh = X(hold), np.array([y for _, y in hold])
    res = {"base_test": {"champion": auc(champ, cal, Xte, yte), "challenger": auc(m, iso, Xte, yte), "n": int(len(te))},
           "feedback_holdout": {"champion": auc(champ, cal, Xh, yh), "challenger": auc(m, iso, Xh, yh), "n": len(hold)}}
    no_regress = res["base_test"]["challenger"] >= res["base_test"]["champion"] - 0.005
    fh = res["feedback_holdout"]
    better = fh["champion"] is not None and fh["challenger"] >= fh["champion"] + 0.01
    pid = "P-" + uuid.uuid4().hex[:6].upper()
    out_dir = MODELS / "candidates" / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    m.save_model(out_dir / "xgb.json")
    joblib.dump(iso, out_dir / "calibrator.joblib")
    shutil.copy(MODELS / "features.json", out_dir / "features.json")
    man = json.loads((MODELS / "manifest.json").read_text())
    man.update({"parent": man.get("git_commit"), "learning_cycle": cycle_id, "feedback_labels": len(use)})
    (out_dir / "manifest.json").write_text(json.dumps(man, indent=2))
    guards = [{"rule": "No regression on the original test split (≤ 0.005 ROC-AUC)", "ok": no_regress,
               "value": f"{res['base_test']['champion']} → {res['base_test']['challenger']}"},
              {"rule": "Better on held-out analyst feedback (≥ +0.01 ROC-AUC)", "ok": better,
               "value": f"{fh['champion']} → {fh['challenger']}"},
              {"rule": "Same features and policy version as the champion", "ok": True, "value": POLICY_VERSION}]
    return {"id": pid, "kind": "retrain", "key": "retrain", "applicable": no_regress and better,
            "title": "Promote a challenger model retrained with analyst feedback" if no_regress and better
            else "Challenger model trained, but not better than the champion",
            "rationale": f"Trained on the base training split plus {len(use)} analyst-confirmed outcomes (weighted 3×), "
                         f"tested on {len(hold)} held-out decisions and the original test split.",
            "evidence": res, "change": {"model": pid}, "impact": res, "safeguards": guards}


# ------------------------------------------------------------------ govern
def run_cycle(trigger: str = "manual", bands: dict | None = None) -> dict:
    with _lock:
        t0 = time.time()
        cid = "C-" + datetime.now().strftime("%m%d-%H%M") + "-" + uuid.uuid4().hex[:4].upper()
        rows = _rows()
        fb = feedback(rows)
        d = drift(rows)
        current = bands or BANDS
        props = []
        b, _ = propose_bands(rows, fb, current)
        if b: props.append(b)
        props += propose_advisories(rows) + propose_health(d) + propose_coaching(rows)
        ready = challenger_readiness(fb)
        if ready["ready"]:
            try:
                props.append(propose_retrain(rows, cid))
            except Exception as e:  # a failed training run must not stop the rest of the cycle
                ready = {**ready, "ready": False, "why": f"Training failed: {type(e).__name__}"}
        with db.session() as s:
            open_ = {p.key: p for p in s.exec(db.select(Proposal).where(Proposal.status == "proposed")).all()}
            for p in props:
                if p["key"] in open_:
                    open_[p["key"]].status = "superseded"
                    s.add(open_[p["key"]])
                s.add(Proposal(id=p.pop("id", None) or "P-" + uuid.uuid4().hex[:6].upper(), ts=now(), cycle=cid, **p))
            c = Cycle(id=cid, ts=now(), trigger=trigger, labels=fb["total"], proposals=len(props),
                      duration_ms=int((time.time() - t0) * 1000),
                      summary={"drift_alerts": d["alerts"], "score_psi": d["score"]["psi"], "analyst_labels": fb["analyst"],
                               "challenger": ready, "kinds": dict(Counter(p["kind"] for p in props))})
            s.add(c)
            s.commit()
            s.refresh(c)
        _since_cycle["labels"] = 0
        db.audit(None, "LEARNING", f"cycle:{cid}", f"{len(props)} proposals ({trigger})")
        return c.model_dump()


def note_label():
    """Called after every analyst disposition; enough new labels start a cycle in the background."""
    _since_cycle["labels"] += 1
    if _since_cycle["labels"] >= LABELS_PER_CYCLE:
        from app.graph import pipeline as P
        threading.Thread(target=run_cycle, kwargs={"trigger": "labels", "bands": P.Runtime.bands}, daemon=True).start()


def _swap_model(src_dir, archive_to=None):
    from app.fusion import model as F
    files = ("xgb.json", "calibrator.joblib", "features.json", "manifest.json")
    if archive_to:
        archive_to.mkdir(parents=True, exist_ok=True)
        for f in files:
            if (MODELS / f).exists():
                shutil.copy(MODELS / f, archive_to / f)
    for f in files:
        shutil.copy(src_dir / f, MODELS / f)
    F.load.cache_clear()
    F.manifest.cache_clear()


def decide(pid: str, action: str, actor: str, runtime) -> dict:
    """apply | dismiss | acknowledge | rollback. Applying changes the live system; everything is audited."""
    with db.session() as s:
        p = s.get(Proposal, pid)
        if p is None:
            raise KeyError(pid)
        if action == "rollback":
            if p.status != "applied":
                raise ValueError("only an applied change can be rolled back")
            if p.kind == "bands":
                runtime.bands = dict(p.previous["bands"])
            elif p.kind == "retrain":
                _swap_model(MODELS / "archive" / pid)
            p.status = "rolled_back"
        else:
            if p.status != "proposed":
                raise ValueError(f"this proposal is already {p.status}")
            if action == "apply":
                if not p.applicable:
                    raise ValueError("this proposal did not pass its safeguards, or is advisory only")
                if p.kind == "bands":
                    p.previous = {"bands": dict(runtime.bands)}
                    runtime.bands = dict(p.change["bands"])
                elif p.kind == "retrain":
                    p.previous = {"model": "archive/" + pid}
                    _swap_model(MODELS / "candidates" / pid, MODELS / "archive" / pid)
                p.status = "applied"
            elif action in ("dismiss", "acknowledge"):
                p.status = "dismissed" if action == "dismiss" else "acknowledged"
            else:
                raise ValueError("unknown action")
        p.decided_by, p.decided_ts = actor, now()
        s.add(p)
        s.commit()
        s.refresh(p)
        out = p.model_dump()
    db.audit(None, "LEARNING", f"proposal:{pid}:{out['status']}", out["title"][:200], actor)
    return out


def restore(runtime):
    """At startup, re-apply the latest applied band change (bands live in memory)."""
    with db.session() as s:
        p = s.exec(db.select(Proposal).where(Proposal.kind == "bands", Proposal.status == "applied")
                   .order_by(Proposal.decided_ts.desc())).first()
    if p:
        runtime.bands = dict(p.change["bands"])


def proposals(status: str | None = None) -> list[dict]:
    with db.session() as s:
        st = db.select(Proposal).order_by(Proposal.ts.desc())
        if status:
            st = st.where(Proposal.status == status)
        return [p.model_dump() for p in s.exec(st.limit(200)).all()]


def cycles(limit=30) -> list[dict]:
    with db.session() as s:
        return [c.model_dump() for c in s.exec(db.select(Cycle).order_by(Cycle.ts.desc()).limit(limit)).all()]


def overview(runtime_bands) -> dict:
    rows = _rows()
    fb = feedback(rows)
    d = drift(rows)
    ps = proposals()
    st = Counter(p["status"] for p in ps)
    cs = cycles(1)
    return {"applications": len(rows), "feedback": fb, "drift": {"alerts": d["alerts"], "score": d["score"],
            "top_feature": d["features"][0] if d["features"] else None},
            "proposals": {"open": st["proposed"], "applied": st["applied"], "rolled_back": st["rolled_back"],
                          "dismissed": st["dismissed"] + st["acknowledged"]},
            "challenger": challenger_readiness(fb), "bands": runtime_bands, "last_cycle": cs[0] if cs else None,
            "next_cycle_in": max(0, LABELS_PER_CYCLE - _since_cycle["labels"]), "policy_version": POLICY_VERSION}


# ------------------------------------------------------------------ applicant tips
def tips_for(r, rows=None) -> dict:
    """What an applicant can do to get through. Only fixable issues are named; fraud signals never are."""
    if r.band == "REJECT":  # the decision is made; the next step is the assisted channel, not a retake
        return {"app_id": r.app_id, "headline": "", "tips": [], "manual_review": False, "note": None}
    fr = {f["check"]: f for f in friction(rows)} if rows is not None else {}
    items, manual = [], False
    for e in r.evidence or []:
        c, stt = e["check"], e["status"]
        if stt == "PASS" or stt == "SIMULATED" or c == "profile":  # the genuine profile explains, never holds
            continue
        if c in FIXABLE_STATUS and stt in FIXABLE_STATUS[c]:
            title, steps = TIPS[c]
            f = fr.get(c)
            items.append({"check": c, "title": title, "steps": steps, "blocking": bool(e.get("required")),
                          "why": "Without this we cannot approve automatically." if e.get("required") else "Needed to complete the session record.",
                          "resolution_rate": f["resolution_rate"] if f else None, "seen": f["held"] if f else None})
        elif e.get("required") or stt == "FAIL":
            manual = True
    items.sort(key=lambda x: (not x["blocking"], -(x["resolution_rate"] or 0)))
    if r.band == "REVIEW" and not items:
        manual = True
    head = ("You're verified. Nothing to fix." if r.band == "APPROVE" and not items
            else f"{len(items)} thing{'s' if len(items) != 1 else ''} you can fix to finish faster" if items
            else "A specialist will review a few details. You don't need to do anything right now.")
    return {"app_id": r.app_id, "headline": head, "tips": items, "manual_review": manual,
            "note": "A specialist will also check some details by hand. This is routine." if manual and items else None}
