"""LLM explains, never decides. Input = structured module outputs only; output must cite reason codes.
Falls back to a deterministic template when no key is set or the API fails."""
import json
import re

from app.llm import client as llm
from app.schemas import code_text

PROMPT = """You help a KYC reviewer. In 3 short sentences of plain English, say what the automated check decided and why.
Rules: use only the findings listed; after each finding you mention, put its code in square brackets exactly as given
(e.g. [REG_SIM_NEW]); do not mention models, SHAP, feature names or internal scores; never invent a finding, number
or action; do not change the decision; end with the recommended action, word for word.

Decision: {band} ({prob})
Required checks not passed: {unresolved}
Pattern: {ftype}
Recommended action: {action}
Findings (code: plain meaning): {reasons}"""


def _top_reasons(modules: list[dict], k=6):
    rs = [(m["module"], r["code"], r["weight"]) for m in modules for r in m["reasons"] if r["weight"] > 0]
    return sorted(rs, key=lambda x: -x[2])[:k]


def template(case: dict) -> str:
    rs = _top_reasons(case["modules"])
    if not rs:
        why = "No module raised a risk signal."
    else:
        why = "Main signals: " + "; ".join(f"{code_text(c)} [{c}]" for _, c, _ in rs[:4]) + "."
    gaps = case.get("rule_codes_ev") or []
    held = (" Not approvable automatically: " + "; ".join(code_text(c) for c in gaps[:4]) + ".") if gaps else ""
    return (f"Decision {case['band']} ({_prob(case)}).{held} {why} "
            f"Pattern: {case['fraud_label']}. Recommended action: {case['action']}.")


def _prob(case):
    return "risk model unavailable" if case.get("prob") is None else f"calibrated fraud probability {case['prob']:.2f}"


def summarize(case: dict) -> tuple[str, str]:
    """Returns (text, source) where source is 'llm' or 'template'."""
    rs = _top_reasons(case["modules"])
    out = llm.complete(PROMPT.format(band=case["band"], prob=_prob(case),
                                     unresolved=", ".join(code_text(c) for c in case.get("rule_codes_ev") or []) or "none",
                                     ftype=case["fraud_label"], action=case["action"],
                                     reasons=json.dumps({c: code_text(c) for _, c, _ in rs})))
    if not out or not llm.cites_only(out, {c for _, c, _ in rs}):  # guardrail: invented or uncited code -> template
        return template(case), "template"
    return out, "llm"
