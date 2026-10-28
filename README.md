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

Optional: `export GEMINI_API_KEY=...` before starting the backend for LLM summaries (a deterministic template is used otherwise).

## Testing
See **[docs/TESTING.md](docs/TESTING.md)**. Quick check: `.venv/bin/python scripts/run_tests.py` → `14/14 passed`.

## Deliverables map

| # | Deliverable | Where |
|---|---|---|
| D1 | Multi-source correlation | `backend/app/modules/registry`, `modules/correlation` (specificity-weighted graph, Louvain, family exception), 3-way QR↔OCR↔form in `modules/document/agent.py` |
| D2 | AI-generated document forgery | Ed25519 signed QR (`qr_sign.py`), Verhoeff/PAN checks, date gate, OCR, cheap forensics (`forensics.py`); TruFor evidence on demand (`trufor.py`) |
| D3 | Behaviour across applications | `modules/behavior` + `correlation/history.py` (velocity windows, sequential emails, keystroke-rhythm links, IsolationForest) |
| D4 | Biometrics | `modules/biometric` (InsightFace ArcFace, EER-calibrated threshold, face reuse, server-side liveness frame check, virtual cam), `frontend/lib/liveness.ts` (MediaPipe) |
| D5 | Adversarial robustness | `eval/run_attacks.py`, `eval/adaptive_attacker.py`, live attack endpoint `/api/attack/live`, Attack Lab page |
| D6 | End-to-end KYC simulation | `/kyc` applicant flow → LangGraph pipeline (`app/graph/pipeline.py`) streamed over SSE → analyst console; Fraud Ring Simulator |
| D7 | Metrics | `eval/train.py` → P/R/F1/FPR/ROC-AUC/PR-AUC/confusion/per-type recall/FDR@top-k/latency + ablation; Metrics page |
| Extra | Investigator chat (Tier 2) | `app/llm/investigator.py` + `/dashboard/chat`: tools `get_case`, `get_neighbors`, `explain_feature` run deterministically; the LLM only phrases answers from their results |

## Real vs simulated

| Component | Status |
|---|---|
| Signed QR, checksums, OCR, date gate, forensics | **Real** |
| Face match, face reuse, liveness frame re-check, virtual-camera check | **Real** (InsightFace on CPU, MediaPipe in browser) |
| Telemetry, velocity, keystroke rhythm, identity graph | **Real** |
| Registries (UIDAI-like, PAN, telecom, CKYC, bureau) | **Mock services** with generated data, behind real HTTP routes (`/mock/*`) |
| Applicant population, ID cards | **Synthetic** (LFW faces + Faker `en_IN`; fantasy "Union Identity Card", watermarked SPECIMEN, no real emblems) |
| Voice / fingerprint step-up | **Simulated**, badged in the UI, never used as a model feature |
| TruFor | **Real** (official CVPR 2023 weights, Apple GPU, ~0.6 s/card), on-demand evidence only; set up with `./scripts/setup_trufor.sh` |
| LLM summary | Real if `GEMINI_API_KEY` is set; output must cite only allowed reason codes, else template |

## Honest-evaluation controls
- Time-based split: train days 0–15, isotonic calibration 16–19, test 20–29.
- Every card in every class gets random resize, noise and JPEG quality 60–95 (the DeepID JPEG-shortcut leak).
- Hard negatives: families sharing phone/address, hostel students on one IP with new SIMs, transliterated names, new-to-credit adults, repeat applicants.
- All cross-application features are computed **as of** each application's timestamp (no future data).
- Leakage check on top features is written into `precomputed/metrics.json`.

## Results (seeded build: 1,400 applications, test = days 20-29, 444 apps, 85 fraud)
| Setting | ROC-AUC | Recall | FPR |
|---|---|---|---|
| Document only | 0.79 | 0.59 | 0.8% |
| Biometric only | 0.98 | 0.87 | 1.1% |
| Behaviour only | 0.84 | 0.67 | 7.5% |
| Registry only | 0.91 | 0.75 | 0.3% |
| Correlation only | 0.67 | 0.34 | 2.2% |
| **Fused** | **0.996** | **1.00** | **0.8%** |
| Fused + hard rules | 0.996 | 1.00 | 7.2% (mostly sent to review: failed liveness, face mismatch) |

Fraud-pattern labels are correct for 84.7% of caught fraud. Acceptance test: `scripts/run_tests.py` passes 14/14 on fresh identities.

**Thresholds (all measured, none guessed):**
- Face 1:1 match at FAR 0.1% (0.203): genuine miss rate 2.6%. The equal-error point (0.12) let ~2% of impostors through and was retired.
- Face 1:N reuse search at ~0.03 expected false hits per search (0.322).
- APPROVE cut-off 0.30, checked with a cost curve on the calibration split (missed fraud = `TRUEID_FN_COST` x a false alarm, default 10).
- A QR vs printed-text mismatch read with OCR confidence >= 0.6 is rejected as an edit; below that it is treated as unreadable and sent to review (edits read at p5 0.69, blurry genuine misreads at median 0.41).

**TruFor (measured on our cards):** on 40 test cards, clean vs Poisson-edited DOB, TruFor's score is at chance (AUC 0.49) and it flags 97.5% of clean cards too; its heatmap lights the legitimately pasted photo (mean 0.73) and misses the edited DOB (0.13). The signed QR catches 100% of the same edits. TruFor is available as evidence on the case page and in the Attack Lab (`./scripts/setup_trufor.sh`); it never feeds the decision.

**Fixed weaknesses:** tilted card photos are read with a QR-anchored perspective correction when it helps (best of both readings: mild tilt 10/10, moderate 7/10 vs 0/10 before); recapture no longer rejects genuine people for misread dates.
**Remaining weaknesses:** very strong recapture or noise can still make the QR unreadable; see the Attack Lab.

## Operations (environment variables, all optional)
| Variable | Default | Effect |
|---|---|---|
| `TRUEID_API_KEY` | unset | When set, analyst endpoints and images need `X-API-Key` (frontend: `NEXT_PUBLIC_API_KEY`) |
| `TRUEID_APPLY_RATE` | 30 | Applications per client per minute (HTTP 429 beyond) |
| `TRUEID_RETENTION_DAYS` | 30 | Uploaded card/selfie images older than this are deleted at startup |
| `TRUEID_HMAC_KEY` | demo key | Key for hashing ID numbers |
| `TRUEID_FN_COST` | 10 | Cost of a missed fraud relative to a false alarm, for the cost curve |
| `GEMINI_API_KEY` | unset | LLM-written summaries (templates otherwise) |

Right to erasure: `DELETE /api/apps/{id}` (or **Erase applicant data** on the case page) removes the record, its images and its graph entry, and leaves an audit stub. Applicants see plain next-step messages, never the internal reason codes.

## Demo order
Use `/kyc?demo=1` and upload a presenter photo. Then run **genuine → hero DOB edit → Frankenstein**. Frankenstein comes last because it reuses the presenter's face under a stolen name, so the face-reuse signal fires there.

## State that survives restarts
The identity graph is in memory. Live applicants are appended to `backend/live_history.jsonl` and replayed on startup, and presenter-kit enrolments are written to `registry.json`. Re-running `eval/seed_db.py` resets both.

## Environment notes
macOS / Apple silicon, Python 3.13. `app/__init__.py` sets `OMP_NUM_THREADS=1`, because torch (EasyOCR) and XGBoost each ship libomp and segfault together in one process.

## Limitations
- Synthetic data: absolute numbers are optimistic; the claim is the **relative** gain shown by the ablation.
- Strongly tilted or recaptured photos can still defeat QR reading (perspective correction helps up to moderate tilt).
- In-memory graph and NumPy face search are for hackathon scale; production path is FAISS + a graph store + a queue.
