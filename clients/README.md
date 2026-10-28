# Partner client sites

TrueID Shield as a backend: a bank or wallet keeps **its own** KYC form, and its server sends the evidence to TrueID's
partner API. The verdict goes to the partner's operations team. The applicant only sees "account open",
"under review" or "declined", never a fraud score.

Two fictional partners show the two ends of Indian digital onboarding:

| | **Northstar Bank** (`northstar-bank/`, port 3001) | **PayLite Wallet** (`paylite-wallet/`, port 3002) |
|---|---|---|
| Modelled on | Full-KYC broker/bank signups (Zerodha-style) plus RBI V-CIP rules | Minimum-KYC wallets and instant-loan apps |
| Mobile | OTP | OTP |
| Email | OTP | Typed, never verified |
| PAN | Checked with NSDL (simulated): must exist and match the DOB | Optional, format check only |
| Name / DOB / ID number | Fetched from DigiLocker (simulated); applicant can't edit them; ID must be the one linked to the PAN | Self-declared, never checked |
| ID card image | Live camera capture, or the DigiLocker e-ID file | Any image from the gallery |
| Selfie | Active liveness (2 random challenges, frames sent to TrueID for a server re-check) | Photo upload, **no liveness** |
| Location | Asked (V-CIP requires India) | No |
| Signature / eSign | Drawn signature + eSign OTP | No |
| TrueID signals SDK (typing rhythm, device id) | Yes | Yes |

**Northstar has no gaps of its own.** What still gets through is fraud that passes every single check: a stolen identity with
a phished OTP, an edited card whose QR doesn't match, a face already used under another name. Only TrueID's
cross-application graph and document/biometric correlation catch those.

**PayLite's gaps are deliberate.** TrueID is its only real identity check. Because PayLite never runs liveness, TrueID never
auto-approves its applicants: a clean one comes back `REVIEW` / "Verification incomplete" and PayLite opens a limited
₹10,000/month wallet. Anything with a fraud pattern is `REVIEW` or `REJECT` with reasons.

## Run

**Windows:** double-click `clients/start.cmd`. **macOS / Linux:** `./clients/start.sh`.
It installs both sites the first time, starts them, and opens:

| Page | Northstar Bank | PayLite Wallet |
|---|---|---|
| Customer site | http://localhost:3001 | http://localhost:3002 |
| Onboarding | `/onboard` | `/start` |
| Operations console | `/ops` (passcode `northstar-ops`) | `/ops` (passcode `paylite-ops`) |

You need Node.js (LTS). Nothing else is required to try the screens.

### Demo mode and connected mode

Both sites talk to TrueID through one file, `lib/trueid.ts`. Set `TRUEID_MODE` in `.env.local` (copy `.env.example`):

| `TRUEID_MODE` | What answers | Use it for |
|---|---|---|
| `auto` (default) | The TrueID backend when it's running on `TRUEID_API_URL`, otherwise demo mode | Everyday use: start the backend and the sites switch over within 5 seconds |
| `remote` | Always the TrueID backend; errors if it's down | Final demos, so a stopped backend can't silently fall back |
| `local` | Always the built-in demo engine (`lib/trueid-local.ts`) | Working on the screens without the Python backend |

The ops console says which one is live ("Connected to TrueID Shield at …" or "Demo mode").

**Demo mode** answers the PAN and DigiLocker lookups from four test identities. Press **Test data** on the onboarding page to see them.
Verdicts come from a few plain rules: registry mismatch, the same ID under two names, phone and device reuse, fill speed,
paste-heavy or robotic typing, virtual camera, and missing liveness. It does not look at images. It returns exactly the same
JSON as the real partner API, so nothing else changes when you connect the backend.

**Connected mode** uses the full pipeline. Start the backend (`./scripts/run_backend.sh`) and leave `TRUEID_MODE=auto`.
PAN and DigiLocker then come from TrueID's mock registries, so use identities from the test kit or the presenter kit
(`/kyc?demo=1` on the main frontend). A different machine or port only needs `TRUEID_API_URL`.

Northstar copies the MediaPipe files it needs into `public/mediapipe/` on `npm run dev`. The wasm comes from its own
node_modules and the face model from `frontend/public/mediapipe/`.

### Demo script (connected mode, with the presenter kit)
OTPs are simulated in both modes: the code appears on screen as a demo message.

1. **PayLite, genuine:** upload the genuine card and a photo → wallet ready with limits; the ops console shows "Verification incomplete".
2. **PayLite, hero DOB edit:** type the edited DOB and upload the Poisson-edited card → TrueID rejects it: the signed QR disagrees with the printed DOB.
3. **PayLite, Frankenstein:** stolen identity with your face → TrueID flags face reuse and a registry face mismatch.
4. **Northstar, genuine:** full flow with the live selfie → approved; every check is ticked in the ops console.
5. **Northstar, Frankenstein:** passes PAN, DigiLocker (phished OTP) and liveness, because the attacker is live. TrueID still catches the face mismatch against the issuer photo and the reused face.

## Partner API (TrueID side)

All calls carry `X-Partner-Key`. Keys are server-side only. Defaults are in `backend/app/partners.py`; override them with
`TRUEID_PARTNER_KEYS='{"northstar":"…","paylite":"…"}'`.

```
POST /api/partner/v1/applications        multipart
     payload  JSON  {reference, form{name,dob,gender,id_number,phone,email,pan?,address?,pincode?},
                     device{device_id,user_agent,ip,camera_labels,active_camera,geo?}, telemetry{…},
                     liveness{performed, passed, challenges[], virtual_camera},
                     capture{card,selfie}, partner_checks{mobile_otp,email_otp,pan_nsdl,…}}
     card     image   required
     selfie   image   required
     frames   image[] liveness frames, optional (≤ 8)
  → {application_id, status: "processing", status_url}

GET  /api/partner/v1/applications/{id}
  → {status: processing|completed|error, decision: APPROVE|REVIEW|REJECT, risk_score, fraud_type, fraud_label,
     recommended_action, reasons[{module,code,text,weight}], modules[{module,risk}], decision_rules[], summary,
     partner_checks, capture, applicant (masked)}

GET  /api/partner/v1/applications        this partner's applications, newest first
```

A partner can only read its own applications (404 otherwise). `partner_checks` is shown back to the partner and never
lowers TrueID's risk. It is a client claim, not evidence. `liveness.performed: false` (or no frames and no challenges)
marks the liveness check as **not performed**. That is missing evidence, not a failed challenge: the model sees it as
missing, a hard rule (`BIO_LIVENESS_NOT_PERFORMED`) blocks automatic approval, and the case is labelled
"Verification incomplete", not "injection".

Applications from partners also appear in TrueID's own analyst dashboard, with source `partner:northstar` / `partner:paylite`.

Tests (pipeline stubbed, no models needed): `cd backend && ../.venv/bin/python -m pytest tests/test_partner_api.py -q`
