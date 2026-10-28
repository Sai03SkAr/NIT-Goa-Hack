"""Investigator chat (plan 4.6.8). Tools run deterministically from the IDs / feature names in the question;
the LLM (if configured) only phrases an answer from the tool results and may cite only codes found there."""
import json
import os
import re
from collections import Counter

from app import db
from app.schemas import REASONS

ID_RE = re.compile(r"\b(?:A\d{5}|L[0-9A-F]{8}|RS[0-9A-F]{4}\d+)\b", re.I)

FEATURE_DOCS = {
    "doc_qr_ocr_dob": "1 if the date of birth printed on the card equals the one inside the issuer-signed QR, else 0.",
    "doc_qr_ocr_name": "Fuzzy similarity between the printed name and the signed QR name.",
    "doc_sig_invalid": "1 if a QR is present but its Ed25519 signature does not verify against the issuer key.",
    "doc_forensic": "Cheap pixel-forensics score (background texture loss, stroke/font and contrast inconsistency).",
    "bio_sim_registry": "ArcFace cosine similarity between the selfie and the issuer's registry photo.",
    "bio_sim_card": "ArcFace cosine similarity between the selfie and the card portrait.",
    "bio_sim_card_registry": "Similarity between the card portrait and the registry photo (low = portrait swapped).",
    "bio_face_reuse_diff_name": "How many earlier applications used this face under a different name.",
    "bio_frames_consistent": "Server re-check: liveness frames are one identity with different head poses.",
    "beh_iki_cv": "Coefficient of variation of inter-key intervals; near zero means scripted typing.",
    "beh_paste_frac": "Share of form fields that were pasted rather than typed.",
    "beh_ks_links": "Earlier applications under other names with the same typing rhythm.",
    "beh_email_seq": "Earlier applications whose email has the same stem and a nearby number (rahul.k1, rahul.k2).",
    "reg_sim_age_days": "Days since the phone's SIM was activated (telecom registry).",
    "reg_file_age_ratio": "Age of the oldest credit account relative to adult age; thin files score low.",
    "cor_ring_score": "Ring score of the application's connected component (size, face/keystroke/email links).",
    "cor_comp_size": "Number of applications in the strongly linked component.",
}
PREFIX = {"doc_": "document agent", "bio_": "biometric agent", "beh_": "behaviour agent", "reg_": "registry agent",
          "cor_": "correlation agent"}


def get_case(app_id: str) -> dict | None:
    with db.session() as s:
        r = s.get(db.Application, app_id)
        if not r:
            return None
        reasons = sorted(((m["module"], x["code"], x["weight"]) for m in r.modules for x in m["reasons"]),
                         key=lambda t: -t[2])
        return {"app_id": r.app_id, "name": r.name, "band": r.band, "prob": None if r.prob is None else round(r.prob, 3), "pattern": r.fraud_label,
                "action": r.action, "hard_rules": r.rule_codes, "reasons": [c for _, c, w in reasons if w > 0][:8],
                "top_shap": r.shap[:3]}


def get_neighbors(app_id: str, hist, hops: int = 2) -> dict:
    """Strongly linked applications around app_id and which attributes link them."""
    from app.modules.correlation.history import STRONG
    i = hist.idx.get(app_id)
    if i is None:
        return {"members": [], "link_kinds": {}}
    adj: dict[int, set] = {}
    for a, b, d in hist.edges:
        if d["w"] >= STRONG:
            adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    seen, frontier = {i}, {i}
    for _ in range(hops):
        frontier = {n for f in frontier for n in adj.get(f, ())} - seen
        seen |= frontier
    return {"members": [hist.apps[k]["app_id"] for k in seen if k != i], **link_kinds(seen, hist)}


def link_kinds(idx: set, hist) -> dict:
    kinds = Counter(k for a, b, d in hist.edges if a in idx and b in idx for k in d["kinds"])
    names = Counter(hist.apps[k]["name"] for k in idx)
    return {"link_kinds": dict(kinds.most_common()), "distinct_names": len(names)}


def explain_feature(name: str) -> str:
    doc = FEATURE_DOCS.get(name)
    owner = next((v for k, v in PREFIX.items() if name.startswith(k)), "fusion")
    return f"{name} ({owner}): {doc}" if doc else f"{name} is a numeric feature produced by the {owner}."


def run_tools(question: str, hist) -> list[dict]:
    calls = []
    ids = list(dict.fromkeys(m.upper() for m in ID_RE.findall(question)))
    for a in ids[:8]:
        calls.append({"tool": "get_case", "args": {"app_id": a}, "result": get_case(a)})
    if len(ids) == 1:
        calls.append({"tool": "get_neighbors", "args": {"app_id": ids[0], "hops": 2},
                      "result": get_neighbors(ids[0], hist)})
    elif len(ids) > 1:
        idx = {hist.idx[a] for a in ids if a in hist.idx}
        calls.append({"tool": "get_neighbors", "args": {"app_ids": ids}, "result": link_kinds(idx, hist)})
    for f in sorted(set(re.findall(r"\b(?:doc|bio|beh|reg|cor)_[a-z0-9_]+\b", question.lower()))):
        calls.append({"tool": "explain_feature", "args": {"name": f}, "result": explain_feature(f)})
    return calls


def template(question: str, calls: list[dict]) -> str:
    if not calls:
        return ("Mention an application ID (e.g. A00123 or L1A2B3C4D) or a feature name (e.g. bio_sim_registry) "
                "and I'll pull the case, its linked applications and why they are linked.")
    out = []
    for c in calls:
        r = c["result"]
        if c["tool"] == "get_case":
            if r is None:
                out.append(f"{c['args']['app_id']}: not found.")
                continue
            why = "; ".join(f"{REASONS.get(x, x)} [{x}]" for x in r["reasons"][:4]) or "no risk signals"
            out.append(f"{r['app_id']} ({r['name']}): {r['band']} at p={r['prob']}, pattern {r['pattern']}. {why}.")
        elif c["tool"] == "get_neighbors":
            k = r.get("link_kinds", {})
            if not k:
                out.append("No strong links to other applications.")
                continue
            how = ", ".join(f"{n} {kind.replace('_', ' ')} link{'s' if n > 1 else ''}" for kind, n in k.items())
            who = f" Linked applications: {', '.join(r['members'][:10])}." if r.get("members") else ""
            out.append(f"They are connected by {how}, across {r['distinct_names']} distinct names.{who}")
        else:
            out.append(r)
    return " ".join(out)


def answer(question: str, hist) -> dict:
    calls = run_tools(question, hist)
    text, source = template(question, calls), "template"
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key and calls:
        try:
            from google import genai
            prompt = ("You are assisting a KYC fraud analyst. Answer the question in 2-5 sentences using ONLY the tool "
                      "results below. Cite reason codes in [BRACKETS] exactly as they appear. Never invent IDs, numbers, "
                      f"codes or decisions.\n\nQuestion: {question}\n\nTool results: {json.dumps(calls, default=str)}")
            out = genai.Client(api_key=key).models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), contents=prompt).text or ""
            allowed = set(re.findall(r"[A-Z]{3}_[A-Z_]+", json.dumps(calls, default=str)))
            if out and set(re.findall(r"\[([A-Z]{3}_[A-Z_]+)\]", out)) <= allowed:
                text, source = out.strip(), "llm"
        except Exception:
            pass
    return {"answer": text, "source": source, "tools": calls}
