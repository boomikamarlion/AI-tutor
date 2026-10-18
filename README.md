# Ecosys — AI learning platform

A hands-on prompt-engineering workspace for college students. Not a video course: learners write a
prompt for a real brief, it runs on a pinned test set, a critic grades it against a human-written
rubric and points at the weak parts of the prompt, and the learner revises until the score moves.

- **Core course:** 12 modules, 46 concept cards, 35 labs (`content/`), from "how a model thinks" to a
  capstone. One design-thinking case — *Meenakshi Textiles goes online* — runs through every module.
- **Engagement under latency:** instant in-browser lint, per-test-case streaming, prediction
  questions while runs are in flight, cached standard paths.
- **Gamification:** XP for measured improvement with a named technique, technique mastery, streaks.
- **Hackathons:** event codes, 30-day Pro grant, leaderboard ranked on the iteration trail,
  judge view and CSV export.
- **RBAC:** admin, author, org admin, mentor, judge, learner. **Consent:** versioned and revocable.
- **Azure-native:** Container Apps, Microsoft Foundry (GPT-6 Luna / 6.1 Sol / 6 Astra), Entra External ID,
  Postgres Flexible (passwordless), Azure Managed Redis, Key Vault, App Insights — all in `infra/`.

See [docs/architecture.md](docs/architecture.md) for the design and decisions.

## Repository

```
apps/web/         Next.js 16 web app (learner canvas, mentor, judge, admin)
services/api/     FastAPI API + arq worker (runs, critic, coach agent, RBAC)
content/          course content — YAML, reviewed by PR (schema: docs/content-schema.md)
config/models.yaml  role → Foundry deployment routing, prices, budgets
infra/            Bicep for azd
scripts/          Entra External ID setup
```

## Run locally (offline, no Azure needed)

```bash
docker compose up --build          # http://localhost:3000 → "Developer login"
```

Or without Docker:

```bash
# Postgres 16 + Redis 7 running locally
cd services/api && uv sync && uv run alembic upgrade head && uv run python -m app.content.seed
uv run uvicorn app.main:app --port 8000 &   uv run arq app.worker.WorkerSettings &
cd apps/web && cp .env.example .env.local && npm install && npm run dev
```

`MODEL_PROVIDER=fake` (the default) uses a deterministic offline model so the whole loop works
without credits. Set `MODEL_PROVIDER=foundry` and `FOUNDRY_PROJECT_ENDPOINT` (and `az login`) to
use real Foundry deployments.

## Tests

```bash
cd services/api && uv run pytest            # API, RBAC, full loop (needs Postgres + Redis)
cd apps/web && npx playwright test          # first-win flow on mobile + desktop (needs the stack running)
```

## Deploy to Azure

One-time access setup: [docs/azure-access-setup.md](docs/azure-access-setup.md).

```bash
azd env new prod && azd env set AZURE_RESOURCE_GROUP rg-ecosys-prod && azd env set AZURE_LOCATION southindia
azd up
```

Without Entra settings the deployment is a **staging** build gated by a passcode
(`az keyvault secret show --vault-name <kv> -n dev-login-code`). For production sign-in, run
`scripts/setup-entra.sh <web-url>` in your External ID tenant, set the printed `ENTRA_*` values and
`azd provision` again.

Edit content in `content/`, deploy, then use **Admin → Content → Reload** (or it reloads on API start).
