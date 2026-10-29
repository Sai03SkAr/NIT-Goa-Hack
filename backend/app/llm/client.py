"""Optional LLM for WORDING only (case summaries, investigator and assistant answers). Groq first, then xAI Grok, then
Gemini; with none, callers use their deterministic templates. Never called on the decision path.
Keys (environment or a git-ignored file in backend/.secrets/):
  Groq    GROQ_API_KEY              or backend/.secrets/groq_api_key
  Grok    XAI_API_KEY / GROK_API_KEY or backend/.secrets/xai_api_key
  Gemini  GEMINI_API_KEY / GOOGLE_API_KEY
TRUEID_LLM=groq|grok|gemini forces one provider when several keys are present."""
import os
import re

import httpx

from app.config import SECRETS_DIR

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
XAI_URL = "https://api.x.ai/v1/chat/completions"
CODE = re.compile(r"\b[A-Z]{2,5}_[A-Z0-9_]{2,}\b")


def cites_only(text: str, allowed: set[str]) -> bool:
    """Guardrail: every code-like token ANYWHERE in the text (not just in brackets) must be one we gave the model."""
    found = set(CODE.findall(text))
    return bool(found) and found <= allowed


def _secret_file(name: str) -> str:
    f = SECRETS_DIR / name
    return f.read_text().strip() if f.exists() else ""


def _groq_key() -> str:
    return os.getenv("GROQ_API_KEY") or _secret_file("groq_api_key")


def _xai_key() -> str:
    return os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY") or _secret_file("xai_api_key")


def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def provider() -> str | None:
    keys = {"groq": _groq_key, "grok": _xai_key, "gemini": _gemini_key}
    forced = os.getenv("TRUEID_LLM")
    if forced in keys:
        return forced if keys[forced]() else None
    return next((p for p, k in keys.items() if k()), None)


def _openai_style(url: str, key: str, model: str, messages: list[dict], max_tokens: int, extra: dict) -> str | None:
    r = httpx.post(url, timeout=25, headers={"Authorization": f"Bearer {key}"},
                   json={"model": model, "temperature": 0.2, "max_tokens": max_tokens, "messages": messages, **extra})
    r.raise_for_status()
    return (r.json()["choices"][0]["message"].get("content") or "").strip() or None


def chat(messages: list[dict], max_tokens: int = 600) -> str | None:
    """Text from the configured LLM for a list of {role, content} messages, or None (no key, timeout, error).
    Callers must fall back to their template."""
    p = provider()
    try:
        if p == "groq":
            return _openai_style(GROQ_URL, _groq_key(), os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), messages, max_tokens,
                                 {"reasoning_effort": "low"})
        if p == "grok":
            return _openai_style(XAI_URL, _xai_key(), os.getenv("XAI_MODEL", "grok-3-mini"), messages, max_tokens, {})
        if p == "gemini":
            from google import genai
            text = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
            out = genai.Client(api_key=_gemini_key()).models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), contents=text).text
            return (out or "").strip() or None
    except Exception:
        return None
    return None


def complete(prompt: str, max_tokens: int = 600) -> str | None:
    return chat([{"role": "user", "content": prompt}], max_tokens)
