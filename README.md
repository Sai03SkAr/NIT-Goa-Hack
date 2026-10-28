# TrueID Shield

**Hacksploit 2026 · PS3 — Synthetic Identity Fraud Detection in Automated KYC.** Everything runs on one laptop, on localhost.

> A synthetic identity passes every single check on its own. So we don't trust any single check: we correlate
> documents, biometrics, behaviour, registries and a cross-application identity graph — and prove it by attacking our own system.

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

## Partner client sites (TrueID as a backend)
Two fictional partners run their own KYC forms and send the evidence to TrueID's partner API:
**Northstar Bank** (full KYC, no gaps, port 3001) and **PayLite Wallet** (minimum KYC with deliberate gaps, port 3002).
Each has an operations console showing TrueID's verdicts. See **[clients/README.md](clients/README.md)**.

## Testing
See **[docs/TESTING.md](docs/TESTING.md)**. Quick check: `.venv/bin/python scripts/run_tests.py` → `14/14 passed`.

## Deliverables map

| # | Deliverable | Where |
|---|---|---|
| D1 | Multi-source correlation | `backend/app/modules/registry`, `modules/correlation` (specificity-weighted graph, Louvain, family exception), 3-way QR↔OCR↔form in `modules/document/agent.py` |
| D2 | AI-generated document forgery | Ed25519 signed QR (`qr_sign.py`), Verhoeff/PAN checks, date gate, OCR, cheap forensics (`forensics.py`); TruFor adapter (`trufor.py`, off on CPU) |
| D3 | Behaviour across applications | `modules/behavior` + `correlation/history.py` (velocity windows, sequential emails, keystroke-rhythm links, IsolationForest) |
| D4 | Biometrics | `modules/biometric` (InsightFace ArcFace, EER-calibrated threshold, face reuse, server-side liveness frame check, virtual cam), `frontend/lib/liveness.ts` (MediaPipe) |
| D5 | Adversarial robustness | `eval/run_attacks.py`, `eval/adaptive_attacker.py`, live attack endpoint `/api/attack/live`, Attack Lab page |
| D6 | End-to-end KYC simulation | `/kyc` applicant flow → LangGraph pipeline (`app/graph/pipeline.py`) streamed over SSE → analyst console; Fraud Ring Simulator |
| D7 | Metrics | `eval/train.py` → P/R/F1/FPR/ROC-AUC/PR-AUC/confusion/per-type recall/FDR@top-k/latency + ablation; Metrics page |
| — | Investigator chat (Tier 2) | `app/llm/investigator.py` + `/dashboard/chat`: tools `get_case`, `get_neighbors`, `explain_feature` run deterministically; the LLM only phrases answers from their results |

## Real vs simulated

| Component | Status |
|---|---|
| Signed QR, checksums, OCR, date gate, forensics | **Real** |
| Face match, face reuse, liveness frame re-check, virtual-camera check | **Real** (InsightFace on CPU, MediaPipe in browser) |
| Telemetry, velocity, keystroke rhythm, identity graph | **Real** |
| Registries (UIDAI-like, PAN, telecom, CKYC, bureau) | **Mock services** with generated data, behind real HTTP routes (`/mock/*`) |
| Applicant population, ID cards | **Synthetic** (LFW faces + Faker `en_IN`; fantasy "Union Identity Card", watermarked SPECIMEN, no real emblems) |
| Voice / fingerprint step-up | **Simulated**, badged in the UI, never used as a model feature |
| TruFor | Adapter present; not run in this CPU build (plan §4.1 fallback). Semantic + cryptographic checks carry D2 |
| LLM summary | Real if `GEMINI_API_KEY` is set; output must cite only allowed reason codes, else template |

## Honest-evaluation controls
- Time-based split: train days 0–15, isotonic calibration 16–19, test 20–29.
- Every card in every class gets random resize, noise and JPEG quality 60–95 (the DeepID JPEG-shortcut leak).
- Hard negatives: families sharing phone/address, hostel students on one IP with new SIMs, transliterated names, new-to-credit adults, repeat applicants.
- All cross-application features are computed **as of** each application's timestamp (no future data).
- Leakage check on top features is written into `precomputed/metrics.json`.

## Results (seeded build: 1,400 applications, test = days 20–29, 444 apps, 85 fraud)
| Setting | ROC-AUC | Recall | FPR |
|---|---|---|---|
| Document only | 0.77 | 0.60 | 4.7% |
| Biometric only | 0.98 | 0.88 | 0.8% |
| Behaviour only | 0.84 | 0.67 | 7.5% |
| Registry only | 0.91 | 0.75 | 0.3% |
| Correlation only | 0.68 | 0.34 | 2.0% |
| **Fused** | **0.996** | **1.00** | **0.8%** |
| Fused + hard rules | 0.996 | 1.00 | 4.7% (liveness fails go to REVIEW, not reject) |

Decision bands: the APPROVE cut-off (0.30) is checked with a cost curve (missed fraud = 10× a false alarm), chosen on the calibration split; the curve is flat at 0.30, so the plan's setting stands.

Face threshold is EER-calibrated (0.12, FAR = FRR ≈ 2%). The 1:N face-reuse threshold is calibrated separately at FAR 1e-4 (0.26); with the 1:1 threshold the graph collapsed.
Hero attack: the Poisson DOB edit is caught 100% by the signed QR ↔ OCR check, while pixel forensics flag 0% at their threshold.

**Known weaknesses (shown honestly in the Attack Lab):** heavy noise (σ = 30) raises fused FPR to 26%; strong screen recapture (perspective ≥ 1) breaks QR and OCR reading because cards are assumed template-aligned (fix: QR-anchored homography).

## Demo order
Use `/kyc?demo=1` and upload a presenter photo. Then run **genuine → hero DOB edit → Frankenstein**. Frankenstein comes last because it reuses the presenter's face under a stolen name, so the face-reuse signal fires there.

## State that survives restarts
The identity graph is in memory. Live applicants are appended to `backend/live_history.jsonl` and replayed on startup, and presenter-kit enrolments are written to `registry.json`. Re-running `eval/seed_db.py` resets both.

## Environment notes
macOS / Apple silicon, Python 3.13. `app/__init__.py` sets `OMP_NUM_THREADS=1`, because torch (EasyOCR) and XGBoost each ship libomp and segfault together in one process.

## Limitations
- Synthetic data: absolute numbers are optimistic; the claim is the **relative** gain shown by the ablation.
- Card normalisation assumes a flat, template-aligned image (no homography for phone photos yet).
- In-memory graph and NumPy face search are for hackathon scale; production path is FAISS + a graph store + a queue.
