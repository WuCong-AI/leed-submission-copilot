# LEED Submission Copilot — MVP

A structured LEED lifecycle and submission-management platform for consultants, architects, engineers, owners, contractors and facility managers. It is deliberately not a generic chatbot.

## Product boundary

- Registry-driven workflows for LEED v4.1 and v5 across BD+C, ID+C and O+M.
- O+M is modeled as operational policy, performance-period, metering, survey and recurring-evidence work.
- The repository contains only illustrative registry modules. Any unprovided requirement, threshold, equation, point option or official form language is `NEED_OFFICIAL_SOURCE`.
- Outputs include evidence citations or explicit assumptions; precedent retrieval never returns verbatim submission text.

## Architecture

`apps/api` is FastAPI with Pydantic schemas, SQLAlchemy model contracts, Alembic migration and a deterministic in-memory MVP repository. `apps/web` is a Next.js App Router consultant workspace. `packages/leed_core` loads registry modules under `data/rating_systems`. PostgreSQL/pgvector, a local storage abstraction and worker-compatible boundaries are wired through Docker Compose.

## Local setup

```bash
copy .env.example .env
docker compose up --build
```

API: `http://localhost:8000/docs` · web: `http://localhost:3000`.

To run the API directly:

```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set PYTHONPATH=..\..
uvicorn app.main:app --reload
```

Run migrations with `alembic upgrade head`; seed examples via `apps.api.app.seed.seed_demo_projects` after configuring a persistence repository. Run backend tests with `pytest apps/api/tests` from the repository root.

## Adding a credit module

Create `data/rating_systems/<version>/<family>/<adaptation>/<credit_id>/` with `credit.yaml`, `evidence_schema.json`, `phase_tasks.yaml`, `review_rules.yaml`, `tender_requirements.yaml`, `submittal_template.md` and `comment_risk_rules.yaml`. Run `POST /api/registry/validate` before use. Do not put requirement logic in Python/TypeScript.

## Precedents and limitations

Import redacted precedent metadata and document chunks only after authorization. The MVP supplies deterministic placeholder embeddings/LLM behavior and does not use an external AI key. It is not an official USGBC/GBCI scorecard or certification decision; load licensed, project-specific source material before relying on any compliance result.
