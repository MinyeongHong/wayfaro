# Wayfaro

Private, evidence-based CV and job description comparison.

Paste a CV and a job description, review the current external-AI consent policy,
then explicitly consent to a temporary comparison. No signup, upload or permanent
CV storage is provided. The interface is English. React/TypeScript/Vite, FastAPI,
SQLAlchemy and PostgreSQL are the only application infrastructure.

## Scope and result semantics

Gemini extracts required/preferred requirements and compares exact document evidence.
Results distinguish `MATCHED` and `UNVERIFIED`: unverified means the CV does not
establish the requirement, not that the person lacks the skill. Suggestions highlight
existing evidence or ask confirmation; they never confirm CV_GAP/SKILL_GAP.
There is no aggregate score. Work eligibility remains `NOT_ASSESSED`.

Pydantic validates results locally. Evidence must match exact original text and
Unicode code-point positions. Incorrect offsets can be repaired only when the exact
quote occurs once; correct offsets may identify repeated quotes. Absent, altered or
ambiguously located quotes are rejected. Gemini's transmission schema omits `maxItems`
only; local Pydantic limits remain enforced.

## Database transition — read before starting

The migration history has been replaced with **one initial revision `cv_initial`**.
It creates only `background_jobs`, `analysis_sessions` and `cv_match_analyses` (plus
Alembic's version table). This history is **incompatible with existing databases**.
Do not run the new application, worker or `alembic upgrade head` against an old
schema. Do not use `alembic stamp` to conceal the mismatch.

The existing development database has not been reset. Resetting it requires separate
approval after confirming the PostgreSQL instance, database name, connected clients
and deletion scope. No other database or Docker volume may be removed. Stop old API
and worker processes before a separately approved reset. Old job compatibility is
not supported. Repository history is the recovery source for the old code/schema.

Only after a compatible empty development database is available, start the stack:

```sh
docker compose up --build
```

Frontend: http://localhost:5173 · API docs: http://localhost:8000/docs.
Compose retains the existing development DB identifiers; do not run `down -v`.
For manual startup, use a project-local virtual environment and a compatible DB:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
# Set DATABASE_URL before these commands. Never target the old development schema.
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload
# In another terminal, same backend directory and environment:
../.venv/bin/python -m app.workers.runner
```

Use Node.js 22 for the frontend (`npm ci`, `npm run dev` in `frontend/`).

## Configuration

See `.env.example`. Backend settings are loaded from environment variables and a
`.env` in the backend process's working directory. Compose reads root environment
values and forwards server settings. Configure API and worker consistently.

- `DATABASE_URL`: compatible PostgreSQL database.
- `GEMINI_API_KEY`, `GEMINI_MODEL`: server-only secrets/model; never `VITE_*`.
- `CV_MATCH_RETENTION_HOURS`: temporary document/result retention, default 24, range 1–168.
- `CV_MATCH_COOKIE_SECURE`: default true; use false only for local HTTP testing.
- `CV_MATCH_ALLOWED_ORIGINS`: JSON array of exact trusted frontend origins.
- `CV_MATCH_SESSION_LIMIT`: active analyses per anonymous session, default 10.
- `CV_MATCH_GLOBAL_PENDING_LIMIT`: pending/processing capacity, default 100.
- `CV_MATCH_GLOBAL_DAILY_LIMIT`: submissions per rolling day, default 200.
- `VITE_API_URL`: frontend API base URL, no secrets.

## API and ownership

| Endpoint | Contract |
| --- | --- |
| `GET /api/v1/health` | Health status |
| `GET /api/v1/analyses/policy` | Current consent, provider policy and limits |
| `POST /api/v1/analyses` | `{cv_text, jd_text, consent: true, policy_version}`; HTTP 202 |
| `GET /api/v1/analyses/{analysis_id}` | Owned status, expiry, result or safe error |
| `DELETE /api/v1/analyses/{analysis_id}` | Owned deletion with CSRF; HTTP 204 |
| `GET /api/v1/tasks/{task_id}` | Owned analysis task state and attempt information |

POST returns `analysis_id`, `task_id`, `status`, `status_url`, `expires_at`,
`csrf_token`. Use the policy's current version; never assume a stale version.
The initial POST establishes an anonymous HttpOnly session cookie and a separate
CSRF cookie. Existing-session POST and DELETE require `X-CSRF-Token`; GET does not.
Cookies must be included in requests. Origin checks apply to mutations. Missing,
expired and other-owner analyses are not exposed. See `/docs` for complete schemas.

The browser keeps documents, results and identifiers in memory only. It does not
put them in URLs, browser storage, logs or analytics. An ambiguous POST response is
never automatically resent. Users can resume GET polling or explicitly start over.

## Privacy and worker behavior

Consent is required before sending documents to Google's Gemini API. Deletion from
Wayfaro cannot retract content already sent to the provider; review the policy URL
returned by the policy endpoint. No real provider call is needed for ordinary tests.

Temporary texts and results are stored in PostgreSQL until deletion/expiry. Expired
analyses are immediately unavailable; the worker periodically removes their private
data (normally checked every 60 seconds while running). Anonymous sessions last up
to seven days. Sanitized queue records can remain for state/budget accounting.
Database backups and provider retention require their own operational policies.

The PostgreSQL worker supports `cv_compare`. `SKIP LOCKED` distributes claims.
A 300-second lease is renewed every 30 seconds. Task tokens and DB wall-clock expiry
are checked before result persistence and completion. Failures retry within the
attempt limit, with exponential backoff starting at five seconds, capped at one hour.
`Retry-After` can extend this up to 24 hours. Unknown task types fail terminally.
No Redis, Celery or legacy task handlers are present.

Gemini diagnostics expose only safe codes, numeric HTTP status and the failing
`extraction`/`comparison` stage. ReadTimeout is distinct from HTTP errors. Provider
response bodies, authentication headers, documents and keys are never diagnostic
content. HTTP 400 alone does not prove a particular schema incompatibility.

## Verification

From the repository root, run against an **independent disposable PostgreSQL 16
instance**, never the development database. For example, create a container with
no development volume mounted:

```sh
wayfaro_test_container=$(docker run --rm -d \
  --tmpfs /var/lib/postgresql/data:rw \
  -e POSTGRES_USER=wayfaro_test -e POSTGRES_PASSWORD=local-test-only \
  -e POSTGRES_DB=wayfaro_test -p 127.0.0.1:55432:5432 postgres:16-alpine)
docker exec "$wayfaro_test_container" pg_isready -U wayfaro_test -d wayfaro_test
# Wait for readiness before testing.
TEST_DATABASE_URL=postgresql+psycopg://wayfaro_test:local-test-only@127.0.0.1:55432/wayfaro_test \
  RUN_GEMINI_SMOKE=0 PYTHONPATH=backend .venv/bin/python -m pytest -q -rs backend/tests
.venv/bin/ruff check backend/app backend/tests --select E4,E7,E9,F
docker stop "$wayfaro_test_container"
```

Each PostgreSQL test uses a unique schema and removes only that schema. Migration
tests use the real Alembic command environment, check head/version metadata, repeat
upgrade, downgrade and re-upgrade. Offline tests compare generated DDL and indexes.
Without `TEST_DATABASE_URL`, PostgreSQL tests skip and cannot be reported as passed.

```sh
cd frontend
npm ci
npm test
npm run typecheck
npm run build
```

`test_match_live.py` is a separate opt-in synthetic Gemini smoke test, skipped unless
`RUN_GEMINI_SMOKE=1` and provider configuration are explicitly supplied. It must not
be enabled without approval. Default tests use mock LLMs and mock HTTP transports.

## Reading the code

Start with `models/core.py`, `api/analysis.py`, `services/matching/schemas.py`,
`storage.py`, `workers/runner.py`, matching `worker.py`, `pipeline.py`, `llm.py` and
`privacy.py`. For the UI: `App.tsx`, `AnalysisPage.tsx`, `analysisController.ts`,
`analysisApi.ts`, `analysisText.ts`, then `components/analysis/AnalysisResults.tsx`.

## Latest local verification

Private-comparison cleanup: backend **123 passed, 26 skipped**, no failures.
Twenty-five skipped tests require isolated PostgreSQL; Docker socket access was denied
in the execution environment. One intentionally skipped test is the live Gemini call.
Offline migration DDL/contract and single-head checks passed; actual PostgreSQL
upgrade/downgrade and worker integration still require execution in a permitted environment.
Two deprecation warnings concern FastAPI/Starlette TestClient and Alembic configuration.
Node 22 frontend: **27 passed**, TypeScript and Vite production build passed. Ruff and
`git diff --check` passed. No development DB reset or real Gemini call was performed.
