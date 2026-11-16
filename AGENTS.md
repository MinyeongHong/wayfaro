# Repository Guidelines

## Product scope

Wayfaro is a private text CV/JD comparison service. React, TypeScript and Vite form
the English UI; FastAPI, SQLAlchemy, PostgreSQL and a database worker form the backend.
No public job catalog, ATS connectors, manual job ingestion, ranking, PDF parsing,
login or permanent CV storage. Do not restore removed product features implicitly.

## Structure and responsibilities

- `backend/app/api/`: policy, analysis creation/status/deletion, owned tasks, health.
- `backend/app/models/core.py`: BackgroundJob, AnalysisSession, CVMatchAnalysis only.
- `backend/app/services/matching/`: Gemini adapter, comparison pipeline, schemas,
  evidence verification, temporary storage, privacy, cleanup and analysis worker.
- `backend/app/workers/runner.py`: PostgreSQL claim, lease, heartbeat and retry.
- `backend/alembic/versions/0001_cv_comparison.py`: sole initial revision `cv_initial`.
- `backend/tests/`: deterministic unit tests, isolated PostgreSQL integration tests,
  migration contracts and separately opted-in live Gemini smoke test.
- `frontend/src/`: analysis-only React UX. `frontend/tests/`: Node test runner.

## Development workflow

Inspect before changing; propose a plan and wait for approval unless already authorized.
Preserve existing uncommitted work. Implement one milestone at a time. Avoid new
infrastructure, abstractions and dependencies unless needed. Report changed files,
actual test results/skips and limitations. Never claim an unexecuted test passed.

## Database safety

The previous migration history was replaced by `cv_initial`, which is incompatible
with old databases. Do not upgrade or stamp an old schema. Development DB deletion
or recreation requires separate explicit approval identifying the instance, DB and
scope. Do not modify other databases or Docker volumes. Tests require an independent
PostgreSQL 16 database via TEST_DATABASE_URL and unique disposable schemas. No reset
against development. Future schema changes should add revisions, not rewrite this
initial revision without authorization.

## Privacy and analysis invariants

Keep cv_compare and common PostgreSQL queue fencing/heartbeat/backoff intact.
Never put CV/JD text in URLs, logs or queue payloads. Frontend documents, results and
analysis handles stay in memory: no localStorage, sessionStorage or analytics.
Never automatically resend an ambiguous POST. Preserve anonymous ownership, cookies,
CSRF, origin checks, consent, expiry, physical deletion and sanitized error handling.
No actual Gemini calls without explicit approval. Secrets/model come from server
GEMINI_API_KEY/GEMINI_MODEL; never expose secrets to VITE_* or logs.

Use exact supporting quotes with Unicode code-point offsets. Repair incorrect offsets
only for a unique exact quote; accept repeated quotes only at correct original offsets.
Preserve local Pydantic limits even when transmission schema omits maxItems.
Use MATCHED/UNVERIFIED; UNVERIFIED does not mean missing skill. No unconfirmed gaps,
aggregate score, fabricated experience or eligibility assessment. Work eligibility
stays NOT_ASSESSED. Keep existing analysis API contracts.

## Commands and style

Use a project-local Python 3.12 environment, never system-wide dependency changes.
From `backend/`: `PYTHONPATH=. ../.venv/bin/pytest -q tests` and
`../.venv/bin/ruff check app tests --select E4,E7,E9,F`.
Set RUN_GEMINI_SMOKE=0 for ordinary verification. PostgreSQL tests skip without a
dedicated TEST_DATABASE_URL. Run them before claiming database verification.
From `frontend/` with Node 22: `npm ci`, `npm test`, `npm run typecheck`, `npm run build`.
Use pytest/TestClient for backend and existing Node/React tests for frontend.
Python: four spaces, snake_case functions, PascalCase classes. Frontend: two spaces,
single quotes, semicolons, PascalCase components, camelCase functions, strict TS.
Git is available. Use concise imperative commit subjects and report validation and
migration/configuration implications in reviews.
