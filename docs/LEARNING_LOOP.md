# Learning loop

TrueID improves from its own outcomes, but it never changes its own decisions on its own. Code: `backend/app/learning.py`. Screen: **Analyst console → Learning loop** (`/dashboard/learning`). Tests: `backend/tests/test_learning.py`.

## The four stages

| Stage | What happens | Where it shows |
|---|---|---|
| **Collect** | Labels come from analyst decisions only (plus generator truth on seeded rows). The system's own band is never a label, because training on its own verdicts would only teach it to agree with itself. | Feedback tab |
| **Monitor** | Score and feature drift (PSI: recent 7 days vs everything before), evidence-check health (a check that stops running, or a sudden surge in failures), and how analysts decided each automated band. | Drift & health tab |
| **Propose** | Band recalibration from labelled outcomes; a retrained challenger model; advisories on noisy or under-used signals; check-health alerts; coaching gaps. | Proposals tab |
| **Govern** | Nothing is applied until an analyst approves it. Every apply and rollback goes into the hash-chained audit log, and the previous state is kept so one click restores it. | Proposals and History tabs |

A cycle runs when an analyst clicks **Run a learning cycle**, and by itself after every 10 analyst decisions. A newer proposal replaces the open one with the same key.

## What can change, and what cannot

- **Decision bands** can be applied. A band proposal needs at least 30 labelled cases with a score, at least 5 fraud and 5 genuine, and no analyst writing more than 60% of the feedback. The approve cut-off minimises cost (a missed fraud costs 10 false alarms). The reject cut-off is the lowest score where labelled cases are at least 95% fraud, so genuine people are not auto-rejected. An applied band change survives a restart.
- **Challenger model** can be applied once the base model and `precomputed/features.csv` exist and there are 50 analyst labels. It is trained on the base training split plus analyst outcomes (weighted 3×). It is promoted only if it is no worse on the original test split (within 0.005 ROC-AUC) and better on held-out analyst decisions (by at least 0.01). The live model is archived first, so rollback restores it.
- **Advisories, health alerts and coaching gaps** can only be acknowledged. They never change the live system.
- **Required evidence rules are outside the loop.** Changing them is a policy change (new `POLICY_VERSION`) and needs sign-off.

## Poisoning guards

1. Only analyst decisions are labels, never the system's own band.
2. Minimum label counts, with both classes present.
3. A cap on how much of the feedback one analyst wrote (a single compromised account cannot steer the model).
4. The existing four-eyes rule: approving what the system rejected needs a second analyst.
5. Every change needs a human approval and is reversible.

## Applicant tips

The applicant's result (`GET /api/apply/{id}/result`, field `coaching`) and the analyst preview (`GET /api/learning/tips/{id}`) list only issues the applicant can fix: photo quality, an unreadable QR, form typos, the head-turn check, the selfie match, the camera and location access. Tips are ordered by what blocks approval first. Each one says how often people held for it were approved in the end, which is computed live from past cases.

Fraud signals are never explained: linked applications, device sharing, other banks, signature failures and registry mismatches. Those cases only say that a specialist will review some details, so the tips cannot be used to tune an attack. Rejected applicants get no tips; their next step is the assisted channel.

## API (analyst only)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/learning/overview` | All four stages in one call |
| GET | `/api/learning/drift` | Score and feature PSI, check health, band and pattern mix |
| GET | `/api/learning/feedback` | Labels by source, system vs analyst, analyst concentration |
| GET | `/api/learning/proposals?status=` | Proposals, newest first |
| POST | `/api/learning/cycle` | Run a cycle now |
| POST | `/api/learning/proposals/{id}` | `{"action": "apply" \| "dismiss" \| "acknowledge" \| "rollback"}` |
| GET | `/api/learning/cycles` | Cycle history |
| GET | `/api/learning/coaching` | Friction points and the tip catalogue |
| GET | `/api/learning/tips/{app_id}` | What this applicant sees |
