"""Optional LLM for WORDING only (case summaries, investigator answers). Groq first, then Gemini; with neither, callers
use their deterministic templates. Never called on the decision path.
Groq key: GROQ_API_KEY or backend/.secrets/groq_api_key (git-ignored)."""
import os
import re

import httpx

from app.config import SECRETS_DIR

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CODE = re.compile(r"\b[A-Z]{2,5}_[A-Z0-9_]{2,}\b")


def cites_only(text: str, allowed: set[str]) -> bool:
    """Guardrail: every code-like token ANYWHERE in the text (not just in brackets) must be one we gave the model."""
    found = set(CODE.findall(text))
    return bool(found) and found <= allowed


def _groq_key() -> str:
    f = SECRETS_DIR / "groq_api_key"
    return os.getenv("GROQ_API_KEY") or (f.read_text().strip() if f.exists() else "")


def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def provider() -> str | None:
    return "groq" if _groq_key() else ("gemini" if _gemini_key() else None)


def complete(prompt: str, max_tokens: int = 600) -> str | None:
    """Text from the configured LLM, or None (no key, timeout, error). Callers must fall back to their template."""
    p = provider()
    try:
        if p == "groq":
            r = httpx.post(GROQ_URL, timeout=20, headers={"Authorization": f"Bearer {_groq_key()}"},
                           json={"model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "temperature": 0.2,
                                 "max_tokens": max_tokens, "reasoning_effort": "low",
                                 "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return (r.json()["choices"][0]["message"].get("content") or "").strip() or None
        if p == "gemini":
            from google import genai
            out = genai.Client(api_key=_gemini_key()).models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), contents=prompt).text
            return (out or "").strip() or None
    except Exception:
        return None
    return None
