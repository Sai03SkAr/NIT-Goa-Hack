"""LLM explains, never decides. Input = structured module outputs only; output must cite reason codes.
Falls back to a deterministic template when no key is set or the API fails."""
import json
import os
import re

from app.schemas import REASONS

PROMPT = """You are a KYC fraud analyst assistant. Summarise this automated decision in 3-4 sentences for a human
reviewer. Rules: cite reason codes in square brackets exactly as given (e.g. [REG_SIM_NEW]); never invent a reason,
code, number or action; do not change the decision; end with the recommended action verbatim.

Decision: {band} (calibrated fraud probability {prob:.2f})
Fraud type: {ftype}
Recommended action: {action}
Reason codes (module: code, weight): {reasons}
Top model drivers (SHAP): {shap}"""


def _top_reasons(modules: list[dict], k=6):
    rs = [(m["module"], r["code"], r["weight"]) for m in modules for r in m["reasons"] if r["weight"] > 0]
    return sorted(rs, key=lambda x: -x[2])[:k]


def template(case: dict) -> str:
    rs = _top_reasons(case["modules"])
    if not rs:
        why = "No module raised a risk signal."
    else:
        why = "Main signals: " + "; ".join(f"{REASONS[c]} [{c}]" for _, c, _ in rs[:4]) + "."
    return (f"Decision {case['band']} with calibrated fraud probability {case['prob']:.2f}. {why} "
            f"Pattern: {case['fraud_label']}. Recommended action: {case['action']}.")


def summarize(case: dict) -> tuple[str, str]:
    """Returns (text, source) where source is 'llm' or 'template'."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        return template(case), "template"
    try:
        from google import genai
        client = genai.Client(api_key=key)
        rs = _top_reasons(case["modules"])
        prompt = PROMPT.format(band=case["band"], prob=case["prob"], ftype=case["fraud_label"], action=case["action"],
                               reasons=json.dumps(rs), shap=json.dumps(case.get("shap", [])))
        out = client.models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), contents=prompt).text
        cited = set(re.findall(r"\[([A-Z_]+)\]", out or ""))
        allowed = {c for _, c, _ in rs}
        if not out or not cited or not cited <= allowed:  # guardrail: any uncited/invented code -> template
            return template(case), "template"
        return out.strip(), "llm"
    except Exception:
        return template(case), "template"
