# TrueID Shield: one page

**Hacksploit 2026 · PS3: Synthetic Identity Fraud Detection in Automated KYC**

## The problem
A synthetic identity mixes real and invented data: a valid ID number, a real-looking card, a face that matches its
photo. **It passes every single check on its own.** India's mule-account crackdown and the rise of AI-made IDs and
deepfake selfies make this the KYC fraud that matters now.

## Our answer, in one sentence
**Trust no single check.** TrueID approves only when *every* required check passes, and it correlates documents,
face, behaviour, government registries, every past application and other banks' signals, so fraud has to stay
consistent everywhere at once.

## How it works
| Layer | What it does |
|---|---|
| **Document** | Trust comes from the issuer's **signed (and encrypted) QR**, not from pixels; an edit contradicts its own QR |
| **Face + liveness** | Selfie vs card vs issuer photo; server-chosen head-turn, verified on a **video burst** |
| **Behaviour** | Typing rhythm, bots, velocity; keystroke rhythm **links different identities typed by one fraudster** |
| **Registries** | PAN, Aadhaar-like, telecom (SIM age), CKYC, credit bureau (mocks) |
| **Identity graph** | Shared device / phone / face / ID across applications; Louvain rings; mule herding |
| **Cross-bank network** | Banks share **keyed hashes only**; same ID under another name elsewhere, or rejected elsewhere, is held |
| **Decision policy** | Missing or unverifiable evidence **never** approves; the LLM only explains |

**It improves, under supervision.** A learning loop turns analyst decisions into proposals (better cut-offs, a retrained challenger model, alerts on drift and on checks that stop running). Nothing changes until an analyst approves, and every change rolls back in one click. Applicants get tips for issues they can fix, never an explanation of fraud signals. An assistant (**Ask TrueID**) answers analysts' questions about the live analytics from the data itself.

## Proof (time-split test: 444 applications, 85 fraud)
| | |
|---|---|
| Fraud caught (recall) | **100%** |
| ROC-AUC | **0.998** (best single module 0.98, document alone 0.78) |
| Reject precision | **95%** (84 of 88 rejections were fraud) |
| False-positive rate | 9.5%, mostly "review", not "reject" |
| Edited date of birth | Top forgery detector (TruFor) **at chance (0.49)**; our signed-QR check catches **~95%** |
| Under attack | No fraud approved at any attack strength; **adaptive attacker: 0 of 85** frauds slipped through |

## Built for banks
A lender keeps its own KYC website; its server calls TrueID with a partner key. Working demos: **Kestrel Home
Finance** (10-step home-loan KYC, every document checked and cross-checked as it's uploaded), plus Zerodha-style and
HDFC-style flows. Each lender gets verdicts, reasons and analytics for its own customers only.

## What we don't claim
Data and registries are synthetic, so absolute numbers are optimistic: the claim is the **relative gain** of
correlation. Voice biometrics and penny drop are simulated. A real-time face swap that follows instructions can pass web
liveness; certified attack detection is the production step.

## Demo in 3 minutes
1. Genuine applicant on Kestrel → every step green → **approved**.
2. Same Aadhaar, another name → blocked at the PAN-Aadhaar check; at another bank → **network alert**.
3. Attack Lab, live **date-of-birth edit**: looks perfect, pixel score unmoved, signed QR disagrees → **rejected**.
