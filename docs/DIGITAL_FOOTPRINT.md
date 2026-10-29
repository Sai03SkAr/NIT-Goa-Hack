# Consented digital footprint

An optional check that compares what an applicant's online footprint says with their KYC details. It is built to
run on licensed data and consent, not scraping, and is simulated until a provider is contracted.

## What it checks

| Check | Contradiction when | Source in production |
|---|---|---|
| Email timeline | The email address is older than its owner's 10th birthday | Email-intelligence vendor (first-seen date, services the address is registered with) |
| Linked account name | The account the applicant chose to link is in a different name (first-name-only profiles count as *partial*, never as a contradiction) | "Sign in with Google / LinkedIn" (OpenID Connect claims, released with the applicant's consent) |
| Linked account photo | The profile picture is a different person from the selfie (same face model and threshold as the registry check) | The same OAuth claims (`picture`) |

Email and phone age, number of services and **footprint depth** (none / thin / moderate / established) are shown for
context only.

## Rules that keep it fair and lawful

- **Separate, optional consent** (DPDP Act 2023, purpose limitation). Every applicant form has its own unticked
  checkbox: TrueID's `/kyc` page and the Kestrel, Tideway and Meridian partner sites. Partners send
  `consent.footprint: true`. Without it nothing is looked up.
- **One-sided.** Only a contradiction counts. Having no footprint, a new email or few accounts never lowers the
  score. That is how first-time digital users, older and rural applicants and people with private accounts stay in.
- **Informational, never decides.** Recorded as `ev_footprint` evidence next to the genuine profile. It is not one of the
  13 required checks and not a model feature, so `POLICY_VERSION` stays `policy-v2`.
- **Never shown to applicants.** Applicant tips skip it. Analysts see the panel; partner operations staff see the
  reason codes, the same way they see other module findings.
- **No scraping and no searching by name.** "Rahul Sharma, Pune" matches hundreds of people. We only look at the
  email, the number and the account the applicant gave us.

## Measured on the synthetic population (`eval/footprint_eval.py`)

Of 1,400 applicants, 921 consented. We compared our rule with a naive "social score" that also marks people down for a thin or new footprint:

| | Flagged by our rule | Flagged by a naive social score |
|---|---|---|
| Genuine applicants | **1.4%** (a profile picture that doesn't match the selfie: the same people the registry face check already struggles with) | **20.3%**, including everyone new to digital life |
| Fraud | 5.8% | 71.2% |

The naive score catches more fraud only by holding 1 in 5 genuine customers. Our rule is a weak fraud detector on
purpose: fraud is already stopped by evidence an attacker can't fake (signed documents, face, registries; 100% caught on
the test split), so the footprint *corroborates* a case for the analyst and never decides it. The footprint data is
simulated (`data/gen_footprint.py`), so these numbers show how the rule behaves, not real-world accuracy.

## Where it lives

- `backend/app/modules/footprint/provider.py`: the source. `TRUEID_FOOTPRINT_PROVIDER=simulated` is the default. Any
  other value reports the footprint as *unavailable* until that licensed provider is wired in, rather than inventing
  a result.
- `backend/app/modules/footprint/agent.py`: the comparison and score (consistent checks ÷ checks run).
- `backend/app/graph/pipeline.py`: `footprint_module`, run in the fusion step for live, partner and seeded cases.
- `data/gen_footprint.py`: simulated footprints. `clients/kyc-homeloan/tools/enrol_in_trueid.py` gives Kestrel's test
  people a footprint; Karthik Prabhu's linked account is in another name, to demo a contradiction.
- Case page: **Digital footprint** panel. Evaluation → **Unseen fraud**: the fairness comparison above.

## Going live

1. Sign a data-processing agreement with an email/phone-intelligence vendor, and register OAuth apps with Google and
   LinkedIn (scopes: `openid profile email`).
2. Add a provider in `provider.py` that returns the same record shape, and set `TRUEID_FOOTPRINT_PROVIDER`.
3. Have the partner sites pass the verified OAuth claims with the application. Keep the consent text and the one-sided
   rule unchanged.
