# PS3 — Synthetic Identity Fraud Detection in Automated KYC: deliverable-by-deliverable

Mentor-facing map from the official Hacksploit 2026 PS3 mandatory deliverables to exactly what TrueID Shield
implements, how it works, and the measured proof. Numbers are from the latest build on a time-split test set of
**444 applications, 85 of them fraud**.

**The thesis to open with:** the PS says a synthetic identity combines real and fabricated data, so it passes each
check in isolation. So the system never trusts one check — a case is APPROVED only if *every* required check passes,
**and** it correlates across documents, biometrics, behaviour, registries and prior applications. The honest framing:
the individual checks (document, face, OCR, liveness) are commodity; our contribution is the **correlation + decision
layer that assumes any single check can be fooled**, and treating KYC as a system we attack ourselves.

---

## 1. Multi-source data correlation
**What it asks:** combine many signals so an identity that looks clean on one axis still gets caught.

**What we have:** five independent agents — document, biometric, behaviour, registry, correlation — plus a
cross-application **identity graph**. Every new application is linked to past ones by shared device, phone, address, a
keyed hash of the Aadhaar number, email pattern, face, and typing rhythm. Rare shared things (a device, a phone) count
much more than common ones. A clustering algorithm (**Louvain**) spots dense clusters, which are fraud rings; a
"family" exception avoids flagging a household that shares an address.

**Proof:** on its own, each source is weak — document 0.78, correlation 0.68, behaviour 0.85, registry 0.91,
biometric 0.98 (ROC-AUC). **Combined: 0.998.** Fraud recall goes from 0.52 (document alone) to 1.00 fused. That jump
is the evidence that correlation, not any one check, does the work.

**Across institutions (new):** a privacy-preserving **consortium network** (`backend/app/consortium.py`). Each
institution's identifiers (ID number, PAN, phone, email, device, account, name) leave it only as keyed hashes
(HMAC-SHA256), so no bank sees another's customers. TrueID alerts when the **same ID number or PAN appears under a
different name at another institution**, when an identifier was **rejected for fraud elsewhere**, or when **one device
onboards several people across institutions** in a week. Answers are counts only (never which bank or which name), and
an alert can only hold a case for review, never approve or reject it alone. It's the same idea as RBI's DPIP and the
I4C-RBIH mule-intelligence sharing, applied at onboarding. Banks outside TrueID join with the reference client
(`scripts/consortium_client.py`). Limit, stated: members share the HMAC key, so production should use an oblivious PRF /
private set intersection.

**Ours vs everyone's:** per-applicant PAN/registry checks are commodity. The **graph that catches rings at
onboarding**, extended **across institutions without sharing PII**, is the differentiator.

## 2. AI-generated document forgery detection
**What it asks:** catch forged or AI-made ID documents.

**What we have:** the card's trust comes from a **cryptographic signature on its QR** (the Aadhaar Secure-QR model),
not from "does the pixel look fake." A generated or edited card can't produce a valid signature, and any edit
disagrees with its own signed QR. On top: Verhoeff checksum, PAN format, impossible-date checks, pixel forensics, the
**TruFor** forgery model (as evidence only), and metadata markers that reveal AI generators or photo-editing software.
Cards can also carry a **signed and encrypted QR** (AES-256-GCM over the signed text), so a stranger who scans the card
learns nothing. Documents nobody signs (electricity bill, salary slip, bank statement, cheque) are checked as they are
uploaded: AI/editing metadata, the same image already used by **another applicant**, legibility, and OCR that the values
the applicant typed are actually printed on the page.

**Proof / the striking finding:** on edited date-of-birth cards, TruFor (a top research forgery detector) performs at
chance (~0.49) and even flags clean cards, while our **signed-QR-vs-print check catches ~95%.** Lesson for the mentor:
for text edits, a signature beats state-of-the-art pixel forensics.

**Ours vs everyone's:** forgery CNNs are commodity; making **cryptographic provenance the trust root, and proving it
beats the SOTA detector**, is ours.

## 3. Behavioural pattern analysis across applications
**What it asks:** analyse behaviour across applications, not one session.

**What we have:** how the form is filled (timing, pasting, key rhythm — content is never logged), bot signals (filled
too fast, heavily pasted, machine-regular timing), velocity (how many applications from one device/IP/phone in
1h/24h/7d), sequential emails (ring.sv01/02/03), an anomaly model (**Isolation Forest**), and the clever one:
**keystroke rhythm used to link identities.** Normally keystroke dynamics authenticate one person; we flip it to
detect when one fraudster is typing many "different" identities. Missing telemetry is treated as unknown, never faked
as normal.

**Proof:** behaviour-only ROC-AUC 0.85; scripted bots caught 100%; a "humanised" bot and a slow ring spread over days
are still caught because the face/keystroke links connect them.

## 4. Biometric verification (face / voice / fingerprint — simulated allowed)
**What it asks:** biometric checks; voice/fingerprint can be simulated.

**What we have:** **face is real** (InsightFace / ArcFace) and matched three ways — selfie vs card photo vs the
**issuer's registry photo** — at a strict threshold (0.1% false-accept). A 1:N search catches one face reused under
different names. **Liveness is real and server-checked:** the server picks a random head-turn order, the browser sends
a continuous **burst of frames**, and the server confirms one live person swept smoothly through each requested turn in
order (a few still photos fail with `BIO_NO_MOTION`); an uploaded photo counts as "not provided" and can't be
auto-approved. Voice/fingerprint are **simulated and clearly badged — and never used in the decision** (we're honest
about what's real).

**Proof:** biometric-only ROC-AUC 0.98 (strongest single module); stolen-ID-with-another-face ("Frankenstein") never
auto-approves because the face fails against the registry.

## 5. Adversarial robustness evaluation
**What it asks:** test it under attack.

**What we have:** an **Attack Lab** that perturbs real cards/selfies (JPEG, noise, blur, brightness, screen-recapture)
and re-runs everything; scenario attacks (virtual camera, replay photo, face splice, humanised bot, ring spread over
time); and an **adaptive attacker** that greedily changes every feature a fraudster actually controls to try to slip
through.

**Proof:** across every attack at every strength, **no fraud is approved and recall stays 100%**; at most ~4% of
genuine users get rejected (very bad photos are sent to "retake," not rejected). The adaptive attacker turned **0 of
85** frauds into approvals.

**Ours vs everyone's:** shipping a built-in attack harness and publishing evasion resistance is the "cybersecurity
platform" framing — vendors don't do this.

## 6. End-to-end KYC pipeline simulation
**What it asks:** a full working pipeline.

**What we have:** a real pipeline (ingest → four agents in parallel → correlation → fusion → step-up → decide →
explain → persist), an applicant flow (`/kyc`) with consent, liveness and a plain-language result, and an analyst
console (`/dashboard`) with the case file, evidence checklist, identity graph, risk drivers, metrics, Attack Lab and
an investigator chat. Plus the **partner integration**: real lender sites (Kestrel Home Finance, etc.) call TrueID
server-to-server with a partner key, each isolated, analysts see everything — that's the market-use architecture.

## 7. Performance metrics
**What it asks:** precision, recall, fraud-detection rate.

Measured (time-split, 444 test apps, 85 fraud):
- **Fraud-detection rate / recall: 1.00** (0 fraud missed)
- Precision 0.71, **F1 0.83**
- False-positive rate 9.5% (mostly sent to review, not rejected)
- **ROC-AUC 0.998**, PR-AUC 0.982
- Of 88 rejections, 84 were real fraud (**95% reject precision**)
- Fraud-type labelled correctly **86%** of the time

**Be honest about this before the mentor is:** the data is synthetic, so a perfect recall (0 missed) is optimistic —
the credible claim is the **relative gain** (fused 0.998 vs any single source ≤ 0.98) plus the adversarial results,
measured on a proper time-based split with 95% confidence intervals and leakage checks. (These offline numbers don't
include the cross-institution network, which only adds review holds on live cases.)

---

## What we took from IDRBT (the RBI's banking-technology research institute)
Full detail and measurements: `docs/IDRBT_INNOVATION.md`.
- **Explainable one-class "genuine profile"** (after IDRBT's COMSNETS 2025 paper): rules learnt from genuine applicants
  only. On fraud types the model never saw, the **model alone catches 0% of bots and 40% of tampered cards; the profile
  catches 94% and 100%**; the live system catches 100%. No fraud labels needed (ROC-AUC 0.984). Shown on every case as
  readable rules, never a decision gate.
- **One-shot federated learning** (after IDRBT's FedPNN): banks share only cluster summaries; with different customer
  bases the federated profile reaches AUC 0.991 and flags 99% of fraud vs 0.982 / 87% for a bank alone.
- **Generative adversarial attacker** (after IDRBT's chaotic-VAE adversarial ML): evades a behaviour-only detector on
  **49 of 49** frauds, and **0 of 85** on TrueID.
- **Counterfactual "what would change this decision"** (after IDRBT's counterfactual XAI): per case, whether anything
  the applicant controls could flip it. A per-decision robustness margin, analyst-only.

## Likely mentor questions, with answers
- **"What's new vs what I built 5 years ago?"** → Not the checks (those are commodity). The **decision-and-correlation
  layer**: evidence-first policy, onboarding-time identity graph, algorithms repurposed as cross-identity linkers, and
  built-in adversarial testing.
- **"Recall 1.0 — overfit?"** → Synthetic data makes absolutes optimistic; we lean on the ablation's relative gain and
  the adversarial / confidence-interval results, not the 1.0.
- **"Why would a bank buy it?"** → It sits behind their existing KYC site, targets synthetic/mule fraud RBI is
  actively cracking down on, runs on open models with no per-call cost, and gets stronger with every member: the consortium network catches an
identity reused across banks without any bank sharing customer data.
- **"Robustness?"** → No fraud approved under any attack; adaptive attacker 0/85; a generative (chaotic-VAE) attacker
  that beats a behaviour-only detector 49/49 gets 0/85 on TrueID; fused beats every single module.
- **"What about fraud you've never seen?"** → Retrain without each fraud type: the model alone misses unseen bots (0%),
  the label-free genuine profile catches 94%, and the evidence policy catches all of them.
- **"Did you use Indian research?"** → Yes: four algorithms from IDRBT's published fraud research, transferred from
  ATM/card fraud to KYC onboarding and measured on our data (`docs/IDRBT_INNOVATION.md`).
- **"Why not score people on their social media?"** → Scraping breaks platform terms and DPDP purpose limitation, and
  marking people down for a thin footprint would hold 20% of our genuine applicants. We built an optional, consented
  footprint check (email/phone age, a linked account) that only flags contradictions, such as a linked account in another
  name, and never decides (`docs/DIGITAL_FOOTPRINT.md`).

## Where this lives in the code
- Decision policy: `backend/app/policy.py` · fusion/model: `backend/app/fusion/`
- Agents: `backend/app/modules/{document,biometric,behavior,registry,correlation}/`
- Identity graph: `backend/app/modules/correlation/history.py`
- Signed QR: `backend/app/modules/document/qr_sign.py` · supporting docs: `modules/document/supporting.py`
- Pipeline: `backend/app/graph/pipeline.py` · partner API: `backend/app/partners.py`
- Adversarial: `eval/run_attacks.py`, `eval/adaptive_attacker.py` · metrics: `eval/train.py` → `precomputed/metrics.json`
- Cross-institution network: `backend/app/consortium.py`, member client `scripts/consortium_client.py`
- Governed self-learning and applicant tips: `backend/app/learning.py` (`docs/LEARNING_LOOP.md`)
- Analytics assistant (Ask TrueID / Investigator): `backend/app/llm/assistant.py` (`docs/ASSISTANT.md`)
- Alignment & threats: `docs/VCIP_ALIGNMENT.md`, `docs/THREATS_2024_2026.md`, `docs/PARTNER_INTEGRATION.md`
