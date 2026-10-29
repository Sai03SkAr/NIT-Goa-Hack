"""Ask TrueID answers from live data, works without an LLM key, and throws away LLM answers that invent IDs."""
import pytest

import learning_data as LD  # tests/ is on sys.path (see test_learning.py)
from app import db
from app.llm import assistant as A
from app.llm import client as llm

AUTH = {"X-Analyst-Key": "test-analyst-key"}


@pytest.fixture()
def data(client, monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: None)   # deterministic: no LLM in tests
    LD.wipe()
    rows = LD.make_rows(n=120, prefix="L")
    for i, r in enumerate(rows):
        r.app_id = f"L{i:08X}"                            # the live-ID format the assistant recognises
        r.fraud_label = "Synthetic ring" if r.fraud_type == "ring" else ""
    LD.load(rows)
    yield rows
    LD.wipe()


def test_trend_question_uses_live_counts(data):
    out = A.ask("How is fraud trending this week?", "/dashboard")
    assert "overview" in out["used"] and out["source"] == "template"
    assert "120 applications" in out["answer"] and "last 7 days" in out["answer"]


def test_case_question_on_the_case_page_uses_that_case(data):
    ring = next(r for r in data if r.fraud_type == "ring")
    out = A.ask("Why was this case flagged?", f"/dashboard/case/{ring.app_id}", ring.app_id)
    assert out["used"][0] == "cases" and ring.app_id in out["answer"]
    assert "densely linked cluster" in out["answer"]
    assert {"label": f"Open {ring.app_id}", "href": f"/dashboard/case/{ring.app_id}"} in out["links"]


def test_pattern_glossary_and_page_help(data):
    out = A.ask("Show me the synthetic rings", "/dashboard/graph")
    assert "patterns" in out["used"] and "Synthetic ring:" in out["answer"]
    out = A.ask("What is PSI?", "/dashboard/learning")
    assert "population stability index" in out["answer"]
    out = A.ask("What am I looking at on this page?", "/dashboard/metrics")
    assert out["answer"].startswith("Evaluation:")


def test_unknown_case_is_said_plainly(data):
    out = A.ask("Tell me about LDEADBEEF", "/dashboard")
    assert "can't find application LDEADBEEF" in out["answer"]


def test_llm_answer_that_invents_an_id_is_discarded(data, monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: "grok")
    monkeypatch.setattr(llm, "chat", lambda msgs, max_tokens=600: "LFFFFFFFF is the ringleader.")
    out = A.ask("How is fraud trending?", "/dashboard")
    assert out["source"] == "template" and "LFFFFFFFF" not in out["answer"]
    monkeypatch.setattr(llm, "chat", lambda msgs, max_tokens=600: "Fraud is steady this week.")
    assert A.ask("How is fraud trending?", "/dashboard")["source"] == "grok"


def test_empty_database_gets_a_helpful_answer(client, monkeypatch):
    monkeypatch.setattr(llm, "provider", lambda: None)
    LD.wipe()
    assert "no applications" in A.ask("How is it going?", "/dashboard")["answer"]


def test_assistant_api_is_analyst_only(client, data):
    body = {"question": "How is fraud trending?", "path": "/dashboard", "history": [{"role": "user", "text": "hi"}]}
    assert client.post("/api/assistant", json=body).status_code == 401
    r = client.post("/api/assistant", json=body, headers=AUTH)
    assert r.status_code == 200 and r.json()["suggestions"]


def test_provider_picks_grok_from_an_xai_key(monkeypatch):
    for k in ("GROQ_API_KEY", "XAI_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "TRUEID_LLM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(llm, "_secret_file", lambda name: "")
    assert llm.provider() is None
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    assert llm.provider() == "grok"
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    assert llm.provider() == "groq"
    monkeypatch.setenv("TRUEID_LLM", "grok")
    assert llm.provider() == "grok"


def test_a_general_question_on_a_case_page_is_not_about_that_case(data):
    ring = next(r for r in data if r.fraud_type == "ring")
    out = A.ask("How is fraud trending this week?", f"/dashboard/case/{ring.app_id}", ring.app_id)
    assert "cases" not in out["used"] and "overview" in out["used"]
