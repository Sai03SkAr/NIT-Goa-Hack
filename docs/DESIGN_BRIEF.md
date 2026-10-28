# TrueID Shield — UI design brief (for the redesign pass)

The product works end to end. This brief is for a **visual and UX redesign only**. Please keep every behaviour listed under "Do not break".

## Direction
- **Light theme.** Calm, trustworthy, institutional: think a bank's internal risk tool or a regulator dashboard, not a crypto or AI landing page.
- **Should not look AI-generated.** Avoid glowing gradients, neon accents, glassmorphism, and generic icons on every card. Prefer a restrained palette, real typographic hierarchy, generous whitespace, data-dense tables done well, and one accent colour.
- **Decision colours carry meaning; keep them consistent everywhere.** APPROVE = green, REVIEW = amber, REJECT = red. "SIMULATED" (voice and fingerprint) must stay visibly distinct and honest.
- **Two audiences:**
  - **Applicant (`/kyc`):** a nervous member of the public on a laptop or phone. Plain language, one task per screen, clear progress, reassuring privacy copy (DPDP Act 2023 consent).
  - **Fraud analyst (`/dashboard/*`):** an expert scanning many cases. Density, scannability, fast filtering, evidence side by side.
- **Demo context:** 5-minute hackathon demo on a projector. The live pipeline screen and the identity graph are the "wow" moments. They must be legible from the back of a room.

## Screens (all in `frontend/app`)
| Route | Purpose | Key data |
|---|---|---|
| `/` | Pitch / landing | Thesis line, 6 signal families, links to KYC + console |
| `/kyc` | 4-step wizard: consent → details → ID upload → selfie + liveness | Form fields, card preview, webcam with oval guide + challenge prompts + countdown |
| `/kyc?demo=1` | Same + **Presenter kit** panel (enrol presenter face → 3 scenario cards + cheat sheet) | Card images, form values |
| `/kyc/progress/[id]` | Live LangGraph pipeline streamed over SSE | 11 nodes (4 parallel agents), per-node risk + reason codes + latency, final band, fraud type, action, step-up, LLM summary |
| `/dashboard` | Review queue | Stats tiles, band/pattern filters, search, table (risk bar, band, pattern, action, status) |
| `/dashboard/case/[id]` | Case investigation | 5 module cards with reason codes; ID card + ELA toggle + QR↔OCR↔form table; face trio (selfie / card portrait / registry) with similarities; 2-hop graph; SHAP top-5; summary; approve/reject with note + audit log |
| `/dashboard/graph` | Identity graph explorer + **Fraud Ring Simulator** button | Pre-laid-out clusters (positions from API), colour by pattern/band, link-type legend |
| `/dashboard/metrics` | Evaluation evidence | KPI tiles, ablation chart (module alone vs fused), confusion matrix, per-type recall, leave-one-out table, hard-negative false-flag rates, top features + leakage check, decision-band editor |
| `/dashboard/attack-lab` | Robustness evidence | Attack list, sweep line charts (fused vs single module), single-attack tables, adaptive-attacker bars, **run one attack live** panel |

## Do not break
- **API calls** live in `lib/api.ts`. Response shapes are typed there (`AppRow`, `CaseDetail`, `ModuleResult`). Backend: `http://localhost:8000`.
- **Silent telemetry.** Every form input on `/kyc` must keep `{...tel.bind("<field>")}` (focus/blur/paste/keydown/keyup). Replacing inputs with a component library is fine if those handlers are forwarded.
- **Liveness.** `lib/liveness.ts` and the `SelfieStep` component. The `<video>` element ref, `grabFrame`, challenge loop and timing. The video is mirrored only with CSS (`-scale-x-100`); landmark logic assumes the raw frame.
- **Camera check.** `lib/device.ts`: `cameraLabels(stream)` must run after `getUserMedia`. Only the active track decides "virtual camera".
- **SSE progress.** `EventSource` on `/api/apply/{id}/events` with `node` and `done` events.
- **Graph.** `components/Graph.tsx`: nodes are pinned to API-provided `x/y` (`fx/fy`) and the graph calls `zoomToFit` after mount. Canvas colours are hard-coded in the draw callback and need light-theme values.
- **Hard-coded dark colours** to revisit: Recharts tooltip/grid colours in `metrics`, `attack-lab` and the case SHAP chart; canvas text/stroke in `Graph.tsx`; `text-[#04201d]` on primary buttons.
- **Theme tokens** live in `app/globals.css` (`:root` variables mapped via `@theme inline`). Custom classes (`.panel`, `.btn`, `.input`, `.chip`, `.label`) sit in `@layer components` so Tailwind utilities can override them.

## Run
```bash
./scripts/run_backend.sh
cd frontend && npm run dev
```
Then open `http://localhost:3000`. The database is pre-seeded with 1,400 scored applications.
