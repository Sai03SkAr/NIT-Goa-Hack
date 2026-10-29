# What we took from IDRBT, why, and what it changed

IDRBT (the Institute for Development and Research in Banking Technology, set up by the RBI) publishes its fraud and
security research through the Centre for AI and ML (Prof. Vadlamani Ravi's group). None of it is about onboarding KYC:
it targets ATM, card and bank fraud. We read it for algorithms that **transfer** to synthetic-identity KYC, tested each
one on our own data, and kept only what measurably helps.

## The IDRBT work we read

| IDRBT work | What it does | Source |
|---|---|---|
| Explainable One-Class Classification for ATM fraud (Vivek, Ravi, Mane, Naidu, COMSNETS 2025) | K-Means on **legitimate transactions only**, one bounding-box rule per cluster; anything outside every rule is flagged, and the broken rule is the explanation | IEEE COMSNETS 2025 |
| XAI and causal inference for ATM fraud (Vivek, Ravi, Mane, Naidu, arXiv 2211.10595) | Binary and one-class models on Indian ATM data, SHAP, causal inference and **counterfactuals** | arXiv 2211.10595 |
| FedPNN, one-shot federated classification (Prasad, Vivek, Ravi, arXiv 2304.04147) | Each client clusters locally and sends only **cluster centres**; the server meta-clusters them in **one round**; motivated by card fraud | arXiv 2304.04147 |
| Chaotic VAE adversarial ML (Reddy, Vivek, Pranay, Ravi, arXiv 2302.12959) | A variational autoencoder generates evasion / poisoning samples; the **logistic map** replaces Gaussian latent noise | arXiv 2302.12959 |
| ATM fraud with streaming analytics (arXiv 2303.04946); GAN oversampling; Adversarial ML for banks (Canara Bank project) | Sliding-window models, oversampling for rare fraud, defending bank IDS/UEBA | IDRBT project archive |

## What we measured before deciding (our data, time split, test = 444 apps / 85 fraud)

**1. Zero-day fraud: the trained model alone does not generalise.** Retraining the model with one fraud type removed,
then testing on that unseen type:

| Unseen type | Model alone | Genuine-profile rules alone | Model + evidence policy (live system) |
|---|---|---|---|
| Bot | **0.00** | **0.94** | 1.00 |
| Tampered card | **0.40** | **1.00** | 1.00 |
| First-party | 0.96 | 0.77 | 1.00 |
| Ring | 1.00 | 1.00 | 1.00 |
| Third-party | 1.00 | 1.00 | 1.00 |

The supervised model misses fraud it never saw; the one-class profile, which never saw *any* fraud, catches it; our
evidence-first policy catches all of it. Three independent layers, each covering the others' blind spots.

**2. The genuine profile needs no fraud labels.** Trained on genuine applicants only (963, no fraud labels): ROC-AUC
**0.984**; **92%** of fraud falls outside it vs **5.9%** of genuine (threshold set at 2% of held-out genuine; later
weeks drift a little). Useful for a bank on day one, before it has any labelled fraud.

**3. Federation costs nothing, and helps banks with narrow customer bases.** Three banks share only cluster
summaries (never a customer row) and the server merges them in one round:

| Setting | ROC-AUC | Fraud outside the profile |
|---|---|---|
| All data pooled (not allowed in practice) | 0.989 | 92% |
| Federated, banks with similar customers | 0.990 | 92% |
| Federated, banks with different customers (split by age) | **0.991** | **99%** |
| One bank alone, different customers | 0.982 | 87% |

**4. A generative attacker gets through a session-only detector, not the fused system.** A chaotic-VAE attacker
samples realistic genuine behaviour and graph values (every feature an applicant controls, 64 samples per case):

| Target | Frauds turned into an approval |
|---|---|
| Behaviour-and-graph-only detector (what session-watching tools do) | **49 of 49** it had caught |
| TrueID (model + evidence policy) | **0 of 85** |

Risk on the full system barely moves (1.00 → 0.94–0.97): the fraud is pinned by evidence an attacker cannot fake.

## Decisions

| Idea | Decision | Why |
|---|---|---|
| Genuine-profile one-class rules | **Build.** Shown on every case as readable rules, recorded as informational evidence, monitored by the learning loop. **Not a decision gate.** | Catches zero-day types the model misses and explains itself. As a gate it would hold ~3 points more genuine applicants with no measured recall gain (the evidence policy already catches every unseen type), so `POLICY_VERSION` stays unchanged. |
| Federated one-shot profile | **Build** (library + evaluation). | Lets consortium banks build a shared "what genuine looks like" without sharing data, matching the hashed-identifier consortium. |
| Chaotic-VAE attacker | **Build** into the Attack Lab, with a behaviour-only contrast. | A stronger, distribution-aware red team than the greedy attacker: the adversarial-ML idea the mentor asked about, used for defence. |
| Counterfactual "what would change this decision" | **Build** as an analyst panel. | Per case: can anything the applicant controls flip the decision? A per-decision robustness margin. |
| Streaming windows, GAN oversampling | Skip. | We already have velocity windows, and no recall gap that oversampling would fix. |

## Where it lives
- `backend/app/fusion/profile.py`: genuine profile (fit, score, explain, federate).
- `backend/app/fusion/counterfactual.py`: decision counterfactuals; analyst endpoint `GET /api/apps/{id}/counterfactual`.
- `eval/train.py`: fits the profile, writes the zero-day table and cold-start numbers into `metrics.json`.
- `eval/federated_profile.py`: federated evaluation → `precomputed/federated.json`.
- `eval/vae_attacker.py`: chaotic-VAE attack → added to `precomputed/attacks.json`.

## Honest limits
- All numbers come from our synthetic population; IDRBT's papers use real ATM and card data from Indian banks.
- The profile and the counterfactuals explain and monitor; they never approve or reject.
- Federation here shares cluster centres and per-cluster bounds. They summarise customers but are not differential
  privacy; production would add noise to the shared summaries (or secure aggregation).
