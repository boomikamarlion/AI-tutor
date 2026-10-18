# Architecture & decisions

## The product in one loop

```
brief ─▶ write prompt ─▶ instant lint (ms, in browser)
                         └▶ run on pinned test set ─▶ each case streams as its own card
                              (prediction question while it runs)
                         └▶ critic grades vs human rubric, quotes the weak parts of the PROMPT
learner revises ─▶ names the technique ─▶ v1→v2 diff + score delta ─▶ XP / mastery
```

## System

```
Browser ──▶ web (Next.js 16, Container App, public)
              │  Auth.js: Entra External ID (prod) / passcode dev login (staging)
              │  BFF proxy /api/backend/* — attaches the API token server-side, streams SSE
              ▼
            api (FastAPI, Container App, internal ingress)
              │  RBAC, content, attempts, runs, events, admin
              │  enqueue ─▶ Azure Managed Redis (arq queue + pub/sub for live tokens)
              ▼
            worker (arq, Container App)
              │  runs prompt × test cases in parallel ─▶ Microsoft Foundry (Agent Framework,
              │  Responses API, Entra auth) ─▶ streams deltas to Redis ─▶ SSE to browser
              │  critic (structured output) ─▶ score, delta, XP
              ▼
            Postgres Flexible (Entra-only auth via the app's managed identity)
```

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Backend language | Python (FastAPI) | Agent Framework, Foundry SDKs and evaluation tooling are first-class in Python; agentic personalisation is on the roadmap. |
| Agent / model SDK | Microsoft Agent Framework `FoundryChatClient` | Official Foundry path; Responses API; tools + agents for the coach; one place to swap models. |
| Model routing | Roles in `config/models.yaml` | Runs on **GPT-6 Luna** ($0.10/$0.50 per 1M), critique on **GPT-6.1 Sol** ($2/$10), capstone grading on **GPT-6 Astra** ($10/$50). Code never names a model. |
| Reproducibility | Every run stores deployment, settings, lab content hash and rubric version | Learners and judges can compare v1 and v2 fairly. |
| Cost | Run + critique cache keyed by prompt/model/settings; per-learner daily soft/hard caps; credit-burn dashboard | Keeps per-learner cost under the subscription, protects the $50k pool. |
| Latency | Lint in the browser, per-case streaming, prediction-before-reveal, cached standard path | The model is never the critical path of attention. |
| Content | YAML in git, human-reviewed rubrics, projected into Postgres | Rubrics must not drift; content changes are reviewable diffs. |
| Identity | Microsoft Entra External ID; app roles `admin`, `author` in the token; scoped roles in Postgres | Azure-native CIAM with email OTP / social sign-up; org/cohort/event scopes are app data. |
| Secrets | None in code; managed identity for Postgres, Foundry, Key Vault, ACR, Storage | Passwordless by default. |
| Consent | Versioned, revocable `consents` rows; mentor views filter on `cohort_sharing`; `hiring_share` separate | DPDP Act: consent + purpose limitation, built in from day one. |
| Region | `southindia` for app + data; Foundry in `eastus2` by default | Data stays in India; GPT-6 Global Standard capacity is broadest in US regions. Change `FOUNDRY_LOCATION` if APAC Data Zone is preferred. |

## RBAC

| Role | Scope | Can |
|---|---|---|
| learner | self (+ cohort/event membership) | own attempts, runs, consents, join by code |
| mentor | cohort | see progress of consenting learners in the cohort |
| judge | event | see every participant's trail, score craft + reasoning |
| org_admin | organisation | create cohorts and hackathons, assign mentor / judge / org_admin within the org, export results |
| author | platform | preview pro content and hidden reference prompts, reload content |
| admin | platform | everything, incl. credit dashboard, plans, platform roles |

Permissions are checked in `services/api/app/auth/rbac.py` against a scope chain (a cohort's
org, an event's org), so an org admin automatically covers that org's cohorts and events.

## Adding a specialist stream (next sprints)

1. Add `content/streams/<stream>/` with the same module/card/lab schema (or a new course file).
2. Reuse the core rubric; add stream-specific criteria per lab.
3. For external tools (Unity, IDE), use the `artifact` handoff: the companion posts prompts and
   outputs to the attempt so the canvas, critic and trail work unchanged.
