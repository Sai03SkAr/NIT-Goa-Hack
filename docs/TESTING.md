# Testing TrueID Shield

Four levels, fastest first. Backend must be running (`./scripts/run_backend.sh`, port 8000) and the frontend
(`cd frontend && npm run dev`, port 3000 or 3001).

## 0. Unit and access-control tests (seconds, no servers)

```bash
cd backend && ../.venv/bin/python -m pytest tests -q
```

**Proper:** all pass. They cover the decision policy (missing or simulated evidence never approves, model unavailable
means REVIEW, signature failure rejects), access control (case files, images, mock registries and demo tools need the
analyst; cross-site POSTs are refused; applicants only see their own jobs), single-use liveness challenges, signed QR
forgery and tampering, the hash-chained audit log, missing telemetry, AI-generator metadata and mule herding.

## 1. Automated acceptance test (about 3 minutes, no camera)

```bash
.venv/bin/python scripts/run_tests.py
```

It signs in with the analyst key (`backend/.secrets/analyst_key`), builds a **fresh** test kit (people the system
has never seen, enrolled in the mock registries), then for every scenario opens an applicant session, asks the server
for a liveness challenge, answers it with **fixture still photos** of the same person, submits with consent and an idempotency key, and polls
until the decision is saved. Those are stills, not a live camera, so they **cannot pass the live head-turn** motion
check: genuine scripted cases land in REVIEW by design. APPROVE is only reachable on a real webcam (section 3).

**Proper:** every line PASS. A report is written to `data/generated/testkit/<tag>/REPORT.md`.

| Scenario | Expected | What must happen |
|---|---|---|
| 01 Genuine applicant | REVIEW | Everything matches, but scripted stills can't prove a live turn (`BIO_NO_MOTION` / `BIO_CHALLENGE_FRAMES`); only a webcam gives APPROVE |
| 02 Name written with an initial (`R. Kulkarni`) | REVIEW | Fuzzy Indian-name match accepts it; REVIEW only for the same liveness reason |
| 03 Head never turned (still frames) | REVIEW or REJECT | Liveness FAIL (`BIO_LIVENESS_FAIL`); never APPROVE |
| 04 DOB edited on the card (hero attack) | REJECT | `DOC_QR_OCR_MISMATCH` |
| 05 Counterfeit card (QR signed by a fake key) | REJECT | `DOC_QR_SIG_INVALID` |
| 06 Stolen ID + someone else's face | REJECT | `BIO_REGISTRY_FACE_MISMATCH`, `REG_SIM_NEW` |
| 07 Fabricated identity (no QR, unissued ID) | REJECT/REVIEW | `REG_ID_NOT_FOUND`, `DOC_QR_MISSING` |
| 08 Someone else at the camera | REVIEW or REJECT | `BIO_CARD_FACE_MISMATCH`; never APPROVE |
| 09 ID number with a wrong digit | REJECT/REVIEW | `DOC_CHECKSUM_FAIL` |
| 10 Virtual camera reported | REVIEW or REJECT | `BIO_VIRTUAL_CAMERA`; a client-reported hint, so it blocks approval rather than proving fraud |
| 11 Scripted bot, one still replayed as every frame | REJECT/REVIEW | `BEH_*` signals plus `BIO_FRAMES_DUPLICATE` |
| 12 Ring members 1-3 | REJECT | Members 2-3 show `BEH_EMAIL_SEQUENCE`, `BEH_KEYSTROKE_LINK`, `BIO_FACE_REUSED` |
| 13 Recruited account holders 1-3 (one phone) | REVIEW x3 | The third shows `COR_MULE_HERDING`. All REVIEW on scripted stills; on a webcam members 1-2 are APPROVE |

**Encrypted-QR people:** `.venv/bin/python scripts/run_tests.py --encrypted 10` builds 10 genuine people whose card
QR is signed **and** AES-256-GCM encrypted (`TID3`), then runs them through the same flow. **Proper:** `10/10 passed`
(each REVIEW: genuine, but scripted stills can't pass the live head-turn). Scanning one of those cards with a phone
shows only `TID3|...` ciphertext: no name, date or ID.

**Not proper:** any `FAIL` line. The worst failures are a genuine applicant (01/02) getting REJECT, or any fraud
scenario getting APPROVE. Exit code 1 means at least one failed.

## 2. Manual browser test with the test kit (no camera needed)

Sign in to `/dashboard` with the analyst key first, then create a kit:

```bash
curl -s -X POST -H "X-Analyst-Key: $(cat backend/.secrets/analyst_key)" localhost:8000/api/testkit | python3 -c "import json,sys; print(json.load(sys.stdin)['folder'])"
```

Open the printed folder: one `_card.jpg` + `_selfie.jpg` per scenario and **`MANUAL.md`** with the exact form values.
For each scenario: open `/kyc`, tick consent, **type** the values, upload the card, and at the selfie step use
**"No camera? Upload a selfie"**.

**Proper (manual):** fraud scenarios still REJECT, but 01 and 02 come out **REVIEW**, not APPROVE: an uploaded photo
gives the server no liveness evidence (NOT_PROVIDED), and the system never approves without it. The applicant sees
"We need a quick live face check".

Use each identity once. From the same browser, the third different person you submit within a week is held as
possible mule herding (one device, several people). That is the check working; use a private window or another
browser profile for a fresh device.

## 3. Live webcam test (the real demo path)

1. Open `/kyc?demo=1` and upload a clear front-facing photo of **yourself** in the Presenter kit.
2. **Genuine card:** type the values shown, then on the face step turn your head in the order shown (the browser
   records a short burst). A smooth live turn → **APPROVE**. Holding a phone photo to the camera → REVIEW (`BIO_NO_MOTION`).
3. **Hero DOB edit card:** DOB `14/03/1994` → **REJECT**, "Tampered document", `DOC_QR_OCR_MISMATCH`.
4. **Frankenstein card:** victim's details → **REJECT**, `BIO_REGISTRY_FACE_MISMATCH` plus `BIO_FACE_REUSED`
   (your face already applied under your name in step 2).

Do it in this order. Sit alone in the frame with your face lit from the front.

**Not proper:**
- Genuine lands in REVIEW with `BIO_LIVENESS_FAIL`: you did not turn far enough, or another face was in a frame.
  Retry (better light, one face only, a clear turn each way).
- Genuine lands in REVIEW with `BIO_CHALLENGE_INVALID`: the challenge expired (over 3 minutes) or was reused; start again.
- Genuine lands in REVIEW with `BIO_CARD_FACE_MISMATCH`: your enrolment photo and webcam face differ too much
  (old photo, glasses, angle). Rebuild the kit with a clearer photo.
- Submit shows "Load failed": the backend is down. Check `curl localhost:8000/api/health`.
- The progress page stays on "Checking your application" for more than 20 s: the first run loads models (about 6 s);
  if it persists, check the backend log.
- "Our checks are busy right now": more than 4 checks are running at once; wait a few seconds.

## 4. Analyst console checks

| Page | Proper |
|---|---|
| Queue `/dashboard` | Your test cases at the top with the bands from above; filters and search work |
| Sign-in | `/dashboard` asks for the analyst key; a wrong key is refused; the sign-out button returns to the sign-in screen |
| Case page | **Required evidence** panel lists every check with passed / failed / could not check / not provided; five module cards with reason codes; QR vs printed vs form table highlights the edited DOB in red for 04; face panel shows liveness head-turn deltas and frame similarity |
| Case page, analyst decision | Approving a REJECT case asks for a second analyst (sign in from another browser to confirm); audit entries show a short hash |
| Identity graph | **Fraud Ring Simulator** adds 8 linked applicants; the new cluster appears highlighted |
| Metrics | Provenance box says what the numbers are measured on (model probability vs policy bands), the commit, and 95% intervals; ablation bars show every single module below "fused" |
| Attack Lab | Charts load; **Run attack** with "Poisson DOB edit" shows `DOC_QR_OCR_MISMATCH` after, nothing before |
| Investigator | "Why are RS... and RS... linked?" lists face, device, email-stem and keystroke links |
| Case page, **TruFor** tab | Heatmap + score in about a second (the model preloads at startup). On a DOB-edited card it lights the photo and misses the date: expected, that is the point |
| Case page, **Erase applicant data** | Record, images and graph entry deleted; the queue no longer shows it |
| Applicant result page | Plain message and next step only; switch on "Technical details" to see codes and scores |

## Resetting

`.venv/bin/python eval/seed_db.py` wipes all live/test applications and the live graph log, then restart the
backend. Registry enrolments from kits remain (harmless).
