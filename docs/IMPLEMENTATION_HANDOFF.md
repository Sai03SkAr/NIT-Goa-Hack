# TrueID Shield: detailed remediation and implementation handoff

**Project:** Hacksploit 2026, PS3 — Synthetic Identity Fraud Detection in Automated KYC Systems  
**Prepared:** 28 October 2026, India Standard Time  
**Reviewed baseline:** `013aec8` on `main`; the backend findings were originally inspected at `cf32985`. The newer commit changes the frontend/design and does not remediate these backend findings.  
**Audience:** The developer implementing the fixes, the teammate validating them, and the presenter explaining the system.

## 1. Read this first

This is an implementation plan, not a record of completed fixes. No application source fixes have been implemented as part of this handoff.

The project already has useful components: signed specimen documents, OCR, face comparison, mock registry validation, behavior features, a cross-application graph, a fusion model, an analyst console, and evaluation scripts. Preserve those components and the latest institutional UI. The work below makes their security boundaries, decisions, evidence, and evaluation consistent.

The hackathon asks for a **simulation**, and explicitly permits simulated biometric signals. It does not require production banking infrastructure, direct UIDAI access, a commercial identity provider, or discovering a bank vulnerability. Keep external integrations mocked unless a legitimate integration is separately provided. Use fictional SPECIMEN documents and consented or appropriately licensed media.

The central implementation rule is:

> APPROVE requires sufficient verified evidence. Missing, contradictory, expired, or merely simulated evidence cannot be treated as a successful independent check.

The second rule is:

> Keep model probability, evidence sufficiency, policy decision, analyst disposition, and known ground truth separate.

An identity graph link is not proof of crime. A virtual-camera label is not proof of a deepfake. A failed camera challenge is not proof of fraud. A valid document signature does not establish that the person presenting it owns that identity.

### 1.1 What was actually verified during the review

- Source review covered the API, pipeline, document module, biometric module, registries, behavior, correlation, database, frontend capture flow, and evaluation code.
- Isolated function checks reproduced the biometric assessor treating absent server frame results as consistent when client liveness was claimed.
- An isolated fusion check reproduced a simulated voice score changing `0.31 / REVIEW` to approximately `0.158 / APPROVE`.
- Isolated hard-rule checks returned no mandatory review for missing face similarities, inconsistent frames, identifier inconsistencies, and an identity absent from the registry.
- These hard-rule results do **not** prove that the trained full pipeline would approve those inputs. The model could still flag them. The confirmed defect is that the mandatory evidence floor is absent.
- Full acceptance tests could not run: the backend was offline, generated dataset/model artifacts were absent, and key runtime dependencies were initially missing. Do not represent the README's historical metrics as independently reproduced.

### 1.2 Development order and priorities

| Stage | Priority | Outcome | Depends on |
|---|---|---|---|
| A | P0 | Characterization tests, isolated test storage, safe configuration | Nothing |
| B | P0 | Evidence contract and shared decision policy | A |
| C | P0 | Server-owned liveness session and identity binding | B |
| D | P0 | Simulated voice removed from real decision adjustment | B |
| E | P0 | Authentication, evidence access, demo isolation | A |
| F | P1 | Complete document/registry identity linkage | B |
| G | P1 | Validated inputs, bounded jobs, trusted telemetry handling | A, C, E |
| H | P1 | Honest document-forgery evaluation and robust capture handling | F |
| I | P1 | Consistent, reproducible evaluation and holdouts | B–H |
| J | P1 | Full integration, browser QA, documentation, demo rehearsal | All |

Treat P0 as the minimum before claiming that the simulator prevents approvals with invalid evidence. P1 is still required for the complete handoff; it is not optional polishing.

## 2. Problem-statement acceptance map

| Mandatory deliverable | Existing implementation | Required completion evidence |
|---|---|---|
| Synthetic identity detection using multi-source correlation | Five module outputs combined with history/graph features | Show a mixed-attribute identity caught by contradictions; show linked applications; show benign shared-household counterexamples |
| AI-generated document forgery detection | QR integrity, OCR comparison, heuristic image forensics; inactive TruFor adapter | Real labeled evaluation on generated/edited specimen documents; distinguish authenticity checking from image-manipulation detection |
| Behavioral patterns across applications | Velocity windows, email sequences, typing links, IsolationForest | Use server-derived network/session observations; mark client telemetry untrusted; test missing telemetry and benign automation |
| Biometric signals; simulation allowed | Face matching/reuse, browser challenge, server pose checks, simulated voice | Fresh challenge validation, frame-to-selfie binding, missing-face review, clear real/simulated/proxy status |
| Adversarial robustness evaluation | Image perturbations, DOB edits, behavioral feature perturbation | Add missing-evidence, replay, session-binding, API authorization, quality degradation, and unseen-forgery tests |
| End-to-end KYC simulation | Applicant wizard → LangGraph → analyst console | Authenticated review, controlled evidence access, consistent final decisions, reliable progress/reconnect behavior |
| Precision, recall, fraud detection rate | Existing training/evaluation scripts | Regenerated results with policy parity, provenance, honest split definitions, per-family results, review workload and uncertainty |

## 3. Stage A — prepare a safe, reproducible implementation environment

### 3.1 Preserve the current baseline

1. Start from `013aec8` or a newer explicitly reviewed commit. Check `git status` before changing anything.
2. Create a branch such as `codex/kyc-evidence-hardening` or the team's chosen branch.
3. Read any `AGENTS.md` added after this handoff before implementing.
4. Preserve the updated light UI. Avoid unrelated redesigns or wholesale rewrites.
5. Add regression tests before changing the defective functions so the failures are reproducible.
6. Never run destructive seeding/reset scripts against the only copy of demonstration evidence.

### 3.2 Add configuration for isolated storage

Current storage locations are fixed under `backend/`, `data/generated/`, and `models/`. Make the root configurable for tests.

Proposed settings:

```text
TRUEID_MODE=local_demo|test|restricted
TRUEID_DATA_DIR=<absolute directory>
TRUEID_DB_PATH=<absolute database path>
TRUEID_ENABLE_DEMO_TOOLS=false
TRUEID_ANALYST_KEY=<secret, server-side only>
TRUEID_SESSION_SECRET=<independent random secret>
TRUEID_HMAC_KEY=<independent random secret>
TRUEID_TRUST_PROXY=false
TRUEID_TRUSTED_PROXY_IPS=<explicit addresses if used>
TRUEID_MAX_UPLOAD_BYTES=<documented limit>
TRUEID_MAX_IMAGE_PIXELS=<documented limit>
TRUEID_MAX_FRAMES=<documented limit>
TRUEID_MAX_ACTIVE_JOBS=<documented limit>
```

Use a typed settings object and validate it at startup. Missing secrets must not silently become predictable defaults in restricted mode. For local demo mode, a generated local secret may be persisted outside served directories with appropriate permissions. Never put analyst credentials into a `NEXT_PUBLIC_*` environment variable.

Create a sample configuration file with placeholders and document PowerShell and Bash startup steps. Ignore actual secret files in Git. Record exact library versions used for successful tests in the project's dependency constraints or lockfiles.

### 3.3 Initial tests

Add `backend/tests/` with a temporary database, temporary uploads, temporary registries, and mocked face/OCR/model adapters. Unit tests should not download models, require a webcam, or call external services.

Keep a separate opt-in integration suite for real installed OCR and face models. Tests using mocked adapters must explicitly say so; they validate policy and wiring, not biometric accuracy.

## 4. Stage B — define evidence and a single decision policy

### 4.1 Files to change

- `backend/app/schemas.py`
- `backend/app/fusion/model.py`
- `backend/app/graph/pipeline.py`
- `backend/app/fusion/fraud_type.py`
- `backend/app/db.py`
- All five module agents where they emit evidence
- Proposed new file: `backend/app/policy.py`

### 4.2 Separate evidence status from risk

Add explicit statuses rather than encoding every situation as a number:

```text
PASS          The configured check completed successfully.
FAIL          The configured check completed and found a contradiction/failure.
UNAVAILABLE   The source/model/service could not complete.
NOT_PROVIDED  Required input was absent.
SIMULATED     An explicitly simulated signal; not independent real evidence.
```

Recommended evidence fields:

```text
check_id, status, source, simulated, verified_at,
session_id, reason_codes, quality, adapter_version
```

`source` should distinguish server measurements, mock registries, client assertions, and trusted imported test fixtures. Server measurements can still have model error; do not label them infallible.

Use finite-value validation for numeric features. Preserve missing values as missing; never convert a failed similarity extraction into a perfect match or zero risk. Validate booleans strictly where coercing a string could be misleading.

### 4.3 Implement an approval eligibility gate

Implement a pure function, independent of XGBoost, with a stable output:

```text
evaluate_policy(features, evidence, model_result, policy_version)
  -> decision_band, rule_codes, approval_eligible, unresolved_checks
```

Order of operations:

1. Validate schema and numeric integrity.
2. Check required evidence and source availability.
3. Apply high-confidence contradiction rules.
4. Establish whether automatic approval is allowed.
5. Apply the calibrated model's risk bands where eligible.
6. Produce a decision and reason codes without modifying the model probability.

Example expected behavior:

| Condition | Minimum decision | Why |
|---|---|---|
| No detected selfie or document portrait | REVIEW | Identity binding is incomplete |
| Missing/non-finite required face similarity | REVIEW | Missing data is not a match |
| Missing, expired, or failed server challenge | REVIEW | Liveness requirement incomplete |
| Frame identity differs from submitted selfie | REVIEW or stronger policy action | Evidence does not belong to one applicant |
| Issuer registry unavailable | REVIEW | Unavailable is distinct from not found |
| Identity not found in the configured mock issuer registry | REVIEW at minimum | No positive identity corroboration |
| Readable, structurally valid signed specimen QR has invalid signature | REJECT submitted evidence, under documented demo policy | Verified evidence-integrity failure |
| Confident OCR disagrees with valid signed identifier/name/DOB | REJECT submitted evidence or REVIEW, as documented | Evidence contradiction |
| OCR unreadable or confidence inadequate | REVIEW / request recapture | Extraction uncertainty is not proven forgery |
| Checksum/format invalid | REVIEW / request correction | User entry error is possible |
| New SIM, thin credit file, shared address/IP | No automatic rejection alone | Weak contextual evidence |
| Model missing or incompatible | REVIEW; model unavailable status | No validated score available |

The team may retain some existing specimen-specific rejection policies, but document them as demo policy. Do not imply that all banks should reject a person for an OCR error, camera configuration, or checksum typo.

### 4.4 Fix the missing-face and frame gaps

In `hard_rules()` or its replacement:

- Check `bio_selfie_found` and `bio_card_found` explicitly.
- Check required similarities with `math.isfinite` or equivalent before threshold comparisons.
- Treat absent or non-finite values as incomplete evidence.
- Check server frame verification status, not only the client's liveness flag.
- Check mandatory document and registry contradictions, including identifier binding.
- Default new/missing evidence fields to incomplete, not successful.

### 4.5 Model availability and score semantics

The current model fallback averages module risks when trained artifacts are absent. Remove silent equivalence between this heuristic and a calibrated fraud probability.

Acceptable design:

- Return `model_status=unavailable` and no calibrated probability.
- Keep module risk summaries visible.
- Force REVIEW when the configured model is required for approval.
- Optionally expose a separately labeled heuristic score in local demo mode.
- Add artifact metadata: feature schema version, training run ID, data version, decision-policy version, and calibration version.
- Reject incompatible/stale model artifacts instead of silently using mismatched features.

### 4.6 Correct fraud-type claims

Current `fraud_type.classify()` maps a failed liveness flag to injection. That overstates the evidence.

Add an `inconclusive` or `verification_incomplete` category. A camera failure or missing face should not be described as a proven injection attack. Likewise, a client-reported virtual-camera label is a suspicion signal rather than forensic proof.

Keep classification separate from risk decision: an application may need review while no fraud family can be established.

### 4.7 Required tests

- Missing selfie, missing card portrait, missing registry portrait, and NaN/Infinity similarities cannot APPROVE.
- Failed/incomplete frame verification cannot APPROVE even when the model returns very low risk.
- Low-confidence OCR is distinguished from a confident contradiction.
- Weak behavioral features alone do not become mandatory rejection rules.
- A forced REVIEW cannot be downgraded by fusion or later summary/step-up code.
- Unavailable model cannot produce an unlabeled calibrated probability.
- Error messages and reason codes accurately describe incomplete evidence.

## 5. Stage C — server-owned liveness and session binding

### 5.1 Current defects

- Browser `pickChallenges()` chooses the challenges.
- `/api/apply` accepts client `passed` and optional frames.
- Biometric assessment defaults missing `frames_consistent` to true.
- `verify_frames()` checks similarity among frames and yaw spread, but not their identity against the submitted selfie.
- No server-owned challenge expiry or one-time consumption binds the sequence to a current submission.
- Selecting the largest detected face hides whether multiple faces were present.

### 5.2 Files to change

- `backend/app/main.py`
- `backend/app/modules/biometric/agent.py`
- `backend/app/modules/biometric/face.py`
- `backend/app/graph/pipeline.py`
- `frontend/lib/liveness.ts`
- `frontend/app/kyc/page.tsx`
- Proposed new file: `backend/app/liveness_sessions.py`

### 5.3 Proposed protocol

1. Applicant opens a server-created enrollment session. Return an opaque random session identifier through a secure cookie or scoped capability.
2. After form and document are selected, request a liveness challenge from the backend.
3. Server generates an unpredictable challenge ID and challenge sequence with issuance and expiry times.
4. Bind the challenge to the enrollment session and a digest of the canonical submitted form/document. Use a server-side canonicalization function, not an undocumented client serialization assumption.
5. Browser displays the exact issued sequence. It must not substitute a new locally generated sequence.
6. Capture a neutral baseline and the evidence needed for each supported challenge.
7. Submit challenge ID, ordered media, and application evidence through the bound session.
8. Atomically check session ownership, expiry, unused status, and evidence binding. Prevent two concurrent submissions from both consuming the same challenge.
9. Verify the submitted media server-side. The client's `passed` value may be retained as diagnostic information only.
10. Mark challenge consumed and persist verification outcome/version.

A single in-memory store is acceptable for a one-process localhost hackathon, with a documented restart limitation. A multi-worker deployment needs a shared transactional store. On server restart, fail closed and request a new challenge.

### 5.4 Server verification requirements

- Exact expected frame/clip structure; reject excessive media.
- Exactly one usable face per required frame; record detection quality.
- All required frames match one identity.
- That identity also matches the submitted selfie using a separately validated frame-binding threshold.
- Verify the requested movements in their correct sequence, using the appropriate detector.
- Validate left/right conventions against real camera samples; do not guess pose sign or reuse uncalibrated thresholds.
- Verify neutral-to-action transitions rather than merely observing a spread of poses.
- If blink/smile verification is unavailable server-side, do not claim to verify it. Initially restrict to actions the backend can actually assess, or add a validated temporal landmark adapter.
- Failed or incomplete evidence leads to review/recapture, not a fraud accusation.

**Limitation:** Server-issued challenges and frame binding improve freshness and consistency. They do not establish a cryptographically trusted camera, defeat every real-time deepfake, or prove that uploaded pixels came from a physical sensor. If sensor attestation is absent, state that explicitly. Do not turn a nonce into a claim of complete replay resistance.

### 5.5 Virtual-camera handling

Retain camera labels only as untrusted client hints. Do not equate hiding the label with passing an integrity test. An installed virtual camera should not penalize use of a different camera. An active reported virtual camera can request additional review under demo policy; it is not conclusive fraud evidence.

### 5.6 Frontend behavior

- Obtain fresh challenges on retry; never reuse an expired/consumed challenge.
- Disable submission while upload is active; avoid duplicate jobs.
- Stop camera tracks when leaving the step or completing submission.
- Explain camera failures and provide a review-only upload fallback.
- Replace claims such as “a replayed video can't follow instructions” and “physical camera (no injection tool)” with accurate descriptions of what was measured.
- Show an actionable expired-session error and a button to restart verification.

### 5.7 Required tests

| Test | Expected |
|---|---|
| Client claims success, no frames | REVIEW |
| Missing/wrong session capability | Deny use of the session |
| Expired challenge | Cannot satisfy liveness; request fresh challenge |
| Reused challenge | Second consumption denied |
| Concurrent challenge consumption | At most one successful consumption |
| Challenge issued for another applicant/session | Denied |
| Form/document changed after challenge binding | Challenge invalid; recapture |
| Frames match each other but not selfie | Cannot APPROVE |
| Required frame contains two faces | Review/recapture |
| Invalid ordering or wrong movement | Cannot claim successful challenge |
| Old static frames | Fail the supported temporal checks |
| Real-time manipulated footage | Report measured result; no blanket guarantee |

## 6. Stage D — remove simulated evidence from real decision adjustment

### Files

- `backend/app/graph/pipeline.py`: `fusion_node`, `route`, `step_up_node`
- `backend/app/modules/biometric/agent.py`: `simulated_voice`
- `frontend/app/kyc/progress/[id]/page.tsx`
- `backend/app/db.py`, summaries, API types

### Implementation

1. Remove the log-odds adjustment driven by `step_up.voice` from ordinary decisions.
2. Preserve voice/fingerprint simulation as an optional demonstrator with `simulated=true`.
3. Keep the base model probability unchanged; show simulation output in a separate UI field.
4. A simulated check cannot satisfy a required real check or overturn an evidence floor.
5. A REVIEW should remain REVIEW until a configured real step-up or authenticated analyst action resolves it.
6. If a future actual voice service is added, version and evaluate it separately; do not reuse simulation thresholds.

### Acceptance

- The known `0.31 / REVIEW` fixture stays REVIEW regardless of simulated voice score.
- Running with simulation on/off produces identical ordinary decisions.
- UI explicitly states “simulated; does not change approval.”
- Offline evaluation and live execution use the same shared decision function.

## 7. Stage E — authentication, authorization, demo isolation, and evidence privacy

### 7.1 Route policy

Implement authorization in backend dependencies or middleware with deny-by-default coverage, not only by hiding frontend buttons.

| Route group | Access policy |
|---|---|
| Minimal health/readiness | Public; no applicant counts or sensitive internals |
| Start enrollment / issue challenge / apply | Scoped applicant session; validation, quotas, consent |
| Applicant progress/result | Only that applicant's session/capability; minimal response |
| Analyst queue, case details, graph, chat, internal config | Authenticated analyst |
| Analyst override and threshold changes | Authenticated authorized role; CSRF protection; audit |
| Document/selfie/registry portraits/ELA | Authorized case access; never globally public |
| Public metrics | Sanitized aggregate export only; no personal evidence or internal paths |
| `/mock/*` | Disabled externally or analyst/demo-only; never public identity enumeration |
| `/api/testkit`, `/api/demo/kit`, `/api/ring-sim`, `/api/attack/live` | Explicit demo mode AND authorized operator |

### 7.2 Analyst authentication

For hackathon scope, a server-configured analyst key exchanged for an expiring server-managed session is sufficient. Use a proper account system later if multiple roles/users are required.

- Do not hard-code credentials or expose them in browser bundles.
- Use an opaque random session token, stored server-side as a digest, or a correctly signed expiring session.
- Prefer `HttpOnly`, `SameSite` cookies; use `Secure` with HTTPS and document the localhost development exception.
- Add login throttling, expiry, logout/revocation, and constant-time credential comparison where relevant.
- Derive audit actor identity from the authenticated principal; ignore client `actor` fields.
- Mutating cookie-authenticated operations need explicit CSRF protection and validated origins. CORS alone is not authorization or CSRF protection.
- Do not trust forwarded identity/authentication headers sent by a caller.
- For programmatic tests, use a documented scoped credential mechanism; never a hidden test bypass in public application submission.

Add a sign-in gate in `frontend/app/dashboard/layout.tsx` or a dedicated component. Include visible labels, password-manager support, paste support, loading/error states, and logout. Never put secrets in URLs or localStorage.

### 7.3 Protect evidence without breaking images and SSE

Current `StaticFiles` mounts expose the generated-data directory and uploads through `/files` and `/uploads`. Merely requiring unguessable filenames is insufficient; the generated directory also holds JSON manifests and registry data.

Replace broad static mounts with narrow authorized handlers:

- Resolve an artifact from an application record, not an arbitrary user-supplied filesystem path.
- Check applicant/analyst permission before reading it.
- Resolve paths and enforce containment within the allowed storage directory; block traversal and symlink escapes.
- Return correct media types and `Cache-Control: private, no-store` for sensitive responses.
- Serve only a small allowlisted set of intentionally public specimen/demo assets separately.
- Use same-origin authenticated cookies or a short-lived scoped mechanism compatible with `<img>` and `EventSource`; do not assume those APIs can attach arbitrary authorization headers.
- Do not put long-lived bearer tokens in image or SSE URLs. If short-lived signed URLs are necessary, narrowly scope, expire, and redact them from logs.
- If SSE reconnect is supported, authenticate every reconnect and preserve event ordering.

Update `frontend/lib/api.ts`, `frontend/next.config.ts`, `frontend/components/Evidence.tsx`, case images, presenter-kit fetches, and progress streaming together. The public landing page currently reads `/api/metrics`; preserve a sanitized public metrics endpoint or update that component deliberately.

### 7.4 Isolate demo registry writes

`build_testkit()` and `build_kit()` enroll data into the mock registries used by verification. Preserve this useful demo capability behind a boundary:

- Demo mutation endpoints disabled by default.
- Separate demo/test data roots and databases from restricted mode.
- Explicit operator authentication even when enabled.
- Mark enrolled identities and resulting cases with a demo provenance field.
- Never allow client `source` to select a privileged validation mode.
- Review production/restricted startup configuration and fail if dangerous demo writes are enabled unintentionally.

### 7.5 Privacy and persistence

The database's masked-form field does not mean all stored evidence is masked. Module evidence contains OCR/registry attributes, images contain identity details, and `LIVE_HISTORY` writes the raw form and embedding.

- Inventory every stored field and artifact.
- Store only fields required for replay/correlation. Use keyed identifiers where full identifiers are unnecessary.
- Move history and private issuer keys outside all web-served directories.
- Replace the hard-coded HMAC key with a secret; document that key rotation changes linkage and requires migration/re-indexing.
- Add retention and deletion commands covering database records, media, history, exports, and graph indexes.
- Make deletion/rebuild behavior consistent; an in-memory face index must not retain an otherwise deleted identity.
- Explain whether raw identifiers are retained for the local demo. Do not claim “only hashes stored” while retaining raw values elsewhere.
- Avoid logging form data, biometrics, credentials, capabilities, or full provider payloads.

## 8. Stage F — complete document and registry linkage

### 8.1 Signed specimen payload

Files: `modules/document/qr_sign.py`, `card.py`, `agent.py`, `schemas.py`, `data/gen_population.py`, `demo_kit.py`, `testkit.py`.

The current signed payload contains `n`, `d`, `g`, `l4`, and `i`. Last-four identity linkage is insufficient to uniquely bind a specimen document to its full identity.

Plan:

1. Version the specimen QR schema.
2. Add a full fictional issuer subject ID or a server-verifiable commitment to the complete specimen identifier. Specify exactly how commitment encoding/canonicalization works.
3. Validate decoded type, required keys, field lengths, dates, version, encoding, and signature size before using `.get()` or indexing fields.
4. Distinguish malformed QR, unreadable QR, untrusted issuer, invalid signature, and valid supported payload.
5. Check all supported signed fields against OCR/form, with OCR-quality gating.
6. Explicitly enforce `doc_qr_ocr_id4` and `doc_form_id` while old fixtures remain, then migrate to stronger subject binding.
7. Check gender/issue date if included in the claimed three-way consistency. If unsupported, state that rather than implying full coverage.
8. Regenerate signed fixtures and invalidate old incompatible model/features artifacts.

Keep this a **fictional issuer** format. Do not label Ed25519 specimen QR verification as implementation of real Aadhaar Secure QR verification.

### 8.2 Key separation

The verifier currently derives its public key through the issuer's private-key function. Separate roles:

- Issuer/generator requires private signing material.
- Verifier loads an allowlisted public key/key ID only.
- Verification must not generate a new issuer private key when a key is missing.
- Missing configured verifier keys means unavailable verification, not implicit new trust.
- Test keys and fixtures stay separate from developer/local demo signing keys.
- Rotation uses explicit key IDs and validity policy.

### 8.3 Mock PAN and registry relationship

Files: `modules/registry/agent.py`, `mocks.py`, generators and test kits.

1. Add full mock issuer subject linkage to PAN records.
2. Check the full relationship, plus compatible name and DOB.
3. Add reason codes distinguishing subject mismatch, name mismatch, DOB mismatch, unavailable source, and not found.
4. Treat registry outages differently from negative lookup results.
5. Preserve Indian-name normalization and known benign variations with explicit tests.
6. Normalize dates through parsed values rather than arbitrary formatting assumptions.
7. If a later snapshot is used for historical evaluation, either reconstruct records as of application time or label the limitation. Do not silently imply the current snapshot was available historically.

### Required fixtures

- Two identities sharing the same last four identifier digits but different full subject IDs.
- PAN linked to identity A, submitted by identity B with colliding suffix.
- Signed QR for one specimen identifier and visible/form identifier for another.
- Name/DOB contradictions, valid initial expansion, supported transliteration, unreadable OCR.
- Valid signatures with malformed/unsupported payload schemas.
- Missing verification key and an explicitly untrusted signer.

## 9. Stage G — inputs, telemetry, jobs, and graph integrity

### 9.1 Typed application input

Replace raw `json.loads(payload)` plus a few truthiness checks with Pydantic request models and controlled error responses.

- Required form strings: trim, maximum lengths, supported date parsing, identifier length, email/phone boundaries.
- For a fictional dataset, validate formats as specimen formats, not claims of government issuance.
- Telemetry: finite numeric ranges, allowed counters, exactly sized keystroke vectors, bounded labels, valid collections.
- Reject type confusion, arbitrary nested data, and oversized JSON before expensive work.
- Handle malformed JSON as 4xx without an internal traceback.
- Capture consent version and server timestamp as part of enrollment, not just a checkbox step that the API never receives.
- Server assigns `source`, creation time, job ID, actor, and final status.

### 9.2 Upload handling

- Enforce per-file byte limits, total body limit, maximum pixel count/dimensions, and frame count.
- Validate actual decoded image content; MIME and filename are not trustworthy.
- Reject corrupt/decompression-heavy inputs before model inference.
- Normalize accepted media into a controlled format.
- Decode and validate before writing final files; clean up partial uploads and failed jobs.
- Use unpredictable collision-resistant artifact IDs and restrictive storage permissions.
- Bound processing time and provide a useful recapture/retry response.

### 9.3 Network/device/behavior trust

The current browser payload does not send an IP, while the server accepts a caller-supplied `device.ip` if provided.

- Derive network address from the actual request peer.
- If using Next as a reverse proxy, explicitly configure trusted proxy addresses and header handling; never trust arbitrary `X-Forwarded-For` from callers.
- Test spoofed forwarded headers and direct backend access.
- Establish a server-issued session/device cookie for continuity. A browser fingerprint can remain an additional weak hint.
- Record client telemetry as client asserted; do not claim that it proves typing behavior.
- Missing telemetry must not get a fabricated clean human default. Emit unavailable status and use the documented policy.
- Add server timing and endpoint-volume observations for useful independent signals.
- Keep accessibility tools, password managers, shared hostel networks, families, fast typists, and new-to-credit applicants in hard-negative tests.

### 9.4 Bounded jobs and progress

Current implementation starts a thread per application and stores queues in a process-global dictionary.

Implement:

- Bounded executor/semaphore and explicit job admission limits.
- Per-session/network quotas appropriate to localhost demonstration; do not make IP alone an identity.
- TTL and cleanup for completed, abandoned, and failed jobs.
- A small event log with monotonic IDs if reconnect/replay is supported. Avoid two subscribers consuming a shared queue and stealing events from each other.
- A terminal event for success/failure and a persisted job state.
- Explicit frontend error state and retry/reconnect behavior; do not leave “agents are working” indefinitely.
- Sanitized applicant errors; detailed internal traces only in restricted logs.
- Idempotency for duplicate application submission in the same enrollment session.

### 9.5 Graph/history consistency and poisoning resistance

The correlation node mutates global history before final persistence. Other nodes read history without the same lock. Failed or rejected applications can still carry valuable fraud signals, but should not become equivalent to verified identities.

Plan:

1. Separate an observed-attempt history from verified identity facts.
2. Preserve rejected attempts for velocity/link evidence with trust labels.
3. Never let unverified submitted attributes overwrite registry truth.
4. Use a consistent history snapshot for each assessment, or serialize the relevant read/commit transaction.
5. Atomically persist the application and a replayable history event, or use an outbox/reconciliation pattern suitable to SQLite.
6. Replay events idempotently and skip already indexed IDs.
7. Handle truncated final JSONL records/corrupt history predictably if JSONL remains; do not make one bad line prevent startup.
8. Ensure every temporal query excludes future records, including face/keystroke/graph queries—not just velocity windows.
9. Re-score earlier linked cases or explicitly show that their decision is historical when later evidence reveals a ring.
10. Test same-name/different-person and changed-name/same-person cases; names are not stable unique identifiers.

## 10. Stage H — document-forgery capability and evaluation

### 10.1 Fix the claim before extending the detector

`trufor._model()` currently returns `None` even if a weight path exists. Setting `with_trufor=True` alone does not integrate a working model.

Choose and complete one documented implementation:

- A working, versioned manipulation-detector adapter with supported local weights, preprocessing, inference, and validation; or
- A clearly labeled heuristic baseline evaluated on an actual labeled AI-generated/edited specimen corpus, with its limitations stated.

An unavailable adapter must emit unavailable status. Do not represent `None` as a passing result. Do not claim general AI-generation detection merely because an unsigned document fails issuer verification.

### 10.2 Proposed evaluation dataset

Use fictional templates and identifiers only. Suggested categories:

| Category | Purpose |
|---|---|
| Genuine specimen scans | Baseline negatives |
| Genuine specimens photographed with consent | Camera/lighting negatives |
| Benign resize/compression/screenshot/rotation | Detect shortcut learning and quality sensitivity |
| Classical field edits | Local manipulation baseline |
| AI-assisted text/portrait edits | Actual AI-related forgery test |
| Fully generated specimen document images | Full-image generation test |
| Reprinted/recaptured manipulated specimens | Test whether detector survives capture changes |
| Unseen templates/generation methods | Generalization test |

Keep the same source identity/document and all edited variants in one split. Keep generator families out of training for an unseen-generator test. Balance compression and export metadata across genuine and forged classes. Record generator/tool/version and transformation provenance without leaking those labels into model features.

Report at least three independent results: issuer/signature validation, visual forgery detection, and end-to-end identity fraud detection. A forged document can fail signature verification without the visual detector recognizing its generated origin.

### 10.3 Capture normalization

Current normalization simply resizes to a fixed template. Improve it with document detection and perspective correction where feasible, then assess alignment quality.

- Avoid trusting a malformed/unverified QR payload to choose security-sensitive behavior.
- Use QR corners or document boundaries as geometric cues, with validation.
- Reject/recapture when reliable alignment is unavailable.
- Test glare, cropped edges, rotation, perspective, low resolution, and unreadable fields.
- Keep unreadable images out of automatic approval and out of unsupported “forgery confirmed” claims.

### 10.4 Required reporting

- Per-family precision/recall and false-positive rate.
- Confidence intervals and sample counts.
- Performance on benign edits versus malicious edits.
- Supported templates, minimum usable quality, and unavailable-detector behavior.
- Explicit statement that no finite benchmark establishes resistance to all generative models.

## 11. Stage I — evaluation correctness and reproducibility

### 11.1 Files

- `eval/build_dataset.py`
- `eval/train.py`
- `eval/run_attacks.py`
- `eval/adaptive_attacker.py`
- `eval/seed_db.py`
- `scripts/run_tests.py`
- `backend/app/testkit.py`
- Proposed `eval/splits.py`, `eval/manifest.py`, shared policy imports

### 11.2 Establish decision parity

Live, seeded, adversarial, and offline evaluation must call the same policy/decision implementation. The live path currently performs simulated voice adjustment that offline scoring omits.

After removing that adjustment:

- Unit-test identical features/evidence producing identical probabilities, rule codes, eligibility, and bands across paths.
- Distinguish extraction tests from decision tests. Cached features cannot prove capture validation works.
- Do not represent a caller-supplied liveness flag as a live-camera test.
- Rework `scripts/run_tests.py`: a no-camera API upload should expect review unless a fully separate test harness supplies explicitly simulated evidence. Never add a public `passed=true` shortcut to recover historical `14/14` outputs.

### 11.3 Split discipline

Current fusion split: days 0–15 training, 16–19 calibration, 20–29 testing. Face threshold calibration and behavior-model fitting currently use days below 20.

This is **calibration-stage overlap**, not evidence that days 20–29 were used for fitting. Fix it by:

1. Fit component models and component thresholds on training-only data or a training-internal validation partition.
2. Fit fusion on the training feature set.
3. Calibrate probability and select operating thresholds on explicitly designated calibration data.
4. Evaluate the frozen full system on untouched test data.
5. Persist split membership and enforce it programmatically across scripts.

Separate two evaluation questions:

- **Temporal deployment:** history from earlier events is available, all features are computed as of the event, and test labels are not used.
- **Unseen identity/ring generalization:** hold out complete identities, source documents, fraud operators/rings, and related variants from fitting/calibration.

Report both rather than claiming one time split proves unseen-identity performance. Retain realistic historical context for graph tests, but distinguish “ring continuing from earlier history” from “entirely unseen ring.”

### 11.4 Fix score and label semantics

- Do not replace model probability with `0.95` merely because a hard rule rejected a case when calculating probability metrics.
- Compute ROC-AUC/PR-AUC and probability calibration on the actual model score.
- Compute final decision precision/recall/confusion on the policy bands separately.
- REVIEW-or-REJECT is a flag rate; report review workload and reject-only precision too.
- Keep fraud detection rate distinct from false discovery rate; define abbreviations prominently.
- Report type classification with real confusion matrices. If several types are accepted as equivalent, disclose the grouping rather than hiding it in an alias rule.
- Do not force ablation results to show fusion winning. Report measured results even if an individual module is stronger.
- Treat tiny or empty subgroups as insufficient data, not 0%/100% confidence.

### 11.5 Adversarial evaluation limitations

Image perturbations are useful robustness tests but do not establish deepfake/injection resistance. The existing adaptive attack mutates derived feature values; it is a feature-space sensitivity test, not necessarily a realizable end-to-end attack.

Label each evaluation as one of:

```text
real-media transformation
synthetic fixture
mocked verification evidence
feature-space sensitivity
real capture integration test
```

For any realism claim, regenerate raw inputs and recompute derived features. Do not independently change graph degree, ring scores, and behavior aggregates into combinations that no application history could produce and call them a demonstrated real bypass.

### 11.6 Required metrics and provenance

Every generated report should include:

- Git commit, run ID, timestamp, seed.
- Dataset and source-media manifest hashes.
- Component/model versions and feature/policy schema versions.
- Split definitions and overlap assertions.
- Real/simulated/unavailable evidence counts.
- Precision, recall/FDR, F1, FPR, confusion matrix.
- Review rate, rejection rate, rejection precision, and genuine-user recapture rate.
- ROC-AUC/PR-AUC from actual scores and calibration metrics where meaningful.
- Per-fraud-family results and hard-negative subgroup results.
- Attack success rate defined as fraudulent cases automatically approved, with denominators.
- Confidence intervals; use group-aware resampling for linked applications where appropriate.
- End-to-end latency p50/p95 and queue delay, distinguished from cached batch CPU timings.

Store a manifest with each artifact and refuse stale/incompatible combinations. Regenerate metrics after policy or extraction changes; never keep old headline numbers beside new behavior without a visible historical label.

## 12. Stage J — UI, explanations, and honest product language

Files: applicant wizard/progress pages, dashboard layout/case/metrics/attack lab, `components/Evidence.tsx`, `components/ui.tsx`, API types, README/testing docs.

### Required changes

- Keep the latest institutional theme.
- Show mock-registry status visibly; external-looking routes do not turn local dictionaries into authoritative integrations.
- Label face comparison as real computation, camera labels as client-reported hints, voice/fingerprint as simulated, and missing adapters as unavailable.
- Replace unverified encryption/compliance claims. Local HTTP does not provide HTTPS transport encryption; a consent checkbox alone does not establish DPDP compliance.
- Explain evidence insufficiency separately from suspected fraud.
- Display model probability separately from policy reason and analyst disposition.
- Protect dashboard data on the backend even when frontend navigation is blocked.
- Preserve sanitized public aggregate metrics on the landing page if desired.
- After an override, show the authenticated analyst, timestamp, note, old/new disposition, and immutable automated decision.
- Add accessible sign-in, retry, expiry, upload-limit, unavailable-model, and stream-error states.
- Do not advertise the historical `0.996` AUC or `100%` recall as current results after changing logic.

### LLM safeguards

Existing LLM code is outside the automated decision path; preserve that boundary.

- Prefer fixed structured evidence and deterministic templates.
- Treat applicant text, filenames, document OCR, and investigator questions as untrusted content.
- LLM output cannot mutate decisions, thresholds, evidence, or audit records.
- Citing an allowed reason code does not prove that the surrounding generated prose is accurate. Validate critical fields or render them directly outside generated prose.
- For a fast reliable demo, keep decision/action/probability in deterministic UI fields and let the LLM provide only non-authoritative explanatory wording.
- Add a test showing malicious document text cannot change policy and generated text cannot override a decision.

## 13. Consolidated regression and acceptance matrix

Every row requires an automated test unless explicitly marked manual/integration.

| ID | Case | Required outcome |
|---|---|---|
| P01 | Low model score, missing required selfie face | REVIEW, missing-evidence code |
| P02 | Missing registry face/similarity | REVIEW, no fabricated match |
| P03 | NaN/Infinity numeric features | Controlled validation/review behavior; never automatic approval |
| P04 | Invalid signed QR | Document integrity rule applied |
| P05 | Valid QR with different identifier | Contradiction raised; cannot APPROVE |
| P06 | Low-confidence OCR mismatch | Recapture/review, not unsupported forgery certainty |
| P07 | PAN suffix collision across two people | Full linkage mismatch detected |
| P08 | Registry timeout vs identity absent | Distinct evidence statuses |
| P09 | Simulated voice score changed | Ordinary decision unchanged |
| P10 | Model artifacts missing/stale | Explicit unavailable state; no silent calibrated fallback |
| L01 | Claimed client liveness without server evidence | REVIEW |
| L02 | Frames from another identity | REVIEW/failure |
| L03 | Challenge replay/expiry/cross-session use | Denied or unresolved liveness |
| L04 | Two concurrent consumers | At most one successful consumption |
| L05 | Wrong sequence/multiple faces | No completed liveness claim |
| L06 | Valid consented camera sequence | Pass supported checks; manual/integration |
| A01 | Anonymous list/case/graph/chat/config access | Denied |
| A02 | Anonymous override/band change | Denied; no mutation |
| A03 | Applicant A requests B's evidence/events/result | Denied |
| A04 | Expired session/logout session | Denied |
| A05 | Forged client actor | Audit uses server principal |
| A06 | CSRF/cross-origin privileged mutation | Denied |
| A07 | Registry JSON/private history/key requested via static path | Never returned |
| A08 | Traversal or symlink outside evidence root | Denied |
| D01 | Demo tools disabled | Mutation routes unavailable |
| D02 | Demo enabled but caller anonymous | Denied |
| D03 | Demo test run | Writes only isolated demo/test storage |
| I01 | Malformed JSON, wrong types, huge strings/vectors | Controlled 4xx |
| I02 | Oversized bytes/pixels/frame count/corrupt image | Controlled rejection and cleanup |
| I03 | Client-supplied IP/forwarded headers | No override of server trust policy |
| I04 | Missing telemetry | Unavailable, not invented human behavior |
| J01 | Duplicate submit | One idempotent application result |
| J02 | Abandoned/reconnected SSE | Bounded storage and documented recovery |
| J03 | Parallel jobs exceeding configured capacity | Controlled admission, no unbounded threads |
| G01 | Restart and replay same history | No duplicate graph entries |
| G02 | Failure between correlation and persistence | Recoverable, consistent state |
| G03 | Future record exists in history | Excluded from earlier-event assessment |
| G04 | Family/hostel shared attributes | No fraud assertion from sharing alone |
| E01 | Same evidence through live/offline/seeded policy | Same bands, eligibility and reason codes |
| E02 | Dataset split overlap assertions | No forbidden identity/document/ring leakage |
| E03 | New policy with old metric manifest | Stale result rejected or visibly historical |
| E04 | Unseen AI-forgery family | Measured result reported with sample count |
| U01 | Upload fallback | Clear REVIEW expectation |
| U02 | Sign-in, camera failure, expired challenge | Accessible recovery; manual/browser QA |
| U03 | LLM adversarial text | No decision or state mutation |

The test suite must check forbidden outcomes and persistence effects, not just whether a reason string exists. Do not write tests that accept both APPROVE and REVIEW for cases with missing mandatory evidence.

## 14. Suggested file-by-file implementation checklist

| File or area | Work |
|---|---|
| `backend/app/config.py` | Typed settings, configurable paths, secrets, modes, limits, versions |
| Proposed `backend/app/security.py` | Analyst sessions, applicant capabilities, CSRF/origin protection, role dependencies |
| Proposed `backend/app/liveness_sessions.py` | Fresh sessions/challenges, expiry, atomic consumption, evidence binding |
| Proposed `backend/app/policy.py` | Shared evidence eligibility and deterministic decision policy |
| `backend/app/schemas.py` | Typed application/evidence/job results, new reason codes, strict validation |
| `backend/app/main.py` | Route authorization, typed payloads, upload bounds, protected artifacts, bounded jobs |
| `backend/app/graph/pipeline.py` | Server verification context, shared policy, simulation isolation, consistent persistence |
| `backend/app/fusion/model.py` | Model scoring only, artifact compatibility, no silent calibrated fallback |
| `backend/app/fusion/fraud_type.py` | Inconclusive category, remove unsupported injection certainty |
| `backend/app/modules/biometric/agent.py` | No trusting client pass, frame-to-selfie binding, explicit missing evidence |
| `backend/app/modules/biometric/face.py` | Face counts, quality, validated frame/pose support |
| `backend/app/modules/document/qr_sign.py` | Typed versioned payload, verifier public-key separation |
| `backend/app/modules/document/agent.py` | Complete field checks, quality-aware contradictions, unavailable adapter status |
| `backend/app/modules/document/trufor.py` | Real tested adapter or honest unavailable baseline; remove misleading stub assumptions |
| `backend/app/modules/registry/agent.py` | Full subject linkage, name/DOB checks, explicit source states |
| `backend/app/modules/registry/mocks.py` | Isolated data store, provenance, no unprotected enumeration |
| `backend/app/modules/behavior/agent.py` | Missing telemetry handling, trusted server features, benign automation cases |
| `backend/app/modules/correlation/*` | Trust-aware history, snapshot/locking, temporal correctness and idempotency |
| `backend/app/db.py` | Evidence/job metadata, authenticated audit actors, disposition separation, migrations |
| `backend/app/demo_kit.py`, `testkit.py` | New subject linkage; isolated demo writes; no liveness bypass |
| `data/gen_population.py` | Versioned fixtures, source/group provenance, stronger linkage and hard negatives |
| `eval/*` | Shared splits/policy, honest scores, manifests, new adversarial datasets and reports |
| `scripts/run_tests.py` | Authenticated test harness, new missing-evidence expectations, isolated storage |
| `frontend/lib/api.ts` | Auth/error types, scoped progress access, nullable/unavailable probability |
| `frontend/lib/liveness.ts` | Server-issued sequence integration and supported capture evidence |
| `frontend/app/kyc/*` | Consent metadata, challenge lifecycle, review fallback, accurate text |
| `frontend/app/dashboard/layout.tsx` | Analyst sign-in/session gate/logout |
| `frontend/app/dashboard/case/[id]/page.tsx` | Protected artifacts, evidence status, reliable override audit display |
| `frontend/app/dashboard/metrics/page.tsx` | Model vs policy metrics, provenance and stale indicators |
| `frontend/app/dashboard/attack-lab/page.tsx` | Distinguish media tests, fixtures and feature sensitivity |
| `frontend/components/Evidence.tsx` | Sanitized current aggregate metrics, honest unavailable states |
| `frontend/next.config.ts` | Coherent proxy/auth/SSE behavior and trusted network forwarding |
| `README.md`, `docs/TESTING.md` | Setup, limitations, updated expected outcomes, regenerated metrics |

## 15. Suggested commit sequence and review gates

Keep each commit reviewable; do not merge unfinished protocol changes that strand the frontend.

1. **Characterization tests and isolated settings:** reproduce defects and establish test storage.
2. **Shared evidence policy:** fix approval floors, missing data, model availability and fraud-type language.
3. **Simulation isolation:** remove simulated voice decision changes; add live/offline parity tests.
4. **Liveness protocol:** backend session lifecycle, frontend challenge integration, expiry/replay/binding tests.
5. **Access controls:** analyst authentication, applicant scoping, protected media, demo isolation, compatible UI.
6. **Identity linkage:** QR schema/key separation, full PAN relationship, regenerated fixtures.
7. **Resource/graph reliability:** validation, bounded jobs, telemetry trust, history consistency and cleanup.
8. **Forgery evaluation:** working detector/baseline, real labeled specimen corpus, alignment quality handling.
9. **Evaluation rebuild:** training/calibration splits, policy parity, manifests and honest metrics.
10. **Documentation and complete demo QA:** update all claims and verify the full workflow.

At every gate, run relevant unit tests. At protocol/access-control gates, also run browser integration. At evaluation gate, freeze configuration and regenerate all dependent artifacts together.

## 16. Definition of done

The handoff is complete only when all of the following are true:

- [ ] Missing required identity/capture evidence cannot result in automatic approval.
- [ ] Client claims cannot establish server liveness success.
- [ ] Challenge expiry, ownership, one-time use, and frame/selfie binding are tested.
- [ ] Simulated signals are visible and cannot silently alter ordinary approval.
- [ ] Document and registry subject binding checks cover identifier collisions and contradictions.
- [ ] Analyst mutations/data and applicant artifacts have backend authorization.
- [ ] Demo enrollment tools are disabled by default and isolated when enabled.
- [ ] No broad static directory exposes registry JSON, raw history, private keys, or unrestricted applicant media.
- [ ] Input/upload/concurrency/job/history behavior is bounded and tested.
- [ ] Current metrics come from the same decision policy used live.
- [ ] No-camera tests no longer impersonate genuine server-verified liveness.
- [ ] AI-forgery claims are backed by an actual labeled evaluation, with unavailable components disclosed.
- [ ] Model scores, policy bands, analyst dispositions, and truth labels remain separate.
- [ ] A clean checkout can reproduce setup/tests with documented commands on the team's OS.
- [ ] Unit, integration and browser results are recorded with exact versions and known failures.
- [ ] README/UI/testing documentation no longer promise unsupported encryption, compliance, general deepfake resistance, or historical accuracy as current accuracy.

## 17. Final demo script after implementation

1. Show the PS deliverable map and identify real versus simulated components.
2. Start an isolated demo environment; sign into the analyst console.
3. Submit a genuine specimen identity using a fresh, supported camera challenge.
4. Show a field-edited document caught by signed-content/OCR inconsistency.
5. Show a mixed identity caught by full cross-source linkage and face mismatch.
6. Show an incomplete/replayed challenge going to review rather than being called a confirmed criminal attack.
7. Submit linked synthetic applications and show the identity graph, including why sharing alone is insufficient.
8. Show generated-document evaluation separately from signature validity.
9. Show the current run manifest, per-family metrics, false positives, review workload, and a known limitation.
10. Close by explaining that this is a measured fraud-detection simulator. It does not establish a bypass against any real bank, nor claim universal resistance to forged media.

**Implementation note for the receiving developer:** Do not restore an old attractive demo outcome by reintroducing trusted client flags, hidden test overrides, hard-coded metrics, or simulated independent evidence. If the stricter system reviews more genuine cases, measure and explain that tradeoff, then improve the actual verification quality.
