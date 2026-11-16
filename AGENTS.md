# Repository Guidelines

## Project Structure & Module Organization

This Phase 1 application uses React, TypeScript, FastAPI, and PostgreSQL.
- `backend/app/`: API routes in `api/`, SQLAlchemy models in `models/`, database setup in `db/`, and the database-backed worker in `workers/`.
- `backend/alembic/`: schema migrations; add revisions under `versions/`.
- `backend/tests/`: pytest tests for health and input validation.
- `frontend/src/`: React entry point (`main.tsx`) and styles (`style.css`). No dedicated asset directory exists yet.
- `docker-compose.yml`: database, migration, API, worker, and frontend services.
- `.github/workflows/`: backend checks and frontend build automation.

## Build, Test, and Development Commands

Run from the repository root unless indicated:
- `docker compose up --build`: build and start the full stack, applying migrations before API and worker startup. Frontend: `http://localhost:5173`; API docs: `http://localhost:8000/docs`.
- In `backend/`, `pip install -r requirements.txt`: install backend and test dependencies; CI uses Python 3.12.
- In `backend/`, `PYTHONPATH=. pytest -q tests`: run backend tests.
- In `backend/`, `ruff check app tests --select E4,E7,E9,F`: run the lint checks enforced by CI.
- In `frontend/`, `npm install` then `npm run dev`: start Vite; CI uses Node.js 22.
- In `frontend/`, `npm run build`: run TypeScript checks and create the production bundle; `npm run typecheck` checks types alone.

## Coding Style & Naming Conventions

Use four-space indentation and snake_case for Python functions and modules; use PascalCase for classes. Match the frontend’s two-space indentation, single quotes, and semicolons. Use PascalCase for React components and camelCase for variables and handlers. TypeScript strict mode is enabled. Ruff is available; no automatic formatter is configured.

## Testing Guidelines

Use pytest and FastAPI’s `TestClient`; name files `test_*.py` and functions `test_*`. Cover changed API behavior, validation, and worker transitions where applicable. Database integration tests require PostgreSQL. No coverage threshold or frontend test framework is configured. Run backend tests, lint, and the frontend build before requesting review.

## Commit & Pull Request Guidelines

This checkout has no Git metadata, so existing commit conventions cannot be verified. Use concise, imperative commit subjects. Pull requests should describe the change, link relevant issues, report validation commands and results, and include screenshots for UI changes. Explain migration or configuration changes explicitly.

## Configuration & Current Scope

Configure `DATABASE_URL` for the backend and `VITE_API_URL` for the frontend. Keep secrets out of source control; bundled database credentials are development-only. Extraction tasks currently fail with `NOT_IMPLEMENTED`; preserve that explicit behavior until extraction is implemented. Keep this unauthenticated development setup private.

## Product Context & Architecture Principles

This project is **Wayfaro** (`wayfaro`).

Tagline: Discover opportunities beyond borders.

Description: AI-powered Global Job Discovery & Work Eligibility Intelligence.

Wayfaro serves international job seekers; opportunity verification remains the primary differentiator.

The primary UX is CV Analysis-first: compare pasted CV and JD text with exact supporting evidence before optional CV saving. Discovery remains a secondary flow for analyzing other jobs. Career Fit and Work Eligibility are separate; the current phase does not assess visas or work eligibility.

Career transition analysis is an optional feature, not a requirement for every user.

### Core Principles

- Keep job discovery, extraction, eligibility verification, and ranking as separate responsibilities.
- Use provider-independent ATS connectors. Start with Greenhouse and allow additional providers later.
- Preserve original job descriptions, source identifiers, and source URLs.
- Never infer visa sponsorship, work authorization, or remote-work eligibility from missing information.
- Distinguish `ELIGIBLE`, `UNKNOWN`, and `INELIGIBLE`. Missing evidence must not automatically produce `INELIGIBLE`.
- Keep eligibility decisions separate from career-fit ranking scores.
- Preserve supporting evidence and explicitly identify missing or conflicting information.
- Do not apply automatic country-based ranking bonuses or penalties.
- Keep career transition analysis optional and configurable per user.
- Preserve profile and analysis version history when implementing AI analysis.

### Development Workflow

- Inspect the existing repository before proposing changes.
- Present an implementation plan and wait for approval before modifying files.
- Reuse existing models, migrations, routes, and worker infrastructure where possible.
- Implement one milestone at a time.
- Add tests for new behavior and relevant failure cases.
- Do not introduce Redis, Celery, or unnecessary infrastructure.
- Never claim tests passed unless they were actually executed.
- Report changed files, test results, and remaining limitations after implementation.

### Current Milestone

CV Analysis-first Phase 1: backend-only text CV/JD matching through Gemini, anonymous ownership,
exact source evidence, MATCHED/UNVERIFIED, expiring private data and PostgreSQL worker integration.
Keep Greenhouse, Discovery and manual ingestion. Do not publish private analysis JDs as JobListing.
No total score, confirmed CV_GAP/SKILL_GAP, eligibility analysis, CV permanent storage/versioning,
React redesign, recommendation or PDF parsing in this phase. Work Eligibility stays NOT_ASSESSED.
Never put CV/JD text in URLs, logs or background job payloads. Existing job_extract/job_analyze
remain NOT_IMPLEMENTED; use the separate cv_compare task. Do not modify prior migration revisions.
