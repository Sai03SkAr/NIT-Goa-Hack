# TrueID Shield: guide for evaluators

**Hacksploit 2026 · PS3: Synthetic Identity Fraud Detection in Automated KYC.** This page is the starting point for evaluating the project. Everything it claims is linked to code, a test, or a document with the measurement.

## The problem, and our answer

A **synthetic identity** mixes real and invented data: a valid ID number, a real-looking card, a face that matches its own photo. **It passes every single check on its own.** AI-generated documents and deepfake selfies make it cheap to produce, and mule accounts make it profitable.

**TrueID trusts no single check.** It approves only when *every* required piece of evidence passes. It also correlates documents, face, behaviour, government registries, every past application and other banks' signals, so a fraudster has to stay consistent everywhere at once. A model ranks the risk; a fixed evidence policy decides; a language model only explains.

## Run it (about 5 minutes once installed)

```bash
# backend (Windows venv shown; Linux/mac use .venv/bin/python)
cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
# analyst console + applicant flow
cd frontend && npm install && npm run dev            # http://localhost:3000
# optional partner bank site that calls TrueID server to server
cd clients/kyc-homeloan && TRUEID_MODE=remote node server.js    # http://localhost:3013
```

- **Full synthetic population, model and evaluation:** `scripts/build_all.sh`. This needs about 1 GB of downloads. Without it, the evidence checks run but the risk model shows *unavailable*.
- **Analyst key:** in `backend/.secrets/analyst_key`, created on first start.
- **Demo applicants with signed cards:** `scripts/make_person_card.py --all` (see `demo/people/`).

## A 10-minute evaluation path

| # | Do this | You should see |
|---|---|---|
| 1 | Open `/kyc` and apply as a demo person: card from `data/generated/people/<slug>/card.jpg`, the values from `details.json`, a live selfie and the head-turn check | The pipeline runs live. The result page gives a plain-language outcome; tips appear only for fixable issues |
| 2 | Open the case in the console (`/dashboard`) | Verdict stamp and risk ring, six check cards, **Do the sources agree?** grid, required evidence as "X of 13 passed", what drove the score |
| 3 | On `/kyc`, build the **test kit** from a photo (it makes a genuine card, a DOB-edited one and a "Frankenstein"), then apply with the **edited** card | *Signed QR agrees with the printed card* **fails**: the QR still holds the true date. Rejected |
| 4 | Apply with the kit's **Frankenstein** card: someone else's real ID number with your face | Face doesn't match the issuer's photo; registry and PAN don't match. Rejected or held |
| 5 | Identity graph → **Fraud Ring Simulator** | Eight linked applicants appear as one ring (shared face, device, typing rhythm) |
| 6 | Attack Lab → **Run attack** (e.g. Poisson DOB edit) | The forgery detector misses it; the signed-QR check catches it |
| 7 | Evaluation page | Fraud caught, false alarms, results per pattern, what each check adds, unseen-fraud results |
| 8 | Learning loop → **Run a learning cycle** | Proposals (cut-offs, drift, coaching) that change nothing until an analyst applies them; one-click rollback |
| 9 | **Ask TrueID** (bottom right) | "Why was this case flagged?" or "How is fraud trending?", answered from the live data |
| 10 | A partner site (Kestrel, :3013) | A bank's own KYC journey calling TrueID's partner API, with per-step checks |

## PS3 requirements and where each is met

| PS3 asks for | What we built | Evidence |
|---|---|---|
| Multi-source data correlation | Document, face, behaviour, registries, identity graph and a cross-bank network, fused; the evidence policy requires all of them | `docs/DELIVERABLES_PS3.md` §1; ROC-AUC 0.998 fused vs 0.78 document-only |
| AI-generated document forgery detection | The issuer's **signed QR** is the source of truth, so an edit contradicts its own QR. Pixel forensics and TruFor are shown as evidence. **C2PA / IPTC AI-provenance** is read on every upload | §2; `docs/AI_GENERATED_IDS.md`; edited DOB caught ~95% vs TruFor at chance (0.49) |
| Behavioural pattern analysis across applications | Typing rhythm, paste and fill-time, velocity; the keystroke rhythm links identities typed by one person; Louvain rings | §3; behaviour-only ROC-AUC 0.85; scripted bots caught 100% |
| Biometric verification (simulation allowed) | ArcFace selfie vs card vs **issuer photo** (strict 0.1% false-accept threshold), server-issued head-turn liveness on a video burst, 1:N face-reuse search; voice is simulated and never decides | §4; biometric-only ROC-AUC 0.98 |
| Adversarial robustness evaluation | Attack Lab: JPEG, noise, blur, recapture, Poisson DOB edit, virtual camera, an adaptive attacker and a chaotic-VAE generative attacker | §5; no fraud approved at any strength; adaptive attacker 0 of 85 |
| End-to-end KYC pipeline simulation | Applicant flow → LangGraph pipeline → evidence policy → analyst console with audit trail; three partner bank sites over a keyed API | §6; `docs/PARTNER_INTEGRATION.md` |
| Performance metrics | Time-split test, 95% bootstrap intervals, leakage check, cost-based cut-off | §7; table below |

## Results (time-split test: 444 applications, 85 fraud)

| Metric | Value |
|---|---|
| Fraud caught (recall) | **100%** (0 missed) |
| ROC-AUC / PR-AUC | **0.998** / 0.982 |
| Reject precision | **95%** (84 of 88 rejections were fraud) |
| False alarms | 9.5%, mostly sent to review, not rejected |
| Fraud type labelled correctly | 86% |
| Unseen fraud (retrained without each type) | The model alone catches 0% of bots and 40% of tampered cards. The label-free genuine profile catches 94% and 100%. The live system catches 100% |
| Fairness of the footprint check | Flags 1.4% of genuine applicants, vs 20.3% for a naive "social score" |

**Read these honestly.** The data is synthetic, so perfect recall is optimistic. The numbers come from a proper time split with confidence intervals and leakage checks, and the *relative* gains are what we claim (`docs/DELIVERABLES_PS3.md` §7).

## What is new here

1. **Evidence policy over a score.** Missing, unverifiable or merely simulated evidence never approves; the model only ranks risk.
2. **Signed and encrypted QR as the document's truth.** It beats pixel forensics on the edits that matter. **Real Aadhaar** is verified offline the same way, through UIDAI's signed Secure QR, including UIDAI's own photo against the selfie (`docs/REAL_AADHAAR.md`).
3. **Cross-bank network on keyed hashes.** The same ID under another name, or rejected elsewhere, is held for review, and no customer data leaves the bank (`backend/app/consortium.py`).
4. **Consented digital footprint ("social scoring") done fairly.** It is opt-in and counts only contradictions; a thin footprint never counts against anyone (`docs/DIGITAL_FOOTPRINT.md`).
5. **Zero-day defence from IDRBT research.** A one-class genuine profile, a one-shot federated profile, a chaotic-VAE attacker and per-case counterfactuals (`docs/IDRBT_INNOVATION.md`).
6. **Governed self-learning.** Analyst decisions become proposals that a person approves and can roll back. There are poisoning guards, and applicant tips cover fixable issues only (`docs/LEARNING_LOOP.md`).
7. **AI-provenance.** C2PA content credentials are read and validated. Honest about SynthID: no self-serve detector exists (`docs/AI_GENERATED_IDS.md`).
8. **An analyst assistant grounded in data.** Facts come first; an AI wording that cites an ID or code not in the facts is discarded (`docs/ASSISTANT.md`).
9. **Built for regulated use.** RBI V-CIP geo-tag and consent, the DPDP right to erasure (including network signals), a hash-chained audit log, four-eyes approval of what the system rejected, and data retention limits (`docs/VCIP_ALIGNMENT.md`).

## Tests

```bash
cd backend && ../.venv/Scripts/python.exe -m pytest tests -q          # 118 passed
cd frontend && npx tsc --noEmit -p . && npx eslint app components lib && npm run build
python scripts/check_partner_connection.py                            # partner API end to end (12 checks)
```

The 118 backend tests cover:

- the evidence policy and every required check
- access control (deny by default, partner keys, origin checks)
- the partner API and the consortium network (including erasure)
- the learning loop and its poisoning guards
- the assistant's grounding guardrail
- the footprint fairness rules
- the IDRBT profile
- C2PA provenance
- Aadhaar Secure QR parsing and signature verification

The manual browser checklist is in `docs/TESTING.md`.

## Limits we state up front

- **Synthetic population.** Absolute accuracy will be lower on real traffic.
- **Mock registries.** UIDAI, PAN, telecom, CKYC and the credit bureau are mocks. Real Aadhaar is verified offline through its signed QR. PAN, telecom and bureau lookups need licensed APIs.
- **Liveness is not a certified PAD.** A production deployment adds an ISO/IEC 30107-3 certified presentation-attack-detection SDK.
- **SynthID is not checked automatically.** Only Google's portal or enterprise API can detect it.
- **The footprint provider is simulated** until a licensed vendor is contracted.

## Where to read more

| Topic | Document |
|---|---|
| One page | `docs/ONE_PAGER.md` |
| Each PS3 deliverable in depth, with mentor Q&A | `docs/DELIVERABLES_PS3.md` |
| Testing, step by step | `docs/TESTING.md` |
| Partner integration | `docs/PARTNER_INTEGRATION.md` |
| Real Aadhaar / AI-generated IDs | `docs/REAL_AADHAAR.md`, `docs/AI_GENERATED_IDS.md` |
| Footprint / learning loop / assistant | `docs/DIGITAL_FOOTPRINT.md`, `docs/LEARNING_LOOP.md`, `docs/ASSISTANT.md` |
| IDRBT research adapted | `docs/IDRBT_INNOVATION.md` |
| Regulation and threats | `docs/VCIP_ALIGNMENT.md`, `docs/THREATS_2024_2026.md` |
| Current state and hand-off | `docs/HANDOFF_2026-10-29.md` |
