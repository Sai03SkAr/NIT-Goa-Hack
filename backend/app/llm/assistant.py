"""Analytics assistant: the floating "Ask TrueID" panel and the Investigator page.

It answers an analyst's questions about the live data: how fraud is trending, what a case means, how well the model
is doing, what the learning loop proposes, what a term or a page means, and how applications are linked.

Facts are gathered deterministically from the database and precomputed files (the "tools"), so every answer is
grounded. Without an LLM key the answer is written from templates. With a key (Groq or xAI Grok, see client.py) the
LLM only rewords the facts, and an answer that mentions an application ID or code we did not give it is discarded.
The assistant reads; it never changes a decision.
"""
import json
import re
from collections import Counter
from datetime import datetime, timedelta

from app import db, learning
from app.config import PRE
from app.llm import client as llm
from app.llm.investigator import ID_RE, explain_feature, get_neighbors
from app.schemas import code_text

PATTERNS = {"ring": "Synthetic ring", "first_party": "First-party / Frankenstein", "third_party": "Third-party fabricated",
            "mule": "Possible mule recruitment", "bot": "Bot / scripted", "tampered": "Tampered document",
            "injection": "Capture integrity / replay", "inconclusive": "Incomplete evidence"}
PATTERN_WORDS = {"ring": ("ring", "rings", "synthetic"), "first_party": ("first-party", "first party", "frankenstein"),
                 "third_party": ("third-party", "third party", "fabricated"), "mule": ("mule",), "bot": ("bot", "scripted", "automation"),
                 "tampered": ("tamper", "forged", "edited", "fake document"), "injection": ("injection", "replay", "virtual camera", "deepfake"),
                 "inconclusive": ("incomplete", "inconclusive")}

GLOSSARY = {
    "band": "Every application lands in one of three bands: APPROVE, REVIEW (a person looks at it) or REJECT.",
    "review": "REVIEW means the case waits for an analyst, because the score is in the middle or required evidence is missing.",
    "risk": "The fraud risk (0 to 1) is the calibrated model probability that the application is synthetic or fraudulent.",
    "recall": "Recall (fraud caught) is the share of fraudulent applications that were flagged for review or rejected.",
    "false alarm": "A false alarm is a genuine applicant who was sent to review or rejected. The false alarm rate is their share of all genuine applicants.",
    "roc": "ROC-AUC is the chance that a random fraud case scores higher than a random genuine one. 1.0 is perfect, 0.5 is guessing.",
    "auc": "ROC-AUC is the chance that a random fraud case scores higher than a random genuine one. 1.0 is perfect, 0.5 is guessing.",
    "precision": "Precision is the share of flagged applications that really were fraud.",
    "psi": "PSI (population stability index) measures how much a distribution moved between two time windows: below 0.1 is stable, 0.1 to 0.25 is worth watching, above 0.25 is drift.",
    "drift": "Drift means today's applicants look different from the ones the model learned from. The Learning loop measures it with PSI.",
    "shap": "SHAP values show how much each feature pushed this case's score up (towards fraud) or down.",
    "evidence": "Required evidence is the set of checks that must all pass for automatic approval: issuer signature, QR matches print, face matches, liveness, registry and more.",
    "liveness": "Liveness proves a real person is in front of the camera: a server-issued head-turn challenge checked across a burst of frames.",
    "consortium": "The cross-institution network lets banks compare keyed hashes of identifiers. No names or documents are shared, only whether an identifier was seen elsewhere.",
    "genuine profile": "The genuine profile is a set of readable rules learnt only from genuine applicants (explainable one-class classification, after IDRBT). A case outside every rule is unlike any genuine applicant; the broken rules are the explanation. It catches fraud types the model never saw, and it never decides.",
    "counterfactual": "The counterfactual shows what would change a decision, searching only what an applicant controls (typing, timing, devices, links). Robust means nothing they control can get it approved. Analyst-only.",
    "zero-day": "Zero-day fraud is a fraud type the model was never trained on. The Evaluation page's Unseen fraud tab retrains without each type and shows who still catches it.",
    "ring": "A synthetic ring is a group of applications under different names that share a face, device, typing rhythm or email pattern.",
    "mule": "Possible mule recruitment: a genuine person whose identity is being used to open accounts for someone else.",
    "cut-off": "The cut-offs decide the band from the risk score: below the approve cut-off is APPROVE, at or above the reject cut-off is REJECT.",
    "threshold": "The cut-offs decide the band from the risk score: below the approve cut-off is APPROVE, at or above the reject cut-off is REJECT.",
    "learning": "The Learning loop collects analyst decisions, watches for drift, proposes better cut-offs or a retrained model, and changes nothing until an analyst approves.",
}

PAGES = {
    "queue": ("Review queue", "Every application, riskiest first. The colour strip on the left of each row is its fraud risk; the decision, fraud pattern and recommended next step are on the row. Open a row for the full case."),
    "case": ("Case review", "One application: the verdict and risk at the top, one card per check (click to open its detail), whether the sources agree on name, date of birth, ID and face, which required checks passed, what drove the score, and your decision with the audit trail on the right."),
    "graph": ("Identity graph", "Applications joined by shared attributes. Rare shared values (a face, a device) are strong links; common ones (an IP) are weak. Clusters with many names are likely rings."),
    "metrics": ("Evaluation", "How well the system separates real from synthetic applicants on held-out data: fraud caught, false alarms, results per fraud pattern, what each check adds, and the cut-off trade-off."),
    "attack-lab": ("Attack Lab", "We attack our own system: each attack perturbs real test cases and re-scores them, to show which defences hold."),
    "learning": ("Learning loop", "TrueID learns from analyst decisions: it monitors drift, proposes better cut-offs or a retrained model, and an analyst approves or rolls back every change."),
    "chat": ("Investigator", "Ask anything about the data, a case or a page. Answers come from the live database and evaluation files."),
}


def page_of(path: str | None) -> str:
    p = (path or "").rstrip("/")
    if p.startswith("/dashboard/case"):
        return "case"
    for k in ("graph", "metrics", "attack-lab", "learning", "chat"):
        if p.startswith(f"/dashboard/{k}"):
            return k
    return "queue"


# ------------------------------------------------------------------ tools
def overview_stats() -> dict:
    with db.session() as s:
        rows = s.exec(db.select(db.Application.ts, db.Application.band, db.Application.fraud_type, db.Application.source,
                                db.Application.status)).all()
    n = len(rows)
    bands = Counter(r[1] for r in rows)
    out = {"applications": n, "bands": dict(bands),
           "band_share": {b: round(c / n, 3) for b, c in bands.items()} if n else {},
           "patterns": {PATTERNS.get(t, t): c for t, c in Counter(r[2] for r in rows if r[2] != "none").most_common()},
           "live": sum(r[3] != "seed" for r in rows), "waiting_for_analyst": sum(r[1] == "REVIEW" and r[4] == "open" for r in rows)}
    if rows:
        end = max(datetime.fromisoformat(r[0]) for r in rows)
        cut = (end - timedelta(days=7)).isoformat()
        recent = [r for r in rows if r[0] >= cut]
        out["last_7_days"] = {"applications": len(recent), "rejected": sum(r[1] == "REJECT" for r in recent),
                              "review": sum(r[1] == "REVIEW" for r in recent),
                              "patterns": {PATTERNS.get(t, t): c for t, c in Counter(r[2] for r in recent if r[2] != "none").most_common(4)}}
    return out


def top_reasons(days: int = 7, k: int = 5) -> list[dict]:
    with db.session() as s:
        rows = s.exec(db.select(db.Application).order_by(db.Application.ts.desc()).limit(2000)).all()
    if not rows:
        return []
    cut = (datetime.fromisoformat(rows[0].ts) - timedelta(days=days)).isoformat()
    c, text = Counter(), {}
    for r in rows:
        if r.ts < cut:
            continue
        for m in r.modules or []:
            for x in m.get("reasons", []):
                if x.get("weight", 0) > 0:
                    c[x["code"]] += 1
                    text.setdefault(x["code"], x.get("text") or code_text(x["code"]))
    return [{"code": code, "meaning": text[code], "cases": n} for code, n in c.most_common(k)]


def case_facts(app_id: str, hist) -> dict | None:
    with db.session() as s:
        r = s.get(db.Application, app_id)
    if r is None:
        return None
    reasons = sorted(((x["code"], x.get("text") or code_text(x["code"]), x.get("weight", 0)) for m in r.modules or [] for x in m.get("reasons", [])),
                     key=lambda t: -t[2])
    failed = [e["label"] for e in r.evidence or [] if e.get("required") and e["status"] != "PASS"]
    out = {"app_id": r.app_id, "name": r.name, "decision": r.band, "risk": None if r.prob is None else round(r.prob, 2),
           "pattern": r.fraud_label or "none", "next_step": r.action, "analyst_status": r.status,
           "set_by_rule": r.forced, "reasons": [{"code": c, "meaning": t} for c, t, w in reasons if w > 0][:5],
           "required_checks": {"passed": sum(1 for e in r.evidence or [] if e.get("required") and e["status"] == "PASS"),
                               "total": sum(1 for e in r.evidence or [] if e.get("required")), "not_passed": failed},
           "top_drivers": [{"feature": s_["feature"], "push": s_["shap"]} for s_ in (r.shap or [])[:3]]}
    if hist is not None:
        nb = get_neighbors(app_id, hist)
        out["linked_applications"] = {"count": len(nb.get("members", [])), "ids": nb.get("members", [])[:6],
                                      "linked_by": nb.get("link_kinds", {}), "distinct_names": nb.get("distinct_names")}
    return out


def pattern_facts(ptype: str) -> dict:
    with db.session() as s:
        rows = s.exec(db.select(db.Application).where(db.Application.fraud_type == ptype)
                      .order_by(db.Application.ts.desc()).limit(500)).all()
    return {"pattern": PATTERNS.get(ptype, ptype), "cases": len(rows), "rejected": sum(r.band == "REJECT" for r in rows),
            "in_review": sum(r.band == "REVIEW" for r in rows), "latest": [r.app_id for r in rows[:5]],
            "typical_reasons": [{"code": c, "meaning": code_text(c)} for c, _ in Counter(
                x["code"] for r in rows for m in r.modules or [] for x in m.get("reasons", []) if x.get("weight", 0) > 0).most_common(3)]}


def metric_facts() -> dict | None:
    p = PRE / "metrics.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    keep = ("recall_fdr", "fpr", "precision", "roc_auc", "pr_auc", "n_test", "n_fraud", "confusion")
    out = {k: m[k] for k in keep if k in m}
    if "per_type" in m:
        out["caught_by_pattern"] = {PATTERNS.get(t, t): v["flag_rate"] for t, v in m["per_type"].items() if t not in ("genuine", "hard_negative")}
    return out


def learning_facts(bands) -> dict:
    ov = learning.overview(bands)
    props = learning.proposals("proposed")
    return {"open_proposals": [p["title"] for p in props[:5]], "drift_alerts": ov["drift"]["alerts"],
            "score_drift": ov["drift"]["score"], "analyst_decisions": ov["feedback"]["analyst"],
            "current_cut_offs": bands, "applied_changes": ov["proposals"]["applied"],
            "challenger_model": ov["challenger"]["why"] or "ready"}


def gather(question: str, page: str, context_id: str | None, hist, bands) -> dict:
    q = question.lower()
    facts: dict = {"page": {"name": PAGES[page][0], "what_it_shows": PAGES[page][1]}}
    ids = list(dict.fromkeys(m.upper() for m in ID_RE.findall(question)))
    trend = re.search(r"trend|going|today|week|overall|summary|overview|how many|stats|analytic|status|happen|recent|latest|most common|top", q)
    about_this = re.search(r"\b(this|the) (case|application|applicant|person)\b|\b(him|her|they|them)\b|\bwhy\b|\blinked\b|\bdecid", q)
    if not ids and context_id and (about_this or (page == "case" and not trend)):
        ids = [context_id]  # on a case page, "why?" means this case; "how is fraud trending?" does not
    for a in ids[:3]:
        facts.setdefault("cases", []).append(case_facts(a, hist) or {"app_id": a, "found": False})
    for t, words in PATTERN_WORDS.items():
        if any(w in q for w in words):
            facts.setdefault("patterns", []).append(pattern_facts(t))
    if re.search(r"accura|recall|catch|caught|false (alarm|positive)|precision|auc|perform|how good|how well|metric|evaluat", q) or page == "metrics":
        facts["model_performance"] = metric_facts() or "Evaluation files are not built on this server yet (run scripts/build_all.sh)."
    if re.search(r"learn|drift|proposal|cut-?off|threshold|band|retrain|improv", q) or page == "learning":
        facts["learning_loop"] = learning_facts(bands)
    terms = {k: v for k, v in GLOSSARY.items() if re.search(rf"\b{re.escape(k)}", q)}
    if terms:
        facts["definitions"] = terms
    for f in sorted(set(re.findall(r"\b(?:doc|bio|beh|reg|cor)_[a-z0-9_]+\b", q))):
        facts.setdefault("features", []).append(explain_feature(f))
    if trend or not any(k in facts for k in ("cases", "patterns", "model_performance", "learning_loop", "definitions", "features")):
        facts["overview"] = overview_stats()
        facts["top_reasons_last_7_days"] = top_reasons()
    return facts


# ------------------------------------------------------------------ answer
def _pct(x):
    return f"{round(x * 100)}%"


def template(question: str, f: dict) -> str:
    out = []
    for c in f.get("cases", []):
        if c.get("found") is False:
            out.append(f"I can't find application {c['app_id']}.")
            continue
        risk = "no model score" if c["risk"] is None else f"fraud risk {c['risk']}"
        s = f"{c['app_id']} ({c['name']}) was decided {c['decision']} with {risk}"
        s += f", pattern: {c['pattern']}." if c["pattern"] != "none" else "."
        if c["reasons"]:
            s += f" Main signals: {'; '.join(r['meaning'].rstrip('.') for r in c['reasons'][:3])}."
        elif c["decision"] == "REVIEW" and not c["required_checks"]["not_passed"]:
            s += " No single red flag was raised: the combined score sits between the approve and reject cut-offs, so a person decides."
        else:
            s += " No risk signals were raised."
        rc = c["required_checks"]
        if rc["total"]:
            s += f" {rc['passed']} of {rc['total']} required checks passed" + (f"; not passed: {', '.join(rc['not_passed'][:3])}." if rc["not_passed"] else ".")
        la = c.get("linked_applications")
        if la and la["count"]:
            s += f" It is linked to {la['count']} other application{'s' if la['count'] != 1 else ''} by {', '.join(k.replace('_', ' ') for k in la['linked_by'])}."
        if c["decision"] != "APPROVE" and c.get("next_step"):
            s += f" Recommended next step: {c['next_step']}."
        out.append(s)
    for p in f.get("patterns", []):
        s = f"{p['pattern']}: {p['cases']} case{'s' if p['cases'] != 1 else ''}, {p['rejected']} rejected and {p['in_review']} in review."
        if p["typical_reasons"]:
            s += f" Typical signals: {'; '.join(r['meaning'] for r in p['typical_reasons'])}."
        if p["latest"]:
            s += f" Latest: {', '.join(p['latest'][:3])}."
        out.append(s)
    m = f.get("model_performance")
    if isinstance(m, dict) and m:
        s = f"On {m.get('n_test', 'the')} held-out applications the system caught {_pct(m['recall_fdr'])} of fraud with a false alarm rate of {_pct(m['fpr'])}"
        s += f" (ROC-AUC {m['roc_auc']})." if "roc_auc" in m else "."
        weak = {k: v for k, v in (m.get("caught_by_pattern") or {}).items() if v < 0.9}
        if weak:
            s += " Weakest patterns: " + ", ".join(f"{k} {_pct(v)}" for k, v in weak.items()) + "."
        out.append(s)
    elif isinstance(m, str):
        out.append(m)
    lf = f.get("learning_loop")
    if lf:
        s = f"The learning loop has {len(lf['open_proposals'])} open proposal{'s' if len(lf['open_proposals']) != 1 else ''}"
        s += (": " + "; ".join(lf["open_proposals"][:3]) + ".") if lf["open_proposals"] else "."
        s += f" {lf['drift_alerts']} drift alert{'s' if lf['drift_alerts'] != 1 else ''}; cut-offs are approve below {lf['current_cut_offs']['approve_below']} and reject at {lf['current_cut_offs']['reject_at']}."
        out.append(s)
    for v in f.get("definitions", {}).values():
        out.append(v)
    out += f.get("features", [])
    o = f.get("overview")
    if o is not None:
        if not o["applications"]:
            out.append("There are no applications in the database yet. Submit one from the KYC flow or a partner site, or seed the demo data.")
        else:
            b = o["band_share"]
            s = (f"There are {o['applications']} applications: {_pct(b.get('APPROVE', 0))} approved, {_pct(b.get('REVIEW', 0))} in review "
                 f"and {_pct(b.get('REJECT', 0))} rejected. {o['waiting_for_analyst']} are waiting for an analyst.")
            r7 = o.get("last_7_days")
            if r7:
                s += f" In the last 7 days: {r7['applications']} new, {r7['rejected']} rejected, {r7['review']} sent to review"
                s += (", mostly " + ", ".join(f"{k} ({v})" for k, v in list(r7["patterns"].items())[:3]) + ".") if r7["patterns"] else "."
            out.append(s)
        tr = f.get("top_reasons_last_7_days")
        if tr:
            out.append("Most common signals this week: " + "; ".join(f"{r['meaning'].rstrip('.')} ({r['cases']})" for r in tr[:3]) + ".")
    if not out or (list(f) == ["page"]):
        out.append(f"{f['page']['name']}: {f['page']['what_it_shows']}")
    elif re.search(r"this page|what is this|how (do i|to) read|what am i looking", question.lower()):
        out.insert(0, f"{f['page']['name']}: {f['page']['what_it_shows']}")
    return " ".join(out)


SYSTEM = ("You are the analytics assistant inside TrueID Shield, a KYC fraud-detection console used by bank analysts. "
          "Answer the analyst's question in plain, friendly English in 2 to 5 sentences, using ONLY the facts given as JSON. "
          "Never invent application IDs, numbers, names or codes. If the facts don't cover the question, say what you can "
          "answer instead. You explain; you never make or change a decision. Refer to applications by their ID.")


def _grounded(text: str, facts_json: str) -> bool:
    ids = {m.upper() for m in ID_RE.findall(text)}
    codes = set(llm.CODE.findall(text))
    return ids <= {m.upper() for m in ID_RE.findall(facts_json)} and codes <= set(llm.CODE.findall(facts_json))


def suggestions(page: str, f: dict) -> list[str]:
    s = {"queue": ["How is fraud trending this week?", "What are the most common fraud signals?", "Show me the synthetic rings"],
         "case": ["Why was this case flagged?", "Which applications is this one linked to?", "What should I check before deciding?"],
         "graph": ["How many rings are there?", "What makes a strong link?", "Show me the synthetic rings"],
         "metrics": ["How good is the model?", "Which fraud pattern is caught least?", "What is a false alarm?"],
         "attack-lab": ["Which attack works best against us?", "What is liveness?", "How good is the model?"],
         "learning": ["What is the learning loop proposing?", "Is there any drift?", "What is PSI?"],
         "chat": ["How is fraud trending this week?", "Explain the evaluation numbers", "What is the learning loop proposing?"]}[page]
    return s


def links(f: dict) -> list[dict]:
    out = [{"label": f"Open {c['app_id']}", "href": f"/dashboard/case/{c['app_id']}"} for c in f.get("cases", []) if c.get("found") is not False]
    if f.get("model_performance"):
        out.append({"label": "Evaluation", "href": "/dashboard/metrics"})
    if f.get("learning_loop"):
        out.append({"label": "Learning loop", "href": "/dashboard/learning"})
    if f.get("patterns"):
        out.append({"label": "Identity graph", "href": "/dashboard/graph"})
    return out[:4]


def ask(question: str, path: str | None = None, context_id: str | None = None, history: list[dict] | None = None,
        hist=None, bands=None) -> dict:
    page = page_of(path)
    facts = gather(question, page, context_id, hist, bands or {"approve_below": 0.3, "reject_at": 0.7})
    text, source = template(question, facts), "template"
    raw = json.dumps(facts, default=str)
    msgs = [{"role": "system", "content": SYSTEM}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("text"):
            msgs.append({"role": h["role"], "content": str(h["text"])[:800]})
    msgs.append({"role": "user", "content": f"Question: {question}\n\nFacts (JSON): {raw[:12000]}"})
    out = llm.chat(msgs, max_tokens=450) if llm.provider() else None
    if out and _grounded(out, raw):
        text, source = out, llm.provider()
    return {"answer": text, "source": source, "page": PAGES[page][0], "used": [k for k in facts if k != "page"],
            "suggestions": suggestions(page, facts), "links": links(facts)}
