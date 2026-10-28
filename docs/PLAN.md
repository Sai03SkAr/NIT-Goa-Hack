# TrueID Shield: Final Implementation Plan
**Hacksploit 2026, PS3: Synthetic Identity Fraud Detection in Automated KYC Systems**
Built for **one Windows PC**: no cloud, no Docker, everything runs on localhost.

Source tags used throughout this document:
- **[DeepID]**: ICCV 2025 DeepID Challenge, the world competition on detecting forged ID documents (26 teams, methods published)
- **[Deriv]**: Deriv AI Hackathon winning KYC pipeline
- **[SentiLink]**: the US industry leader in synthetic-identity detection
- **[CallPilot]**: open-source scam-call detector, the source of the "LLM only classifies or explains" engineering
- **[CyberShield]**: Bank of India × IIT-H hackathon 2026 judging criteria
- **[FraudLens]**: Central Bank of India hackathon 2025 winner
- **[ISB/Saakshya]**: 2026 agentic and multi-agent winners
- **[Your plan]**: ideas from your docx that were genuinely good and are kept
- **[Reasoning]**: constraints of one PC / Windows, or domain logic

---

## 0. The thesis (say this in the first 20 seconds)

> "A synthetic identity passes every single check on its own: valid ID number, real-looking card, a face that matches the photo. The best ID-forgery detectors in the world score at chance on a carefully edited date of birth. So we don't trust any single check. We **correlate** documents, biometrics, behavior, registries and a cross-application identity graph, and we prove it by attacking our own system."

**Why this framing:**
- [DeepID]: when one small text field (DOB, name) was edited with a fine-tuned generator and smoothly blended, **every team, including the winners, performed at chance**. That's hard evidence that pixel forensics alone fails, and it's exactly why PS3 asks for multi-source correlation (Deliverable 1).
- [SentiLink]: production synthetic-ID detection compares each application against the history of all prior applications and outside data. It doesn't judge a document on its own.

---

## 1. What we build: features mapped to the 7 mandatory deliverables

| # | Deliverable | Our implementation | Tier |
|---|---|---|---|
| D1 | Multi-source correlation | Weighted identity graph + mock registries (UIDAI-like, PAN, telecom, CKYC, credit bureau) + 3-way field consistency (QR ↔ OCR ↔ form) | Must |
| D2 | AI-generated document forgery | **Signed-QR verification** + checksums + date gate + OCR cross-check + TruFor heatmap + cheap forensics (edge, font, noise, ELA visual) | Must |
| D3 | Behavioral analysis across applications | Session telemetry + bot signals + velocity windows + sequential-email pattern + **typing-rhythm links between different identities** | Must |
| D4 | Biometrics (simulated allowed) | InsightFace match (selfie ↔ card ↔ registry) + **face reuse across identities** + active liveness (MediaPipe) + virtual-camera detection; voice and fingerprint simulated and clearly labeled | Must |
| D5 | Adversarial robustness | Attack Lab: 12 attacks, strength sweeps, **single module vs fused**, plus an **adaptive attacker** that changes only what a fraudster controls | Must |
| D6 | End-to-end KYC simulation | Applicant flow → LangGraph pipeline with live progress → decision; analyst console; fraud-ring simulator | Must |
| D7 | Metrics | P / R / F1 / FPR / ROC-AUC / PR-AUC / confusion matrix / per-fraud-type recall / FDR@top-k / latency + **ablation chart** | Must |

---

## 2. Tech stack: final choices and why

| Layer | Choice | Instead of | Why | Source |
|---|---|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | — | Your core stack; fastest path to a polished UI. UX is a scored criterion | [CyberShield] criteria include UX |
| Charts | Recharts | — | Simple, enough for ROC, PR, bars and curves | [Your plan] |
| Graph viz | react-force-graph-2d | Cytoscape.js | Animates nicely for the ring-simulator moment; fewer lines of code | [Your plan] |
| Liveness (client) | MediaPipe Tasks Vision FaceLandmarker **in the browser** | Server-side MediaPipe | Real-time feedback and **no load on your one PC's CPU**. The server re-checks the captured frames, so the client can't just send "passed=true" | [Reasoning] one PC |
| Backend | FastAPI + Pydantic, Python 3.11 venv | — | Your core stack; free Swagger docs at `/docs` | [Your plan] |
| Orchestration | **LangGraph StateGraph** (parallel nodes + conditional step-up branch), no LLM in the decision | Plain `asyncio.gather` | Same parallelism, but you also get a **visual agent graph**, conditional step-up routing and streamed node events for the live progress UI. Agentic/multi-agent designs won in 2026; the decision stays deterministic | [ISB/Saakshya], [CallPilot] |
| Document forgery model | **TruFor** (pretrained, gives score + heatmap) | ELA as the main signal | Almost every top DeepID team built on TruFor, and only 6 of 26 teams beat it. ELA is weak, and a judge who knows forensics will notice. ELA stays as a visual only | [DeepID] |
| Cheap forensic add-ons | Edge density + HOG font-consistency + date sanity gate, fixed-weight fusion | Training a new CNN | Indian team Reagvis placed with exactly this (0.6 TruFor + 0.2 edge + 0.2 font) and no training. Feasible in a hackathon on CPU | [DeepID] Reagvis/Hardik |
| OCR | **EasyOCR** | Tesseract, PaddleOCR | Tesseract struggles with ID-card layouts and phone photos. EasyOCR runs on **PyTorch, which TruFor already needs**, so one fewer framework to install on Windows | [Reasoning] |
| Face | **InsightFace** (buffalo_l, ArcFace, ONNX) | face_recognition (dlib), DeepFace | Stronger embeddings and fast on CPU. dlib is dated; DeepFace pulls in TensorFlow (a second heavy framework) | [Reasoning] |
| Face dedupe search | NumPy cosine matrix | FAISS | 3–5k × 512 vectors is milliseconds in NumPy. FAISS is for millions (mention it on the "scale" slide) | [Reasoning] |
| QR | `qrcode` (generate) + `cv2.QRCodeDetector` (read) + `cryptography` Ed25519 | pyzbar | OpenCV is already installed, so no extra DLL hassle on Windows | [Reasoning] |
| Fuzzy matching | `rapidfuzz` (Jaro-Winkler + token-sort) + Indian name normalization | Exact match | Attackers tweak spellings to dodge exact links | [Your plan] attribute perturbation |
| Graph | NetworkX in memory + Louvain communities | Neo4j | Zero setup and enough at hackathon scale | [Your plan] |
| Fusion | XGBoost + isotonic calibration + SHAP | LightGBM, raw scores | SHAP TreeExplainer works natively. Calibration makes the 0.3/0.7 thresholds mean real probabilities | [Your plan] + [Reasoning] |
| Anomaly | IsolationForest (behavior) | — | Unsupervised signal for new bot patterns | [Your plan] |
| DB | **SQLite** via SQLModel | Firestore | Velocity windows and cross-application joins are SQL queries; Firestore makes them painful. SQLite needs zero setup on one PC | [Reasoning] |
| LLM | Gemini API free tier (any provider works), with a **template fallback** | LLM in the decision path | Only explains and answers analyst questions. The demo still works if the API fails | [CallPilot], [Deriv] |
| Run / demo | localhost (camera works on localhost without HTTPS) | Docker + Render + CI/CD | Render's free tier can't hold TruFor + InsightFace + OCR in memory; Docker on Windows costs hours; CI earns zero points. If a judge needs a link: `cloudflared` tunnel | [Reasoning] |

**Dropped from your plan, and why:**
- **Docker, Render, GitHub Actions:** no judging value; they cost hours on one Windows PC.
- **Firestore:** see above.
- **Tesseract, face_recognition:** see above.
- **Neo4j:** NetworkX is enough.
- **Drift tab:** low judge value; mention it as roadmap.
- **FingerprintJS:** replaced by a 20-line device hash (UA + screen + timezone + canvas hash), because the synthetic population needs device IDs anyway and it removes a dependency/licensing question.

---

## 3. Architecture

```
APPLICANT (Next.js)                                   ANALYST CONSOLE (Next.js)
consent → details (+telemetry) → ID upload             queue · case view · graph · metrics
→ selfie + active liveness (MediaPipe, browser)        attack lab · ring simulator · investigator chat
→ [step-up voice, simulated] → live progress (SSE)          ▲
            │                                               │
            ▼                                               │
FastAPI ── LangGraph StateGraph ────────────────────────────┘
   ingest
     ├─► document_agent   (QR sig, checksums, date gate, OCR↔form↔QR, TruFor, cheap forensics)
     ├─► biometric_agent  (face match card/selfie/registry, liveness frames, virtual cam, voice/fp sim)
     ├─► behavior_agent   (telemetry, bot score, velocity, email pattern, keystroke vector)
     └─► registry_agent   (mock UIDAI / PAN / telecom / CKYC / bureau)
            ▼ (join)
     correlation_agent    (weighted identity graph, face reuse, ring detection)
            ▼
     fusion               (hard rules → calibrated XGBoost → SHAP → fraud-type classifier)
            ▼
     router ── review band & no step-up yet ──► step_up (extra liveness / voice) ──► fusion
            ▼
     decide (APPROVE / REVIEW / REJECT + reason codes + recommended action)
            ▼
     explain (LLM summary from structured outputs only; template fallback) → persist (SQLite + audit log)
```

**Every module returns the same shape** (kept from [Your plan]; it makes fusion and the UI trivial):
```json
{ "module": "document", "risk": 0.82, "confidence": 0.9,
  "reasons": [{"code": "DOC_QR_SIG_INVALID", "text": "QR signature does not verify", "weight": 0.4}],
  "evidence": {"heatmap_url": "...", "ocr": {...}, "qr": {...}},
  "simulated": false, "latency_ms": 640 }
```
- **`reasons` use fixed codes** with a fixed text table. The LLM never invents a reason [CallPilot].
- **`simulated: true`** is shown as a badge in the UI for voice and fingerprint. Being honest about what's simulated earns trust with judges [Your plan].

---

## 4. Module specifications

### 4.1 Document agent (D2)

| Check | How | Why / source |
|---|---|---|
| **Signed QR verification** (hard fail) | Our mock "issuer" signs `{name, dob, gender, id_last4, issue_date}` with Ed25519; the QR printed on the card carries payload + signature; we verify with the public key | Real Aadhaar Secure QR is digitally signed by UIDAI. **Cryptographic verification beats pixel forensics**: a pixel-perfect AI forgery still can't forge a signature. Cheap to build, very strong pitch line. [Reasoning, Indian context] |
| **3-way consistency** | QR payload ↔ OCR of the printed text ↔ form input (fuzzy name match, exact DOB) | Catches the small DOB edit that beat every DeepID team, because the edited printed DOB ≠ the signed QR DOB [DeepID finding] |
| Checksums and format | Aadhaar-like number: Verhoeff checksum. PAN-like: `^[A-Z]{5}[0-9]{4}[A-Z]$`, 4th char = holder type (P), 5th char = surname initial | Free, deterministic and explainable [Your plan] |
| **Date sanity gate** | DOB < issue date, no future dates, age 18–100, issue date after the 18th birthday where applicable | Copied from DeepID team Reagvis's "chronological sanity gate" [DeepID] |
| TruFor | Detection score + localization heatmap overlaid on the card | Industry-standard baseline [DeepID]. **CPU is slow**, so precompute for seeded data and run live only on the demo card |
| Cheap forensics | 32×32 patch Canny edge density, HOG font-consistency across text fields, face-region vs background noise variance, ELA (visual only) | Reagvis + Hardik approach [DeepID] |
| EXIF | Editing-software tags = weak positive. **Missing EXIF = no signal** | Browsers and WhatsApp strip EXIF; flagging it would hurt genuine users [Reasoning] |
| Layout | OCR box positions vs the template's expected field positions | Pasted text drifts off the template grid [Your plan] |

**Fusion inside the module:** `doc_risk = max(hard_fail, 0.5·TruFor + 0.2·semantic_mismatch + 0.15·font + 0.15·edge)`. Tune the weights by grid search on the validation split (the Reagvis method).

**Fallback if TruFor won't run on your PC within 45 minutes:** drop it, keep everything else, and say in the pitch *"pixel detectors fail on fine edits (DeepID), so our main defense is semantic and cryptographic."* The thesis survives.

### 4.2 Biometric agent (D4)

| Check | How | Why / source |
|---|---|---|
| Selfie ↔ card portrait | InsightFace ArcFace cosine similarity; **calibrate the threshold on LFW genuine vs impostor pairs** (don't guess 0.4) | A measured threshold is defensible in Q&A [Reasoning] |
| Selfie ↔ registry face | Mock UIDAI stores a face embedding per ID number | Catches **first-party / Frankenstein** fraud: a real ID number used with someone else's face [SentiLink first-party category] |
| **Face reuse across identities** | Compare the new embedding with all prior applicants; same face + different name → strong graph edge | The single strongest synthetic-ring signal [Your plan] |
| Active liveness | Browser: 2 random challenges from {blink, turn left, turn right, smile} using FaceLandmarker blendshapes + head pose, time-limited. Server: the 3 captured frames must be the same identity with **different** head poses | A random challenge defeats replayed video. The server re-check defeats a client that fakes "passed" [Your plan + Reasoning] |
| **Virtual camera detection** | `navigator.mediaDevices.enumerateDevices()` labels containing OBS / ManyCam / "Virtual" → hard flag | DeepID focuses on **injection attacks**; a virtual camera is how a deepfake gets injected into the selfie step. About 5 lines of JS [DeepID] |
| Passive | Blur (Laplacian variance), moiré (FFT peaks) on the selfie | Cheap screen-replay hint [Your plan] |
| Voice / fingerprint | Mock services return scores from class-conditional distributions with configurable noise; UI badge "SIMULATED" | PS allows simulation; spend the time where judges score depth [Your plan] |

### 4.3 Behavior agent (D3)

- **Session telemetry (client):** time per field, inter-key interval mean/std, paste count per field, corrections, total fill time, focus/blur (tab switches), mouse-movement entropy.
- **Bot signals:** superhuman fill time, paste-heavy (e.g. 5/7 fields), near-zero timing variance.
- **Cross-application signals:**
  - **Velocity:** 1h/24h/7d windows per device, IP, phone, email domain and address, plus a **relative velocity** ratio (short window ÷ long window) [Your plan].
  - **Sequential email pattern:** strip digits and separators → same stem across identities (`rahul.k1`, `rahul.k2`).
  - **Typing rhythm as a link:** a 12-dim keystroke vector per application; cosine similarity > threshold between **different identities** adds a graph edge. One fraudster typing 8 identities has one rhythm. [Reasoning: keystroke-dynamics idea]
- **Model:** IsolationForest trained on genuine sessions + rule thresholds → `behavior_risk` with plain reasons ("pasted 5/7 fields", "filled in 11 s", "device seen on 6 applications today").

### 4.4 Registry agent (D1)

Five mock services (JSON tables built by the data generator), each behind a FastAPI router so the demo shows "external lookups":

| Mock | Returns | Synthetic-identity signal |
|---|---|---|
| UIDAI-like | name, DOB, gender, face embedding | Name or face mismatch with a valid number → first-party / stolen-ID blend |
| PAN-like | name, DOB, linked ID hash | PAN–ID link mismatch |
| Telecom | SIM activation date, subscriber name | **SIM < 30 days old** behind a "35-year-old" identity |
| CKYC-like | record exists, first-seen date | No KYC history anywhere |
| Credit bureau | number of accounts, oldest account age, recent inquiries | **Thin file at age 35** + burst of recent inquiries (bust-out pattern) |

**Why:** synthetic identities typically look clean in the documents but **have no history**. [SentiLink] trains on bureau, utility, phone and email data for exactly this reason.

### 4.5 Correlation agent (D1, the differentiator)

- **Nodes:** Application, ID-hash, PAN, Phone, Email, Device, IP, Address, FaceCluster, KeystrokeCluster.
- **Edge weight = base weight × specificity**, where `specificity = log(N / apps_sharing_value)`. Base weights: face 1.0, ID-hash 1.0, device 0.8, phone 0.7, email 0.6, keystroke 0.3, address 0.4, **IP 0.15**.
  - **Why:** Indian mobile carriers put many users behind one IP (CGNAT), and joint families share phones and addresses. Unweighted graphs flag genuine families as fraud rings. Rare shared values are suspicious; common ones aren't. [Reasoning, Indian context]
- **Placeholder cleaning** before linking (9999999999, test@test.com, "NA") [Your plan: a real fraud-analytics trick].
- **Ring detection:** connected components on edges above a weight cutoff, then Louvain communities. `ring_score = f(size, weighted density, distinct names per face/device, velocity)`.
- **Family exception:** shared address + phone, different faces, a common surname and plausible age gaps → reduced suspicion (this is also a hard-negative class in the data, see §5).

### 4.6 Fusion, decision and explanation

1. **Hard rules first:** invalid QR signature, checksum fail, liveness fail, or virtual camera → REJECT or forced REVIEW, regardless of the model. These are auditable and deterministic.
2. **XGBoost** on about 40 features (module risks + key raw features) → **isotonic calibration** → probability.
3. **Bands:** APPROVE < 0.3 ≤ REVIEW < 0.7 ≤ REJECT, configurable in the UI [Your plan]. Choose them with a **cost curve** (missed fraud costs about 10× a false positive) [Your plan].
4. **Step-up:** REVIEW band → an extra liveness challenge or (simulated) voice check → re-score once. Real KYC escalates rather than rejecting outright [Your plan], and partial automation is what won [Deriv].
5. **SHAP top-5** waterfall + reason codes per case.
6. **Fraud-type classifier** (rules over the signal pattern) + **recommended action**, the [SentiLink] idea:

| Type | Signature | Recommended action |
|---|---|---|
| First-party / Frankenstein | Valid ID number, registry face or name mismatch | Verify via issuer OTP / face authentication |
| Third-party fabricated | Thin file + new SIM + new email + no CKYC record | Require DigiLocker-fetched document or assisted video KYC |
| Synthetic ring | Cluster membership | Freeze linked applications, escalate to the fraud team |
| Bot / scripted | Telemetry anomalies + velocity | Block device, step-up challenge |
| Tampered document | QR/OCR mismatch, TruFor, forensics | Reject document, request re-upload through DigiLocker |
| Injection / replay | Virtual camera, liveness fail | Assisted video KYC |

7. **LLM summary:** input = structured module outputs only; output = 3–4 sentences that **must cite reason codes**; actions come from the fixed table above. If the API fails, a template fills in. [CallPilot]
8. **Investigator chat (Tier 2):** the LLM gets tools `get_case(id)`, `get_neighbors(id, hops)`, `explain_feature(name)`, so an analyst can ask "why are these 8 linked?". This is your LangGraph strength shown off safely.

---

## 5. Synthetic data (build this first: everything depends on it)

**Population:** 3,000 applications (start with 500 while iterating), Faker `en_IN`, spread over a 30-day timeline.

| Class | Share | Pattern |
|---|---|---|
| Genuine | ~70% | Consistent identity, unique device, normal typing |
| **Hard negatives (genuine)** | ~10% | Families sharing address/phone, hostel or office shared IP, students with new SIMs, name transliteration variants (Mohd/Mohammed, initials) |
| First-party / Frankenstein | ~4% | Real registry ID number + different face or name |
| Third-party fabricated | ~4% | Everything new, AI-generated portrait, thin file |
| Ring | ~6% | 5–10 identities sharing device, face, phone or address, sequential emails, one keystroke profile |
| Bot | ~3% | Paste-heavy, 8-second fills, bursts |
| Tampered document | ~3% | Poisson-blended DOB or name edit, face splice |

**Why the hard negatives:** without them the classes are trivially separable, your metrics will be near 100%, and judges won't believe them. Real fraud detection is hard because genuine people look odd too. [Reasoning]

**Images:**
- **Real faces:** LFW via `sklearn.datasets.fetch_lfw_people(min_faces_per_person=2)`. It has **multiple photos per person**, giving genuine selfie↔card pairs. It's small and needs one line to download.
- **AI faces:** a few hundred StyleGAN faces (e.g. a subset of Kaggle "140k Real and Fake Faces").
- **Cards:** our own fantasy "National ID" and "Tax ID" templates rendered with PIL. **Don't copy real government emblems.** Watermark every card "SPECIMEN", use fake numbers, and include the signed QR. [Reasoning: legal/ethical]
- **External benchmark for D2:** **FantasyID** (786 genuine, 1,572 forged cards with face swaps and text inpainting; mostly CC BY 4.0). Report the document module on it. Download it as soon as you start, and if it's gated or too big, skip it and say so. [DeepID]

**Leakage controls (critical):**
- Apply **random JPEG quality (60–95), resizing and noise to every card in every class**. [DeepID]: the winning team found real and fake images had been saved at different JPEG qualities (95 vs 75), so a model could learn the shortcut "low quality = fake".
- **Time-based split:** train on days 1–20, test on days 21–30 [Your plan].
- After training, **check the top features**. If something like "jpeg_quality" or "image_width" ranks high, you have a leak.

---

## 6. Evaluation (D5 + D7): the slides that win

### 6.1 Metrics page
- Precision, Recall, F1, FPR, ROC-AUC, PR-AUC, confusion matrix, latency p50/p95.
- **Define "Fraud Detection Rate" explicitly as recall on the fraud class**, and show FDR@top-3%/5% separately [Your plan]. This avoids a definition argument with judges.
- **Per-fraud-type recall**, so you can say which attack types you catch best.
- **Ablation chart:** each module alone vs fused. *This is the proof of the PS's core requirement (multi-source correlation).* [Your plan]
- Document module on FantasyID, compared with TruFor zero-shot (detection F1 0.746 on the FantasyID validation set, as reported in the DeepID paper) [DeepID].

### 6.2 Attack Lab

| Attack | Target | Defense shown |
|---|---|---|
| JPEG / resize sweep (quality 95 → 30) | Document | Semantic + QR checks don't degrade |
| Gaussian noise / blur sweep | Document, face | Fusion holds |
| Brightness / contrast | Document, face | Augmentation |
| Screen recapture (perspective + moiré) | Document, liveness | Passive checks + QR still readable |
| **Poisson-blended DOB edit** (`cv2.seamlessClone`) | Document | **TruFor misses it, QR↔OCR mismatch catches it** (the hero moment) [DeepID] |
| Face splice / AI portrait on the card | Document, biometric | Registry face mismatch + face reuse |
| Replay selfie (static photo / video) | Liveness | Random challenge fails |
| Virtual camera | Liveness | Device-label flag |
| Attribute perturbation (typos, transliteration) | Correlation | rapidfuzz fuzzy linking |
| Slow-and-low (spread over time and devices) | Behavior | Keystroke + face links still connect them |
| Humanized bot (random delays) | Behavior | Velocity + graph |
| **Adaptive attacker** | Fusion | See below |

**Adaptive attacker (the advanced robustness slide):** split the features into **attacker-controllable** (typing timing, email, device, IP, application time) and **non-controllable** (face, registry history, QR signature, SIM age). Run a greedy search that changes only the controllable features to minimize the fraud score, then report how much recall survives. The message: *"Even a fully adaptive attacker can't fake history, cryptography or their own face."* [Reasoning: standard feature-space evasion threat model]

**One PC:** precompute every attack result with a script (`eval/run_attacks.py`) and have the page display them. Run **one** attack live on a single card during the demo.

---

## 7. Screens

**Applicant:**
1. Consent + privacy note
2. Details form (telemetry captured silently)
3. ID upload (front + QR)
4. Selfie + active liveness
5. Step-up voice (simulated, only when routed there)
6. **Live pipeline view:** nodes turn green or red as LangGraph streams events over SSE [Your plan]
7. Result screen

**Analyst:**
1. **Queue:** risk, band, fraud type, filters.
2. **Case page:**
   - per-module score cards with reason codes
   - card with TruFor/ELA heatmap
   - face trio (selfie / card / registry) with similarity scores
   - graph neighborhood (2 hops)
   - SHAP waterfall, fraud type + recommended action, LLM summary
   - approve/override with notes (audit log)
3. **Graph explorer:** **Fraud Ring Simulator** button injects 8 linked applicants live and the graph lights up [Your plan].
4. **Metrics page.**
5. **Attack Lab:** attack picker, strength slider, before/after table, strength curve.
6. **Investigator chat** (Tier 2).

---

## 8. Folder structure

```
trueid-shield/
  frontend/                          # Next.js
    app/(applicant)/kyc/...          # consent, form, upload, selfie, progress, result
    app/(analyst)/dashboard/...      # queue, case/[id], graph, metrics, attack-lab, chat
    lib/telemetry.ts  lib/liveness.ts  lib/device.ts
  backend/
    app/main.py                      # FastAPI, SSE endpoint
    app/schemas.py                   # ModuleResult, ReasonCode enum + text table
    app/graph/pipeline.py            # LangGraph StateGraph
    app/modules/document/  qr_sign.py checksums.py ocr.py dates.py trufor.py forensics.py
    app/modules/biometric/ face.py liveness_verify.py sim_voice.py sim_fp.py
    app/modules/behavior/  features.py velocity.py keystroke.py anomaly.py
    app/modules/registry/  mocks.py (uidai, pan, telecom, ckyc, bureau routers)
    app/modules/correlation/ graph.py rings.py fuzzy.py
    app/fusion/            features.py train.py calibrate.py explain.py fraud_type.py
    app/llm/               summary.py investigator.py
    app/db.py                        # SQLite via SQLModel, audit log
  data/
    gen_population.py  gen_cards.py  gen_tampered.py  issuer_keys/
  eval/
    metrics.py  ablation.py  run_attacks.py  adaptive_attacker.py  fantasyid_eval.py
  models/                            # trufor weights, insightface, xgb.json, calibrator
  precomputed/                       # embeddings, heatmaps, attack results
  README.md                          # architecture, real-vs-simulated table, metrics, limitations
```

---

## 9. Timeline for one PC (≈24 h build; extras if you have 36 h)

| Hours | Work | Done when |
|---|---|---|
| **0–1** | venv, `pip install`, Next.js scaffold. **Start downloads in the background:** TruFor weights, InsightFace buffalo_l, EasyOCR models, LFW, FantasyID. **Test TruFor on CPU on one image** | All models load. TruFor time per image is known (keep or drop it) |
| 1–4 | Data: population + hard negatives + mock registries + cards with signed QR + tampered variants + leakage controls (start with 500) | A labeled CSV + images exist |
| 4–8 | Document agent (QR, checksums, OCR 3-way, date gate, cheap forensics) + registry agent + behavior features | Each returns a ModuleResult on a test applicant |
| 8–10 | Biometric (InsightFace match, reuse, liveness-frame verify, sims) + correlation graph + rings | Ring of 8 detected in the seed data |
| 10–12 | LangGraph pipeline + SSE + fusion training + calibration + **metrics + ablation script** | **Real numbers exist.** From here every change is measurable |
| 12–17 | Frontend: applicant flow with MediaPipe liveness + virtual-camera check, analyst queue + case page + graph view | A full flow works end to end in the browser |
| 17–20 | Attack Lab: precompute script + page + the Poisson hero attack + adaptive attacker; TruFor heatmaps if kept | Before/after charts render |
| 20–22 | LLM summary (+ template fallback), ring simulator, metrics page polish | Demo path complete |
| 22–24 | Seed the demo data, **record a backup video**, slides, rehearse 3 times | — |
| (+12 h if available) | Investigator chat, AI-portrait FFT detector, Hindi toggle on the applicant UI [FraudLens multilingual], FantasyID benchmark slide | — |

**Cut order** if you fall behind: investigator chat → Hindi → AI-portrait detector → TruFor (fallback described in §4.1) → voice/fingerprint UI → LLM summary (keep the template).

**Never cut:** signed QR + 3-way check, identity graph, liveness, metrics + ablation, Attack Lab (even fully precomputed), reason codes.

**One-PC performance rules:**
- **Precompute** embeddings, TruFor maps and attack results for the seeded data.
- Only the live applicant runs the full pipeline.
- Load models once at FastAPI startup.
- Stream progress, so a 6–8 s CPU run still feels fast.

**Windows install risks (check in hour 0):**
- `insightface` may need the Microsoft C++ Build Tools. If it fails, fall back to DeepFace with the ArcFace backend.
- TruFor's test script: confirm it runs on CPU.
- Keep everything in one Python 3.11 venv.

---

## 10. Demo script (5 minutes)

1. **Hook (20 s):** the thesis line from §0.
2. **Genuine applicant (40 s):** live flow, liveness, progress nodes turn green → APPROVE, with an evidence panel.
3. **Frankenstein fraudster (60 s):** valid ID number, but registry face mismatch + face reused under another name + thin file + 3-day-old SIM → REJECT. Fraud type "First-party" with the recommended action. **Show the failure path; that's when judges lean in** [Deriv].
4. **Hero attack (50 s):** a card whose DOB was edited with Poisson blending. *"The best ID-forgery detectors at ICCV 2025 scored at chance on exactly this."* TruFor shows clean, but the signed QR says DOB 1998 while the printed card says 1994 → caught.
5. **Fraud ring (45 s):** click the simulator, 8 identities connect through one device, one keystroke rhythm and a reused face.
6. **Attack Lab + metrics (45 s):** JPEG sweep (single module collapses, fused holds), adaptive-attacker result, ablation chart.
7. **Close (20 s):** privacy (hashed IDs, masking, consent, DPDP Act 2023), production path (DigiLocker document fetch, FAISS at scale, issuer QR keys), and the line *"the LLM only explains; it never decides."*

---

## 11. Judge Q&A prep

| Likely question | Answer |
|---|---|
| "Synthetic data, so your metrics mean nothing?" | Hard negatives, a time split, leakage checks (the JPEG shortcut from DeepID), an external FantasyID benchmark, and we claim **relative** gains (ablation), not absolute accuracy |
| "Why not just use Aadhaar e-KYC / DigiLocker?" | We recommend them as the fix for tampered documents. But synthetic IDs often use **real** numbers with a fake person, so you still need biometrics, history and graph correlation |
| "Deepfake detectors don't generalize." | Agreed, and DeepID proves it. That's why pixel detection is one weighted signal and not the decision |
| "Won't families get flagged?" | Specificity-weighted edges, IP downweighted for CGNAT, a family pattern exception, and hard negatives in training |
| "Why is there an LLM at all?" | Only for summaries and analyst Q&A, with output limited to cited reason codes. Decisions are deterministic, reproducible and auditable |
| "How does it scale?" | Stateless agents, FAISS ANN for faces, incremental graph updates, a queue in front of the pipeline |
| "What about privacy?" | ID numbers HMAC-hashed and masked to the last 4 digits, consent screen, data minimization, a retention policy, DPDP Act 2023 |

---

## 12. Sources
- DeepID Challenge overview paper (ICCV 2025): https://publications.idiap.ch/attachments/papers/2025/Korshunov_ICCV_2025.pdf
- DeepID challenge site: https://deepid-iccv.github.io/
- FantasyID dataset: https://www.idiap.ch/paper/fantasyid/
- Sunlight (winning DeepID team) code: https://github.com/ZeqinYu/ICCV-DeepID2025-Sunlight
- TruFor (CVPR 2023): https://github.com/grip-unina/TruFor
- Deriv AI Hackathon KYC winner write-up: https://shahzaib.netlify.app/blog/winning-deriv-ai-hackathon-kyc-rekognition-openai
- SentiLink scores and categories: https://help.withpersona.com/articles/2aYEhpHKbRvd2GWieHIbkv.md · https://www.celent.com/solutions/613184779 · https://marketplace.fico.com/synthetic-fraud-score
- CallPilot AI (LLM-only-classifies engineering): https://dev.to/manohar_paturi_2e0c6213f4/callpilot-ai-5b1m
- CyberShield 2026 judging criteria: https://pr.iith.ac.in/pressrelease/CYH2026.pdf
- FraudLens / Central Bank of India hackathon: https://financialservices.gov.in/beta/sites/default/files/2025-10/Central-Bank-of-India.pdf
