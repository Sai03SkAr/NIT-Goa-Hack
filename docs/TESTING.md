# Testing TrueID Shield

Three levels, fastest first. Backend must be running (`./scripts/run_backend.sh`, port 8000) and the frontend
(`cd frontend && npm run dev`, port 3000 or 3001).

## 1. Automated acceptance test (2 minutes, no camera)

```bash
.venv/bin/python scripts/run_tests.py
```

It builds a **fresh** test kit (new people the system has never seen, enrolled in the mock registries), submits
every scenario through `/api/apply` exactly like the browser, and checks the decision.

**Proper:** `14/14 passed`. A report is written to `data/generated/testkit/<tag>/REPORT.md`.

| Scenario | Expected | What must happen |
|---|---|---|
| 01 Genuine applicant | APPROVE | Nothing fires |
| 02 Name written with an initial (`R. Kulkarni`) | APPROVE | Fuzzy Indian-name match accepts it |
| 03 Liveness challenge failed | REVIEW | `BIO_LIVENESS_FAIL`; never auto-rejected |
| 04 DOB edited on the card (hero attack) | REJECT | `DOC_QR_OCR_MISMATCH` |
| 05 Counterfeit card (QR signed by a fake key) | REJECT | `DOC_QR_SIG_INVALID`, pattern "Tampered document" |
| 06 Stolen ID + someone else's face | REJECT | `BIO_REGISTRY_FACE_MISMATCH`, `REG_SIM_NEW` |
| 07 Fabricated identity (no QR, unissued ID) | REJECT/REVIEW | `REG_ID_NOT_FOUND`, `DOC_QR_MISSING` |
| 08 Someone else at the camera | REVIEW or REJECT | `BIO_CARD_FACE_MISMATCH`; must never APPROVE |
| 09 ID number with a wrong digit | REJECT/REVIEW | `DOC_CHECKSUM_FAIL` |
| 10 Virtual camera (deepfake injection) | REJECT | `BIO_VIRTUAL_CAMERA` |
| 11 Scripted bot | REJECT/REVIEW | `BEH_FAST_FILL`, `BEH_PASTE_HEAVY`, `BEH_ROBOTIC_TIMING` |
| 12 Ring members 1–3 | REJECT | Members 2–3 show `BEH_EMAIL_SEQUENCE`, `BEH_KEYSTROKE_LINK`, `BIO_FACE_REUSED`, pattern "Synthetic ring" |

Ring member 1 is labelled "Frankenstein": the ring is only visible once a second member arrives. That is correct.

**Not proper:** any `FAIL` line. The worst failures are a genuine applicant (01/02) getting REJECT, or any fraud
scenario getting APPROVE. Exit code 1 means at least one failed.

## 2. Manual browser test with the test kit (no camera needed)

```bash
curl -s -X POST localhost:8000/api/testkit | python3 -c "import json,sys; print(json.load(sys.stdin)['folder'])"
```

Open the printed folder: one `_card.jpg` + `_selfie.jpg` per scenario and **`MANUAL.md`** with the exact form values.
For each scenario: open `/kyc`, tick consent, **type** the values, upload the card, and at the selfie step use
**"No camera? Upload a selfie"**.

**Proper (manual):** same as the table above **except** 01 and 02 come out **REVIEW**, not APPROVE. Uploading a
photo skips the live liveness challenge, and the system never auto-approves without one. Fraud scenarios still REJECT.

Use each identity once. Submitting the same identity again adds velocity signals (same phone/device in 24 h)
and is no longer the scenario described.

## 3. Live webcam test (the real demo path)

1. Open `/kyc?demo=1` and upload a clear front-facing photo of **yourself** in the Presenter kit.
2. **Genuine card:** type the values shown, do the two liveness challenges on camera, submit → **APPROVE**.
3. **Hero DOB edit card:** DOB `14/03/1994` → **REJECT**, "Tampered document", `DOC_QR_OCR_MISMATCH`.
4. **Frankenstein card:** victim's details → **REJECT**, `BIO_REGISTRY_FACE_MISMATCH` plus `BIO_FACE_REUSED`
   (your face already applied under your name in step 2).

Do it in this order. Sit alone in the frame with your face lit from the front.

**Not proper:**
- Genuine lands in REVIEW with `BIO_LIVENESS_FAIL`: retry the challenge (better light, one face only).
- Genuine lands in REVIEW with `BIO_CARD_FACE_MISMATCH`: your enrolment photo and webcam face differ too much
  (old photo, glasses, angle). Rebuild the kit with a clearer photo.
- Submit shows "Load failed": the backend is down. Check `curl localhost:8000/api/health`.
- The pipeline page stays on "Agents are working..." for more than 20 s: the first run loads models (about 6 s);
  if it persists, check `logs/backend.log`.

## 4. Analyst console checks

| Page | Proper |
|---|---|
| Queue `/dashboard` | Your test cases at the top with the bands from above; filters and search work |
| Case page | Five module cards with reason codes; QR vs printed vs form table highlights the edited DOB in red for 04; face trio shows the mismatch for 06/08 |
| Identity graph | **Fraud Ring Simulator** adds 8 linked applicants; the new cluster appears highlighted |
| Metrics | ROC-AUC ≈ 0.996, recall 100%, ablation bars show every single module below "fused" |
| Attack Lab | Charts load; **Run attack** with "Poisson DOB edit" shows `DOC_QR_OCR_MISMATCH` after, nothing before |
| Investigator | "Why are RS... and RS... linked?" lists face, device, email-stem and keystroke links |
| Case page, **TruFor** tab | Heatmap + score in about a second (the model preloads at startup). On a DOB-edited card it lights the photo and misses the date: expected, that is the point |
| Case page, **Erase applicant data** | Record, images and graph entry deleted; the queue no longer shows it |
| Applicant result page | Plain message and next step only; switch on "Technical details" to see codes and scores |

## Resetting

`.venv/bin/python eval/seed_db.py` wipes all live/test applications and the live graph log, then restart the
backend. Registry enrolments from kits remain (harmless).
