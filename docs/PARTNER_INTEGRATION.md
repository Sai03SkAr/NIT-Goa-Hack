# Connecting a partner KYC site to TrueID Shield

How to run TrueID Shield as the verification service behind a lender's own KYC website, and test the whole path end
to end. The worked example is **Kestrel Home Finance** (`clients/kyc-homeloan/`, port 3013), a 10-step home-loan KYC.
The same steps apply to Tideway (3011) and Meridian (3012).

## 1. How the pieces connect

```
Applicant's browser                 Lender's server (Node)                  TrueID Shield (FastAPI, :8000)
-------------------                 -----------------------                 ---------------------------------
Kestrel KYC pages  ── same-origin ─> clients/kyc-homeloan/server.js  ── X-Partner-Key ──>  /api/partner/v1/*
(http://localhost:3013)             holds the partner key; the browser       |  registry lookups (mock NSDL/UIDAI)
                                    never sees it                            |  liveness challenges
Lender ops console (/ops) <──────── analytics + verdicts <───────────────── |  per-document checks (card, bill, slip...)
                                                                             |  applications -> full pipeline -> verdict
                                                                             v
                                                          TrueID analyst dashboard (Next.js, :3000)
```

- **Who calls whom.** Only the lender's server calls TrueID, server to server, with its partner key. The applicant's
  browser only ever talks to the lender's site.
- **Isolation.** Each partner sees only its own applications and analytics. TrueID's analysts see everything, tagged
  `partner:<id>`.
- **Access.** `backend/app/security.py` is deny by default. `/api/partner/v1/*` requires a valid `X-Partner-Key`. The
  mock registries (`/mock/*`) stay analyst-only, so partners use `/api/partner/v1/registry/*`, which returns only what
  a real NSDL/DigiLocker response would give a bank.

| Piece | Where | Port |
|---|---|---|
| TrueID backend | `backend/` | 8000 |
| TrueID analyst dashboard | `frontend/` | 3000 |
| Kestrel site + ops console | `clients/kyc-homeloan/` | 3013 |
| Partner key (Kestrel) | `backend/app/partners.py` (`kestrel`) and `clients/kyc-homeloan/partner.json` | - |

## 2. One-time setup (Windows; the same commands work in Git Bash)

Prerequisites: Python 3.13, Node.js LTS, Git, about 3 GB of disk and a reasonable internet connection (the face and
OCR models are downloaded once, about 400 MB).

```powershell
# from the repository root
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt -c backend\constraints.txt

# download the models once (otherwise the first application waits for them)
.venv\Scripts\python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=-1)"
.venv\Scripts\python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"
```

If the downloads are slow, let them finish. Until they do, face checks and text reading report "unavailable"
(never "passed"), and nothing can be approved automatically.

## 3. Build TrueID's data and model

This creates the synthetic population and the mock registries, trains the fraud model and fills the database. It
takes 15-40 minutes, depending on the machine.

```bash
# Git Bash, from the repository root (the script picks .venv/Scripts/python.exe on Windows)
./scripts/build_all.sh
```

## 4. Enrol the partner's test people (with your face)

The build rewrites `data/generated/registry.json`, so run this **after** the build. It adds Kestrel's four test people
to TrueID's mock registries:

- **PAN (NSDL):** linked to the right Aadhaar
- **UIDAI:** with a registry photo
- **Telecom:** an old SIM in their name
- **CKYC and credit bureau:** a normal history

It also regenerates the sample documents so the ID cards are signed with this machine's issuer key.

```powershell
cd backend
..\.venv\Scripts\python ..\clients\kyc-homeloan\tools\enrol_in_trueid.py --photo C:\path\to\your_face.jpg --as riya-kamat
```

`--photo` is a clear, front-facing photo of you. It becomes Riya Kamat's UIDAI photo and her ID-card portrait, so your
live selfie can match both and TrueID can approve her. The other three people are enrolled without a face, so their
face checks come back unavailable and they go to review.

## 5. Start everything

Use three terminals, from the repository root:

```powershell
# 1. TrueID backend (restart it after any enrolment: the registries load at startup)
cd backend; ..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. TrueID analyst dashboard (optional, to watch cases arrive)
cd frontend; npm install; npm run dev        # http://localhost:3000, sign in with backend\.secrets\analyst_key

# 3. Kestrel, connected to TrueID
cd clients\kyc-homeloan; copy .env.example .env.local   # then set the values below
node server.js                                          # http://localhost:3013
```

`clients/kyc-homeloan/.env.local`:

```
TRUEID_MODE=remote                     # remote: always TrueID (fails loudly if it is down); auto: TrueID if up, else demo
TRUEID_API_URL=http://127.0.0.1:8000   # where TrueID runs
TRUEID_PARTNER_KEY=kh_test_3e8d14b9c702
```

The sidebar of the site says **"Live fraud checks connected"** when it is talking to TrueID. The ops console header
says **"Connected to TrueID Shield"**.

## 6. Check the connection

```powershell
python scripts\check_partner_connection.py
```

It tests every link and prints a fix for anything broken:

1. TrueID is up and its model is built
2. The partner key is required and accepted
3. The test people are enrolled
4. The PAN-Aadhaar link check works
5. Liveness challenges are issued
6. Document checks answer, and OCR is ready
7. The site is in connected mode and can verify a PAN through TrueID

Every line must say PASS before you test end to end.

## 7. End-to-end tests

Use Riya Kamat with your own face. Her values, and the files to upload, are listed under the site's **Test data**
button. Results appear in Kestrel's ops console (http://localhost:3013/ops, passcode `kestrel-ops`) and in TrueID's
dashboard (http://localhost:3000).

| # | Scenario | How | Expected at the step | Expected from TrueID |
|---|---|---|---|---|
| 1 | Genuine applicant | All Riya's values and files; do the head-turn check yourself | Every step green, cross-checks consistent | **APPROVE**; applicant sees "Identity verified" |
| 2 | Frankenstein identity | Arjun's PAN with Riya's Aadhaar | Step 4 blocks it: names differ, PAN not linked to this Aadhaar | - |
| 3 | Someone else's face | Riya's details, another person does the selfie | Passes the step | **REVIEW/REJECT**: face doesn't match the card and the UIDAI photo |
| 4 | Liveness not done | Stay still during the head-turn check | Passes the step | **REVIEW**: head turns not verified |
| 5 | Fake ID card | Upload any card whose QR wasn't signed by the issuer, or edit the card | Step 5: signature or QR-vs-print fails | **REJECT** for a bad signature or an edit that contradicts the QR; **REVIEW** if there is no QR |
| 6 | Old bill | `fraud-samples/old-bill-riya.jpg` at step 7 | Blocked: older than 2 months | - |
| 7 | Edited / AI documents | `edited-slip-riya.jpg` or `ai-generated-statement-riya.png` at step 8 | "Not saved by editing software" / "No AI marker" fails | Case flagged; applicant sees "under review" |
| 8 | Reused document | Apply as Arjun, upload Riya's electricity bill | "Not already used by another applicant" fails | Flagged |
| 9 | Income mismatch | Declare ₹90,000 but upload the ₹68,400 slip | Slip net pay and salary-credit checks fail | Flagged |
| 10 | Same ID, two names | Apply twice with Riya's Aadhaar under different names and mobiles | - | Second case: registry mismatch and shared-ID link; never approved (**REVIEW** or **REJECT**, depending on the model's score) |
| 11 | Repeat device | Several applications from one browser in a day | - | Velocity / possible mule pattern, **REVIEW** |

For each case, open it in the ops console and check three things:
- **TrueID's checklist:** card signature, face matches, liveness, registries, capture quality and so on.
- **Reasons:** why TrueID decided what it did.
- **"Checks this site ran":** Kestrel's own step results. TrueID shows these but never counts them as evidence.

## 8. API contract (what a partner implements)

All calls are server to server with `X-Partner-Key`. Interactive docs are at http://127.0.0.1:8000/docs.

| Call | Purpose |
|---|---|
| `GET  /api/partner/v1/registry/pan/{pan}` | NSDL-style PAN lookup: `{name, dob, id_last4}` |
| `GET  /api/partner/v1/registry/uidai/{id}` | e-KYC data after the applicant's OTP: `{name, dob, gender, address?}` |
| `GET  /api/partner/v1/registry/pan-link?pan=&id_number=` | `{pan_found, linked}` |
| `POST /api/partner/v1/liveness/challenge` | `{challenge_id, sequence[turn_left/turn_right], expires_in}` |
| `POST /api/partner/v1/documents/check` | multipart `kind`, `claims` (JSON), `owner`, `file` -> `{checks[{check,label,status,detail}]}` |
| `POST /api/partner/v1/applications` | multipart `payload` (JSON: form, device, telemetry, `challenge_id`, capture, partner_checks), `card`, `selfie`, `frames` (neutral + one per step) -> `{application_id}` |
| `GET  /api/partner/v1/applications/{id}` | Verdict: decision, risk, fraud pattern, reasons, evidence checklist |
| `GET  /api/partner/v1/applications` / `analytics?days=` | Ops list and dashboard numbers for this partner only |

**Status meanings.**
- **PASS** and **FAIL** mean the check ran.
- **UNAVAILABLE** means it could not run (a model is still loading, or a service is down).
- **NOT_PROVIDED** means the evidence was never given.

Only PASS counts towards automatic approval.

**Liveness.** Frames must answer a challenge TrueID issued: one-time, partner-bound, 15 minutes. Without a
`challenge_id`, liveness is NOT_PROVIDED, so the case can never be approved automatically.

## 9. Configuration reference

| Setting | Where | Default |
|---|---|---|
| Partner keys | `TRUEID_PARTNER_KEYS='{"kestrel":"..."}'` on TrueID; `TRUEID_PARTNER_KEY` in the site's `.env.local` | test keys in `partners.py` |
| Site mode | `TRUEID_MODE` = `auto`, `remote` or `local` (demo) | `auto` |
| TrueID address | `TRUEID_API_URL` | `http://127.0.0.1:8000` |
| Partner challenge lifetime | `TRUEID_PARTNER_CHALLENGE_TTL_S` | 900 s |
| Frames / upload size | `TRUEID_MAX_FRAMES`, `TRUEID_MAX_UPLOAD_BYTES` | 3 frames, 8 MB per image |
| Ops passcode | `OPS_PASSCODE` in the site's `.env.local` | `kestrel-ops` |

Adding another partner:
1. Add an entry to `PARTNERS` in `backend/app/partners.py`.
2. Copy `clients/kyc-homeloan/` (or another site).
3. Set the new site's `partner.json` (id, name, port, key, passcode).

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Verification service unavailable: ... not built yet" | No registry | Steps 3 and 4, then restart TrueID |
| "This PAN is not found" for a test person | Not enrolled, or enrolled before the build | Run step 4 again, restart TrueID |
| Text checks say "Text reader is unavailable" | EasyOCR models not downloaded | Step 2 pre-download; restart TrueID |
| Every case is REVIEW with "model unavailable" | Build not run | Step 3 |
| Face checks unavailable | InsightFace model missing, or no face in the registry photo | Step 2, then step 4 with `--photo` |
| ID-card signature fails on a teammate's machine | Cards were signed with another machine's issuer key | Run step 4 on that machine |
| 401 from TrueID | Wrong or missing partner key | Match `.env.local` with `partners.py` / `TRUEID_PARTNER_KEYS` |
| Site shows "Demo mode" | `TRUEID_MODE=local`, or TrueID unreachable in `auto` | Set `remote`, check `TRUEID_API_URL` |

## 11. Known limits

- Registries are mocks, and all identities are synthetic.
- Penny drop is simulated.
- Re-use detection catches the same file and digitally re-saved copies, not a re-photographed print.
- Metadata markers are strong evidence when present; their absence proves nothing.
- A real-time face swap that follows the head-turn instructions can pass a web liveness check (see
  `docs/THREATS_2024_2026.md`).
