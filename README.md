# TrueID Shield

**Hacksploit 2026 · PS3: Synthetic Identity Fraud Detection in Automated KYC.** Everything runs on one laptop, on localhost.

> A synthetic identity passes every single check on its own. So we don't trust any single check: we correlate
> documents, biometrics, behaviour, registries and a cross-application identity graph, and prove it by attacking our own system.

Full design rationale: [docs/PLAN.md](docs/PLAN.md).

## Run it

```bash
# 1. Python 3.13 (torch pinned in constraints.txt)
uv venv --python 3.13 .venv
VIRTUAL_ENV=.venv uv pip install -r backend/requirements.txt -c backend/constraints.txt

# 2. Data → features → model → metrics → attack lab → database   (≈15–25 min on an M3 CPU)
./scripts/build_all.sh            # or step by step, see the script

# 3. Servers
./scripts/run_backend.sh          # http://localhost:8000  (Swagger at /docs)
cd frontend && npm run dev        # http://localhost:3000
```

Optional: put a Groq key in `backend/.secrets/groq_api_key` (or `export GROQ_API_KEY=...`) for LLM-worded summaries and investigator answers. The LLM only rewords findings the system already produced; any answer naming a finding that isn't in the case is discarded for the deterministic template. Decisions never use it.

**Analyst sign-in.** The console and every case file, image and mock registry are analyst-only. On first start the
backend writes a random key to `backend/.secrets/analyst_key` (git-ignored): paste it into the sign-in screen once per
browser session. Scripts send it as an `X-Analyst-Key` header. Applicants never need it.

## Partner client sites (TrueID as a backend)
Two fictional partners run their own KYC forms and send the evidence to TrueID's partner API:
**Northstar Bank** (full KYC, no gaps, port 3001) and **PayLite Wallet** (minimum KYC with deliberate gaps, port 3002).
Each has an operations console showing TrueID's verdicts. See **[clients/README.md](clients/README.md)**.
Two KYC-only replicas follow real Indian flows: **Tideway** (Zerodha-style, port 3011, server-issued head-turn
liveness) and **Meridian Bank** (HDFC InstaAccount-style, port 3012, uploaded selfie). See
**[clients/KYC-REPLICAS.md](clients/KYC-REPLICAS.md)**. Partners call `/api/partner/v1/*` with an `X-Partner-Key`.
Setup and end-to-end testing: **[docs/PARTNER_INTEGRATION.md](docs/PARTNER_INTEGRATION.md)**; check the connection with `python scripts/check_partner_connection.py`.
Cross-institution fraud network (banks share keyed hashes, never customer data): `backend/app/consortium.py`, member client `scripts/consortium_client.py`. Mentor/judge summaries: **[docs/DELIVERABLES_PS3.md](docs/DELIVERABLES_PS3.md)**, **[docs/ONE_PAGER.md](docs/ONE_PAGER.md)**.
Governed self-learning (TrueID proposes band, model and coaching improvements from analyst outcomes; nothing changes without an analyst; applicants get tips for fixable issues only): **[docs/LEARNING_LOOP.md](docs/LEARNING_LOOP.md)**.
Research from IDRBT (the RBI's banking-technology institute) adapted to KYC: label-free genuine-profile rules, one-shot federated learning across banks, a chaotic-VAE generative attacker and per-case counterfactuals: **[docs/IDRBT_INNOVATION.md](docs/IDRBT_INNOVATION.md)**.

Optional, consented digital-footprint check (email and phone age, a linked Google/LinkedIn account) that only flags contradictions with the KYC details, never a missing footprint: **[docs/DIGITAL_FOOTPRINT.md](docs/DIGITAL_FOOTPRINT.md)**.
Real Aadhaar, verified offline through UIDAI's signed Secure QR (signature, printed text, UIDAI's photo vs the selfie, linked mobile): **[docs/REAL_AADHAAR.md](docs/REAL_AADHAAR.md)**. Fully AI-generated IDs and selfies (issuer signatures, C2PA content credentials, SynthID status): **[docs/AI_GENERATED_IDS.md](docs/AI_GENERATED_IDS.md)**. A signed demo card for a named person from their photo: `scripts/make_person_card.py`.
Analytics assistant (floating **Ask TrueID** panel + Investigator page; optional Groq / xAI Grok wording, grounded in live data): **[docs/ASSISTANT.md](docs/ASSISTANT.md)**. Latest state and hand-off: **[docs/HANDOFF_2026-10-29.md](docs/HANDOFF_2026-10-29.md)**.

## Testing
See **[docs/TESTING.md](docs/TESTING.md)**.
- Unit and access-control tests (no servers needed): `cd backend && ../.venv/bin/python -m pytest tests -q`
- End-to-end on fresh identities (backend running): `.venv/bin/python scripts/run_tests.py`

## How a decision is made
1. Each module turns its evidence into features and, for every **required check**, a status: PASS, FAIL,
   UNAVAILABLE (could not check), NOT_PROVIDED (never shown to us) or SIMULATED.
2. The calibrated XGBoost model gives a fraud probability. If it is missing or was trained under a different policy
   or feature schema, the probability is reported as unavailable, never replaced by a made-up average.
3. `backend/app/policy.py` picks the band. **APPROVE only when every required check passed and the model is low.**
   Hard REJECT only for an invalid issuer signature or a confidently read contradiction between the signed QR and the
   printed card. Poor photos turn a model REJECT into REVIEW. The policy never edits the probability.
4. The same policy function is used live, for seeding, in the Attack Lab and in evaluation.

Required checks: issuer signature, QR vs print, form vs card, ID checksum, selfie vs card, selfie vs registry,
**server-verified liveness**, registry identity, PAN linked to this person, capture quality, camera hint, media
integrity (photo not seen before, no AI-generator marker), device network (no mule herding). Voice step-up is
simulated and shown only.

**Liveness protocol.** The server issues a challenge (turn left / turn right in random order) bound to the applicant's
session, valid once for 3 minutes. The browser captures a short **video burst** through the challenge and the server
checks it is one live person: one face per frame all matching the selfie, and a **continuous head-turn** performing the
requested sequence. A few still photos jump straight to the turned pose with nothing in between, so they fail with
`BIO_NO_MOTION`; an uploaded selfie is NOT_PROVIDED. Both go to a person, never auto-approve. This defeats still-photo
spoofing but not a full video replay of the victim: production needs certified presentation-attack detection
(ISO/IEC 30107-3) or a native app with device attestation. See [docs/VCIP_ALIGNMENT.md](docs/VCIP_ALIGNMENT.md).

**RBI V-CIP extras.** With consent the browser records a GPS geo-tag and the session's network IP; both are shown on
the case page and kept as informational evidence (recorded, never scored: a self-reported fix can't be trusted, and on
localhost there is no public IP to geolocate).

Real-world fraud methods from 2024 to 2026 and how each is handled: **[docs/THREATS_2024_2026.md](docs/THREATS_2024_2026.md)**.

## Deliverables map

| # | Deliverable | Where |
|---|---|---|
| D1 | Multi-source correlation | `backend/app/modules/registry`, `modules/correlation` (specificity-weighted graph, Louvain, family exception), 3-way QR↔OCR↔form in `modules/document/agent.py` |
| D2 | AI-generated document forgery | Ed25519 signed QR (`qr_sign.py`; optional AES-256-GCM encrypted variant `TID3` so a scan reveals nothing), Verhoeff/PAN checks, date gate, OCR, cheap forensics (`forensics.py`); TruFor evidence on demand (`trufor.py`) |
| D3 | Behaviour across applications | `modules/behavior` + `correlation/history.py` (velocity windows, sequential emails, keystroke-rhythm links, IsolationForest) |
| D4 | Biometrics | `modules/biometric` (InsightFace ArcFace, threshold at FAR 0.1%, face reuse, server-issued and server-verified head-turn challenge in `liveness_sessions.py`, virtual-camera hint, media reuse), `frontend/lib/liveness.ts` (MediaPipe guidance only) |
| D5 | Adversarial robustness | `eval/run_attacks.py`, `eval/adaptive_attacker.py`, live attack endpoint `/api/attack/live`, Attack Lab page |
| D6 | End-to-end KYC simulation | `/kyc` applicant flow (session cookie, consent version, idempotent submit) → bounded job queue → LangGraph pipeline (`app/graph/pipeline.py`) with progress by polling → analyst console; Fraud Ring Simulator |
| D7 | Metrics | `eval/train.py` → P/R/F1/FPR/ROC-AUC/PR-AUC/confusion/per-type recall/FDR@top-k/latency + ablation; Metrics page |
| Extra | Investigator chat (Tier 2) | `app/llm/investigator.py` + `/dashboard/chat`: tools `get_case`, `get_neighbors`, `explain_feature` run deterministically; the LLM only phrases answers from their results |

## Real vs simulated

| Component | Status |
|---|---|
| Signed QR, checksums, OCR, date gate, forensics | **Real** |
| Face match, face reuse, server-verified liveness challenge | **Real** (InsightFace on CPU; MediaPipe in the browser only guides the user) |
| Virtual-camera check | **Real but client-reported**: the browser's camera label, which an attacker can rename |
| Liveness in the seeded population | **Synthetic fixture** labelled by the generator, never shown as live camera evidence |
| Telemetry, velocity, keystroke rhythm, identity graph | **Real** |
| Registries (UIDAI-like, PAN, telecom, CKYC, bureau) | **Mock services** with generated data, behind real HTTP routes (`/mock/*`) |
| Applicant population, ID cards | **Synthetic** (LFW faces + Faker `en_IN`; fantasy "Union Identity Card", watermarked SPECIMEN, no real emblems) |
| Voice / fingerprint step-up | **Simulated**, badged in the UI, never used by the model or the policy |
| TruFor | **Real** (official CVPR 2023 weights, Apple GPU, ~0.6 s/card), on-demand evidence only; set up with `./scripts/setup_trufor.sh` |
| LLM summary | Real if `GEMINI_API_KEY` is set; output must cite only allowed reason codes, else template |

## Honest-evaluation controls
- Time-based split: train days 0–15, isotonic calibration 16–19, test 20–29.
- Every card in every class gets random resize, noise and JPEG quality 60–95 (the DeepID JPEG-shortcut leak).
- Hard negatives: families sharing phone/address, hostel students on one IP with new SIMs, transliterated names, new-to-credit adults, repeat applicants.
- All cross-application features are computed **as of** each application's timestamp (no future data).
- Leakage check on top features is written into `precomputed/metrics.json`.

## Results (seeded build: 1,400 applications, test = days 20-29, 444 apps, 85 fraud)
Synthetic population (generated identities, LFW faces). Liveness outcomes in these rows are generator-labelled
fixtures, not live camera sessions. ROC/PR-AUC are on the calibrated model probability; recall and false-flag rates
are on the bands the evidence policy actually assigns.

| Setting | ROC-AUC | Recall | Genuine flagged |
|---|---|---|---|
| Document only | 0.78 | 0.52 | 0.6% |
| Biometric only | 0.98 | 0.91 | 1.1% |
| Behaviour only | 0.85 | 0.65 | 10.9% |
| Registry only | 0.91 | 0.78 | 0.6% |
| Correlation only | 0.68 | 0.34 | 1.7% |
| **Fused model** | **0.998** | **1.00** | **0.6%** |
| **Fused + evidence policy (what the system does)** | 0.998 | **1.00** | 9.5% held, nearly all sent to REVIEW |

- 95% bootstrap intervals: ROC-AUC 0.993-1.000, recall 1.00-1.00, genuine flagged 6.8%-12.6%.
- Bands on the test split: 325 APPROVE, 31 REVIEW, 88 REJECT. Of the 88 rejections, 84 were fraud (precision 95%):
  4 of 359 genuine applicants were rejected.
- Why genuine applicants are held (34): a failed liveness fixture, a borderline face match, or unreadable card text.
  Each is a "check again" case, which the policy sends to a person instead of approving blind.
- PR-AUC 0.982. Fraud-pattern labels match the true type for 86% of caught fraud (74% counting "injection" as wrong
  for bots and fabricators). The cost curve on the calibration split confirms the 0.30 approve cut-off.

**Under attack (Attack Lab, test-split sample of 185 apps, 85 fraud):** across JPEG, noise, blur, brightness and
screen-recapture sweeps at every strength, **no fraud is approved** and fraud recall stays at 100%; at most 4% of
genuine applicants are rejected. At the strongest blur, noise and recapture levels every genuine applicant is held for
a retake (photo quality check), which is the intended behaviour: too poor to judge is never a fraud verdict. Ring,
humanised-bot, virtual-camera, replay and face-splice scenarios: 100% flagged. The adaptive attacker, who controls
every behaviour and graph feature, turns no caught fraud into an approval (85/85 still flagged).

**Thresholds (all measured, none guessed):**
- Face 1:1 match at FAR 0.1% (0.203): genuine miss rate 2.6%. The equal-error point (0.12) let ~2% of impostors through and was retired.
- Face 1:N reuse search at ~0.03 expected false hits per search (0.322).
- APPROVE cut-off 0.30, checked with a cost curve on the calibration split (missed fraud = `TRUEID_FN_COST` x a false alarm, default 10).
- A QR vs printed-text mismatch is rejected as an edit only when it is read with OCR confidence >= 0.6 **and** the printed value could be real (the ID passes its checksum, the date parses). Otherwise it is treated as unreadable and sent to review. This stopped a genuine card being rejected for one misread ID digit.

**TruFor (measured on our cards):** on 40 test cards, clean vs Poisson-edited DOB, TruFor's score is at chance (AUC 0.49) and it flags 97.5% of clean cards too; its heatmap lights the legitimately pasted photo (mean 0.73) and misses the edited DOB (0.13). The signed QR catches 95% of the same edits outright; the rest are read too unclearly to call and go to review, never to approval. TruFor is available as evidence on the case page and in the Attack Lab (`./scripts/setup_trufor.sh`); it never feeds the decision.

**Fixed weaknesses:** tilted card photos are read with a QR-anchored perspective correction when it helps (best of both readings: mild tilt 10/10, moderate 7/10 vs 0/10 before); recapture no longer rejects genuine people for misread dates.
**Remaining weaknesses:** very strong recapture, blur or noise sends most genuine applicants to review (retake), so throughput drops on bad photos; see the Attack Lab.

## Operations (environment variables, all optional)
| Variable | Default | Effect |
|---|---|---|
| `TRUEID_MODE` | `local_demo` | `restricted` refuses to start without the secrets below and turns demo tools off |
| `TRUEID_ANALYST_KEY` | generated | Analyst key (else random, kept in `backend/.secrets/`) |
| `TRUEID_SESSION_SECRET` | generated | Signs session cookies |
| `TRUEID_ENABLE_DEMO_TOOLS` | true (false in restricted) | Ring simulator, test kit, presenter kit, live attack (analyst-only either way) |
| `TRUEID_TRUST_PROXY` / `TRUEID_TRUSTED_PROXY_IPS` | false / loopback | Believe `X-Forwarded-For` only from these proxies |
| `TRUEID_MAX_ACTIVE_JOBS` | 4 | Concurrent checks before `/api/apply` answers 503 |
| `TRUEID_APPLY_RATE` | 30 | Applications per client per minute (HTTP 429 beyond) |
| `TRUEID_RETENTION_DAYS` | 30 | Uploaded card/selfie images older than this are deleted at startup |
| `TRUEID_HMAC_KEY` | generated | Key for hashing ID numbers in the graph |
| `TRUEID_FN_COST` | 10 | Cost of a missed fraud relative to a false alarm, for the cost curve |
| `GROQ_API_KEY` (or `backend/.secrets/groq_api_key`) | unset | LLM wording for case summaries and investigator answers via Groq (`GROQ_MODEL`, default `openai/gpt-oss-120b`); templates otherwise |
| `GEMINI_API_KEY` | unset | Used only if no Groq key is set |

Right to erasure: `DELETE /api/apps/{id}` (or **Erase applicant data** on the case page) removes the record, its images and its graph entry, and leaves an audit stub. Applicants see plain next-step messages, never the internal reason codes.

Audit log: every entry is hash-chained to the previous one; `GET /api/audit/verify` reports the first edited or
deleted entry. Analyst decisions are stored next to the automated band (which is never changed). Going against the
system needs a written reason; approving an automated REJECT needs a second analyst session.

## Demo order
Use `/kyc?demo=1` and upload a presenter photo. Then run **genuine → hero DOB edit → Frankenstein**. Frankenstein comes last because it reuses the presenter's face under a stolen name, so the face-reuse signal fires there.

## State that survives restarts
The identity graph is in memory. Live applicants are appended to `backend/live_history.jsonl` once their case is saved and replayed on startup (a torn last line or a duplicate is skipped), and presenter-kit enrolments are written to `registry.json`. Re-running `eval/seed_db.py` resets both. Liveness challenges and in-flight jobs live in memory and are lost on restart (run one worker).

## Environment notes
macOS / Apple silicon, Python 3.13. `app/__init__.py` sets `OMP_NUM_THREADS=1`, because torch (EasyOCR) and XGBoost each ship libomp and segfault together in one process.

## Limitations
- Synthetic data: absolute numbers are optimistic; the claim is the **relative** gain shown by the ablation.
- Strongly tilted or recaptured photos can still defeat QR reading (perspective correction helps up to moderate tilt).
- In-memory graph and NumPy face search are for hackathon scale; production path is FAISS + a graph store + a queue.
- A real-time face swap that follows the head-turn instructions can pass web liveness; production needs certified
  presentation-attack and injection-attack detection or a native app with device attestation.
- Camera labels and device IDs are browser-reported and can be spoofed; analysts are sessions, not named accounts.
