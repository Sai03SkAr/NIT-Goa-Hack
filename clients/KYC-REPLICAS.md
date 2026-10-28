# KYC-only replicas

Two copies of **only the KYC part** of two real Indian onboarding flows, so TrueID Shield can sit behind them as the
verification backend. Each lives in its own folder, needs only Node.js (no `npm install`), and talks to TrueID through the
partner API.

| | Original (open it next to the copy) | Replica | Folder |
|---|---|---|---|
| **No gaps** | Zerodha signup: https://signup.zerodha.com/ | http://localhost:3011 | `kyc-zerodha-style/` |
| **With gaps** | HDFC Bank InstaAccount: https://applyonline.hdfc.bank.in/savings-account/insta-savings/open-instant-savings-account-online.html | http://localhost:3012 | `kyc-hdfc-insta-style/` |

Ops consoles (TrueID's verdict, reasons, risk by area, the checks the site ran): http://localhost:3011/ops (passcode
`tideway-ops`) and http://localhost:3012/ops (passcode `meridian-ops`).

The brands are fictional (Tideway Securities, Meridian Bank). Step order, fields, wording and validation follow the
originals. Meridian also follows HDFC's layout; Tideway has its own Dribbble-inspired look (dark step rail with a live
"verification requirements" checklist, camera stage with a face oval, document picker rows, result timeline), so compare
its steps with Zerodha's rather than its colours. Names and logos don't, because a pixel-exact bank KYC page that collects Aadhaar, PAN and selfies works as
a phishing page if it ever leaves your laptop.

## Run

Windows: double-click `clients/start-kyc.cmd`. Otherwise, in two terminals:

```
cd clients/kyc-zerodha-style && node server.js
cd clients/kyc-hdfc-insta-style && node server.js
```

## Steps, compared with the originals

**Tideway (Zerodha signup, KYC steps only)**

| # | Zerodha | Replica |
|---|---|---|
| 1 | Mobile number → SMS OTP | Same |
| 2 | Email: Continue with Google, or email OTP | Same (Google button shown, email OTP works) |
| 3 | PAN + date of birth, checked with the Income Tax Department | Same, against TrueID's mock PAN registry |
| 4 | Aadhaar through DigiLocker: Aadhaar number → OTP → consent → details fetched, not editable | Same (DigiLocker simulated in a pop-up). PAN and Aadhaar must be linked, and the names must match |
| 5 | Personal details: marital status, father's and mother's name, income, occupation, trading experience, PEP | Same |
| 6 | Webcam in-person verification (IPV) with location | Live camera only (no gallery upload), location asked, 4 frames sent to TrueID |
| 7 | Signature | Drawn on screen |
| 8 | Upload PAN card (and income proof for F&O) | Same |
| 9 | Review → eSign with Aadhaar OTP | Same |

Left out because they aren't KYC: trading segments, bank-account linking and nominee.

**Meridian (HDFC InstaAccount, KYC steps only)**

| # | HDFC InstaAccount | Replica |
|---|---|---|
| 1 | "Let's Get Started": Aadhaar-linked mobile, PAN **or** date of birth, consent notice | Same |
| 2 | "Help us confirm this is you!": OTP, 30-second resend timer, attempts left | Same |
| 3 | KYC, "Identify using": Central KYC (CKYC) / Aadhaar / Other Valid Documents | Same three options. CKYC and Aadhaar = OTP e-KYC; OVD = passport/DL/voter ID upload + branch visit |
| 4 | Upload Selfie | Same: a file upload, no live camera |
| 5 | Your Details: personal (name as per PAN, editable), email (verify **or skip**), Indian national / tax resident, address as per Aadhaar + communication address, financial profile, family | Same |
| 6 | Review | Same |
| 7 | Video KYC consent → account number shown, Video KYC "later" (within 12 months) | Same, but the account number appears only after TrueID's verdict comes back |

Left out because they aren't KYC: branch selection, account variant, family group, nominee.

**Gaps Meridian keeps on purpose** (they're what makes it the "gaps" site; TrueID is meant to catch what they let through):
the selfie is a gallery upload with no liveness; the name can be edited after e-KYC; email verification can be skipped;
PAN is optional (DOB-only login); OVD documents are typed in and uploaded, not fetched; the account opens before Video KYC.

## Connecting the TrueID backend

Both sites already speak TrueID's partner API (`POST /api/partner/v1/applications`, see `clients/README.md`). The two
partners are registered in `backend/app/partners.py` as `tideway` and `meridian`.

1. Start the backend as usual on port 8000.
2. That's it. In the default `TRUEID_MODE=auto` each site checks `http://127.0.0.1:8000/api/health` every 5 seconds and
   switches over by itself; the server window and the ops console say "Connected to TrueID Shield".

To change it, copy `.env.example` to `.env.local` in the site's folder:

| Setting | Meaning |
|---|---|
| `TRUEID_MODE=remote` | Always use the backend; fail if it's down (for the real demo) |
| `TRUEID_MODE=local` | Always use the built-in demo engine (no backend needed) |
| `TRUEID_API_URL=http://host:port` | Backend on another machine or port |
| `TRUEID_PARTNER_KEY=…` | Must match the key in `partners.py` / `TRUEID_PARTNER_KEYS` |

In connected mode the PAN and Aadhaar lookups go to the backend's `/mock/pan/…` and `/mock/uidai/…`, so use identities
from the test kit. In demo mode, press **Demo mode · Test data** (bottom left) for four test people.

What each site sends:

| | Tideway | Meridian |
|---|---|---|
| `card` | Uploaded PAN card photo | OVD front photo, or (Aadhaar/CKYC path) an image of the e-KYC record, since e-KYC hands over data, not a card photo |
| `selfie` | Live webcam photo | Uploaded photo |
| `frames` | 4 live frames | none |
| `liveness.performed` | true | false → TrueID won't auto-approve ("Verification incomplete") |
| `device`, `telemetry` | device hash, camera labels, location, typing rhythm | device hash, typing rhythm |
| `partner_checks` | mobile_otp, email_otp, pan_nsdl, digilocker_aadhaar, webcam_ipv, location, signature, pan_card_upload, esign | mobile_otp, pan_nsdl, aadhaar_ekyc_otp / ckyc_otp / ovd_upload, selfie_upload, email_otp (if done), vkyc_consent |

The applicant only ever sees approved / under review / declined. The score and reasons go to the ops console.

## Files

Each folder: `server.js` (static pages + the only code that holds the partner key; identical in both), `partner.json`
(name, port, key, ops passcode), `public/index.html` (the KYC flow), `public/kyc-common.js` (telemetry, device hash,
camera checks; identical in both), `public/ops.html` (operations console; identical in both). Demo-mode applications
are kept in `.trueid-local.json` (git-ignored); delete it to start fresh.

## Kestrel Home Finance: full home-loan KYC (port 3013)

`kyc-homeloan/`, http://localhost:3013 (ops: `/ops`, passcode `kestrel-ops`). A home loan asks for the most KYC
documents of any common journey, so this site uses TrueID for everything it can check. Every step shows its own
verification results the moment the applicant acts, and a **cross-checks** panel compares the same facts across all
documents collected so far.

| # | Step | Checked at the step | Cross-checked against |
|---|---|---|---|
| 1 | Loan amount + consent | Consent to KYC, TrueID and bureau checks recorded | - |
| 2 | Mobile & email | OTP on both (SIM age/subscriber checked by TrueID at submission) | - |
| 3 | PAN + DOB | Individual-PAN format, found in Income Tax records, DOB matches | - |
| 4 | Aadhaar e-KYC | Verhoeff checksum, record exists, UIDAI OTP | Name and DOB vs PAN; **PAN linked to this Aadhaar** (Income Tax link status) |
| 5 | ID card | TrueID: **issuer-signed QR valid**, QR vs printed text (needs OCR), ID checksum, AI-generator/editing metadata, re-use | **Card belongs to the person verified by Aadhaar** |
| 6 | Live selfie | Live camera only, no virtual camera, **TrueID-issued head-turn challenge** (frames verified on TrueID's server at submission) | Face vs ID card vs UIDAI photo (TrueID, at submission) |
| 7 | Electricity bill | Bill under 2 months (RBI), legibility, metadata, re-use, OCR: name/consumer no/date/PIN printed | Name vs Aadhaar (or declared relation); bill PIN vs current address |
| 8 | Salary slip + bank statement | Slip under 3 months, legibility, metadata, re-use, OCR of name/employer/net pay/account/credit | Employer vs declared; net pay vs declared (±10%); salary credit vs slip (±5%); names vs Aadhaar |
| 9 | Cancelled cheque + affordability | IFSC format, metadata, re-use, OCR; penny drop (simulated); FOIR ≤ 50% | Account vs statement; name vs Aadhaar |
| 10 | Review, signature, eSign | Aadhaar OTP eSign | Everything above is sent to TrueID |

At submission TrueID runs its full pipeline (document, biometrics, liveness, registries, behaviour, cross-application
graph) and returns the identity verdict. Kestrel's step checks travel as `partner_checks`: shown to Kestrel's team in the
ops console, never counted by TrueID as evidence. If any step was flagged, the applicant sees "under review" even when
TrueID approves.

**New TrueID endpoints** (partner key): `POST /api/partner/v1/documents/check` (ID card: signed QR + card module;
supporting documents: metadata, re-use across applicants, legibility, OCR of typed values) and
`GET /api/partner/v1/registry/pan-link`. Code: `backend/app/modules/document/supporting.py`.

**Test documents**: `kyc-homeloan/public/test-documents/` (also linked from the "Test data" button): an ID card with a
QR signed by TrueID's issuer key, an electricity bill, salary slip, bank statement and cheque for each test person,
plus fraud samples (old bill, bill in another name, slip saved by Photoshop, statement with an AI-generator marker,
and re-using one person's bill for another). Regenerate with
`cd backend && ../.venv/Scripts/python.exe ../clients/kyc-homeloan/tools/make_test_docs.py --photo me.jpg` to put your
own face on the cards, so the live selfie can match.

**Limits, stated**: text checks need EasyOCR's models (downloaded on first use; until then those checks say
"unavailable", never "passed"). Re-use detection catches the same file and digitally re-saved copies, not a
re-photographed print. Metadata markers are strong when present; their absence proves nothing. Penny drop is simulated.
