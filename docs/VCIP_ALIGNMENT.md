# TrueID Shield vs Indian KYC standards and research

A map from the binding Indian standard (RBI's Master Direction on KYC, V-CIP section), UIDAI/ReBIT Aadhaar
verification, and current research, to what this project implements. "Done" means implemented and tested here, not
certified. This is a hackathon demo on synthetic data, not a compliant production system.

## RBI V-CIP (Video-based Customer Identification Process) technical requirements

| RBI V-CIP requirement | TrueID Shield |
|---|---|
| Liveness / spoof detection that rejects "a photo, video or face spoofing attempt" | **Done for still photos.** The server issues a random head-turn sequence and verifies a **burst of frames** shows a continuous live turn (`app/modules/biometric/agent.py::_motion`): a few stills fail with `BIO_NO_MOTION`. Open limit: a full video replay of the victim still passes; production needs certified PAD (ISO/IEC 30107-3) or a native app with device attestation. |
| Face match: live capture vs the document photo | Done. ArcFace 1:1, selfie vs card and vs the issuer registry photo, threshold set at FAR 0.1%. |
| Randomised sequence so a replay can't be pre-staged | Done. Server-chosen left/right order, single use, 3-minute TTL, bound to the applicant session (`liveness_sessions.py`). |
| Geo-tagging: live GPS coordinates + timestamp in the record | **Captured and recorded.** The browser sends a consented GPS fix; it is stored on the application and shown on the case page. Not scored (a self-reported fix can't be trusted as proof), per "informational" evidence. |
| Block connections from outside India / spoofed IPs | **Partial / honest.** The client IP is taken from the network peer (X-Forwarded-For only from a trusted proxy) and recorded. On localhost there is no public IP to geolocate; production plugs an India allow-list geoIP where the code is marked `shortcut`. |
| Audit trail with documented decision logic for every approve/reject | Done, and **hash-chained** (`/api/audit/verify` detects any edited entry), beyond the ask. Each decision stores its policy version and every check's status. |
| Maker-checker: the officer who ran the session can't approve it | Done for overrides: approving an automated REJECT needs a **second analyst session** and a written reason. Weakness: analysts share one key rather than being named officers. |
| Consent-based, recorded | Done. Consent version is required on submit and stored with the case. |
| Recording retention | Partial. Uploaded images are deleted after 30 days (a privacy choice); production would retain the session record for the mandated period. |

## UIDAI / ReBIT (Aadhaar offline verification)

Our signed-QR model mirrors UIDAI's Secure QR: issuer-signed resident data, verified against the issuer's published
public certificate, and "verification is not complete" on a printed card unless the QR signature checks out. We use an
Ed25519 demo issuer key, plus an optional AES-256-GCM **encrypted** QR (`TID3`) so a casual scan reveals nothing.
Production would verify against UIDAI's certificate and consume DigiLocker / Aadhaar Offline e-KYC signed XML instead
of a photographed card.
- UIDAI, validating the Secure QR / offline e-KYC signature: https://uidai.gov.in/en/283-faqs/aadhaar-online-services/e-aadhaar/1892-how-to-validate-digital-signatures-in-e-aadhaar.html

## Research alignment

"Agentic AI Microservice Framework for Deepfake and Document Fraud Detection in KYC Pipelines" (JISEM, 2024) proposes
almost exactly our architecture: autonomous micro-agents, pipeline orchestration, dynamic retries and
human-in-the-loop escalation, modular vision + liveness + deepfake + OCR document forensics + multimodal identity
linking + a policy-driven risk engine. We implement each as the document/biometric/behaviour/registry/correlation
agents feeding `app/policy.py`, with a REVIEW step-up and analyst review. The one idea we don't lean on is
hot-swapping individual detector models without downtime.

## Sources
- RBI Master Direction on KYC (V-CIP) and amendments: https://www.rbi.org.in (consolidated Master Direction)
- V-CIP requirement summaries: https://hyperverge.co/blog/rbi-video-kyc-guidelines/
- Agentic KYC framework paper: https://arxiv.org/pdf/2601.06241
- UIDAI Secure QR / offline e-KYC: https://uidai.gov.in/en/283-faqs/aadhaar-online-services/e-aadhaar/1892-how-to-validate-digital-signatures-in-e-aadhaar.html
