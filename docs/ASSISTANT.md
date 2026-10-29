# Ask TrueID and the Investigator

An analytics assistant for the people using the analyst console. It answers questions about the live data in plain English: how fraud is trending, why a case was flagged, what a number or term means, what the learning loop proposes, and how applications are linked.

- **Floating panel:** the **Ask TrueID** button at the bottom right of every analyst page (or **Ctrl + /**). It knows which page you are on, and on a case page, which case.
- **Investigator page** (`/dashboard/chat`): the same conversation, full width, for digging deeper. The panel's expand button opens it. The conversation is kept for the browser tab.

Code: `backend/app/llm/assistant.py` (facts and answers), `backend/app/llm/client.py` (LLM providers), `frontend/components/Assistant.tsx` (panel, shared conversation), `frontend/app/dashboard/chat/page.tsx`. Tests: `backend/tests/test_assistant.py`.

## How an answer is made

1. **Facts first, always.** The question and the page decide which lookups run:

   | Lookup | Runs when |
   |---|---|
   | Live totals, this week's patterns and top signals | Trend or summary questions, or nothing more specific matched |
   | The case record and its graph links | An application ID is mentioned, or on a case page when the question is about "this case" / "why" |
   | Fraud pattern counts and typical signals | The question names a pattern (ring, mule, bot, tampered, replay…) |
   | Evaluation numbers | Accuracy, recall, false alarms, ROC-AUC, or on the Evaluation page |
   | Learning loop state | Drift, proposals, cut-offs, retraining, or on the Learning page |
   | Glossary and feature docs | A known term (PSI, SHAP, liveness, consortium…) or a feature name like `bio_sim_registry` |
   | What the current page shows | "What is this page?" style questions |

2. **Wording.** Without an AI key, the answer is written from templates using those facts, so it always works offline. With a key, the LLM rewrites the facts in natural language, using the last six messages for follow-ups.
3. **Guardrail.** An LLM answer that mentions an application ID or a reason code that isn't in the facts is thrown away, and the template answer is used instead.
4. **Read-only.** The assistant never changes a decision, a band or a proposal.

Each answer shows which data it used (for example "case record · live totals"), links to the cases and pages it mentions, and three follow-up suggestions.

## Turning on AI wording (Groq or xAI Grok)

Pick one. Keys are machine-local and must never be committed (`backend/.secrets/` is git-ignored).

```bash
# xAI Grok
echo "xai-..." > backend/.secrets/xai_api_key          # or: export XAI_API_KEY=xai-...
# optional: export XAI_MODEL=grok-3-mini                 # any chat model your xAI account has

# or Groq (the project's original provider)
echo "gsk_..." > backend/.secrets/groq_api_key          # or: export GROQ_API_KEY=gsk_...
```

Restart the backend. `GET /api/config` then shows `"llm": "grok"` (or `"groq"`), and answers say "worded by Grok". When several keys exist, Groq is used first; set `TRUEID_LLM=grok` to force Grok.

## API

`POST /api/assistant` (analyst only)

```json
{ "question": "Why was this case flagged?", "path": "/dashboard/case/L1A2B3C4D", "context_id": "L1A2B3C4D",
  "history": [{ "role": "user", "text": "..." }, { "role": "assistant", "text": "..." }] }
```

The response is `{ answer, source: "template" | "groq" | "grok" | "gemini", page, used: [...], suggestions: [...], links: [{label, href}] }`.

The older `POST /api/chat` (graph-only investigator) is kept for compatibility.
