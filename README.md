# Wayfaro

Discover opportunities beyond borders.

**AI-powered Global Job Discovery & Work Eligibility Intelligence**

Repository name: `wayfaro`. CV Match Engine backend is implemented; eligibility intelligence remains a planned feature. React + TypeScript, FastAPI, PostgreSQL, and a separate database-backed worker.

## Run locally

Prerequisite: Docker Desktop / Docker Engine with Compose.

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

Paste a job posting (at least 30 characters) in the frontend. It creates a `job_listings` record and a `background_jobs` record in the same transaction. **The worker intentionally marks the task as `failed` with `NOT_IMPLEMENTED` because extraction is Phase 2.** No LLM calls or rankings are implemented yet.

To inspect tasks:

```bash
curl http://localhost:8000/api/v1/tasks/<task_id>
```

## Tests

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=. pytest -q tests
```

Frontend build:

```bash
cd frontend
npm install
npm run build
```

## Current scope and next steps

Implemented: app shell, API health, text job ingestion, transactional queue insertion, worker claim, ATS synchronization with retries and renewable leases, explicit unsupported-task failure, core schema, migrations, CI skeleton.

CV Match Engine의 비공개 텍스트 분석은 구현했습니다. 공개 job_extract/job_analyze, eligibility, ranking, feedback, applications, posting stale detection, deployment auth는 아직 구현하지 않았습니다. Do not expose this development setup publicly. Local database credentials are development-only.

Before production, add secure authentication, rate limiting, secrets management, database backup, and operational monitoring.

## ATS foundation (incremental implementation)

ATS 스키마, Greenhouse Connector, Source Synchronization Service와 PostgreSQL Worker 연동을 구현했습니다. Discovery API와 React 탐색 UI도 구현했습니다.
Revision `0001` is frozen to the original schema; `0002` adds ATS sources, nullable
posting metadata, and source synchronization run history while preserving manual
postings. Apply migrations with `cd backend && alembic upgrade head` after setting
`DATABASE_URL` for the intended development database. Do not reset the database.

The connector uses the public Greenhouse Job Board API with `content=true` and
preserves raw records. It performs one request per board, reports malformed records,
and exposes retryable failures handled by the worker. It does not call LLMs.

Run foundation checks from `backend/`:

```bash
PYTHONPATH=. pytest -q tests
ruff check app tests --select E4,E7,E9,F
```

Migration tests require `TEST_DATABASE_URL` pointing to a **dedicated PostgreSQL
test database**. They create randomly named schemas, test both fresh and existing
schemas containing manual data, and remove only those generated test schemas.
Without this variable, database tests skip. Never use the development database
for these tests. External HTTP calls are mocked in connector tests.

### Isolated migration verification

Install dependencies into the repository's virtual environment (no global install):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
```

From the repository root, start a disposable PostgreSQL container independent of
Compose. It uses temporary storage and never mounts the development volume:

```bash
wayfaro_test_container=$(docker run --rm -d \
  --tmpfs /var/lib/postgresql/data:rw \
  -e POSTGRES_USER=wayfaro_test \
  -e POSTGRES_PASSWORD=local-test-only \
  -e POSTGRES_DB=wayfaro_test \
  -p 127.0.0.1:55432:5432 postgres:16-alpine)
# Check readiness; repeat this command if PostgreSQL is still starting.
docker exec "$wayfaro_test_container" pg_isready -U wayfaro_test -d wayfaro_test
```

After readiness succeeds, run from the repository root:

```bash
TEST_DATABASE_URL=postgresql+psycopg://wayfaro_test:local-test-only@127.0.0.1:55432/wayfaro_test \
  PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests
.venv/bin/ruff check backend/app backend/tests --select E4,E7,E9,F
# Stop only the disposable container created above when verification is finished.
docker stop "$wayfaro_test_container"
```

`test_migration_contract.py` compares every PostgreSQL CREATE TABLE clause and
column order in frozen revision `0001` with the original model snapshot without
requiring a database. Live tests exercise migration operations on a fresh schema
and on the original schema containing manual listing and queue records, compare
resulting models, and enforce source/listing uniqueness. They do not yet exercise
Alembic's version-table/CLI lifecycle or downgrade compatibility.

### 저장소 경로와 개발 환경

현재 프로젝트 경로는 `/Users/min/wayfaro`입니다. 가상환경을 새 경로에 재생성했으며 시스템 Python은 변경하지 않았습니다.
기존 DB 이름과 사용자 `jobmatcher`는 호환성을 위해 유지합니다.
Docker Compose는 디렉터리 이름으로 프로젝트와 볼륨 이름을 정하므로, 기존 개발 볼륨을 계속 사용할 때는
기존 프로젝트 이름을 `COMPOSE_PROJECT_NAME`으로 명시하세요. 개발 DB에 `docker compose down -v`를 실행하지 마세요.

### Source Synchronization Service와 Worker

기존 `JobSource`, `BackgroundJob`, `SourceSyncRun`, `JobListing` 모델 및 `0001`/`0002`를 재사용합니다.
동기화 단계에서는 추가 마이그레이션, Redis, Celery를 도입하지 않았습니다. Discovery API는 아래 단계에서 추가했습니다.
설정된 소스는 Python 서비스에서 작업 큐에 추가할 수 있습니다. 호출자가 트랜잭션을 소유합니다.

```python
from app.db.session import SessionLocal
from app.services.ingestion.sync import enqueue_source_sync

with SessionLocal.begin() as db:
    task_id = enqueue_source_sync(db, source_id, idempotency_key="optional-logical-request-key")
```

`source_id`는 기존 `job_sources` 행의 UUID이며 활성 Greenhouse 소스여야 합니다.
같은 idempotency key는 같은 논리 요청에만 재사용하세요. 주기적 동기화에는 새 key를 사용하거나 생략합니다.
소스 등록 API와 자동 스케줄러는 이번 범위에 포함하지 않습니다.
Worker 실행 명령은 기존과 같은 `python -m app.workers.runner`입니다.

- `source_sync`: Greenhouse 조회 후 ATS 식별자 `(provider, board_token, external_job_id)`로 Upsert합니다.
  기존 공고의 ID, 생성 및 최초 수집 시각을 유지하고 원본 JSON, URL, HTML과 텍스트 설명, 소스 수정 시각을 저장합니다.
  설명이 없으면 필수 `raw_text`는 빈 문자열로 저장하며 내용을 추측하지 않습니다.
- 부분 오류는 유효 공고를 저장하고 실행 상태 `partial` 및 원본 오류를 기록합니다.
  작업 자체는 `completed`입니다. 정상 실행은 `completed`, 실패 실행은 `failed`입니다.
  `jobs_updated`는 기존 식별자로 재수집된 공고 수이며 실제 내용이 바뀐 공고만을 뜻하지는 않습니다.
- 조회 전체 실패나 저장 트랜잭션 실패는 기존 공고를 보호합니다. 응답에서 사라진 공고도 삭제하거나 종료 처리하지 않습니다.
- PostgreSQL `SKIP LOCKED`로 작업을 분배하고, 소스별 session advisory lock으로 HTTP 조회부터 저장까지 직렬화합니다.
  HTTP 요청 중 데이터 트랜잭션을 유지하지 않습니다. lock 경합은 `SOURCE_BUSY` 재시도 대상으로 기록합니다.
- Lease는 300초, Heartbeat는 30초 간격입니다. DB의 `clock_timestamp()`로 만료를 검사하며,
  공고 저장 전과 완료 처리 전에 작업 행 잠금, Lease token, 만료 시각을 확인합니다.
  저장·실행 이력·작업 완료는 같은 트랜잭션입니다. 오래된 Worker 결과는 롤백합니다.
- 네트워크 오류 및 Connector의 재시도 가능 HTTP 오류는 기본 최대 3회 시도합니다.
  백오프는 5초부터 두 배씩 증가해 최대 1시간입니다. `Retry-After`는 백오프와 비교해 더 긴 대기를 사용하되 최대 24시간으로 제한합니다.
  영구 오류는 즉시 실패하며, Lease 만료 복구도 시도 한도를 적용하고 해당 실행 이력을 실패 처리합니다.
- `job_extract`, `job_analyze`는 계속 `NOT_IMPLEMENTED`로 실패합니다.

소스 advisory lock은 전용 DB 연결 하나를 작업 동안 사용하며 최종 저장도 같은 연결에서 처리합니다. Heartbeat는 별도 연결을 사용합니다.
직접 PostgreSQL 연결 또는 session pooling이 필요하며 transaction pooling과는 호환되지 않습니다.
정지한 프로세스가 DB 연결을 유지하면 소스 lock도 유지될 수 있으며 경합 작업은 시도 한도에서 실패할 수 있습니다.
현재 전체 보드 응답을 메모리에 담으며, 대규모 응답에서는 저장 시간과 Lease 설정을 재검토해야 합니다.

### 이번 단계 검증

`tests/test_source_sync.py`는 독립된 `TEST_DATABASE_URL`과 테스트별 무작위 스키마를 사용합니다.
반복 수집, 변경·부분 오류, 네트워크/API 실패, 재시도 한도, 동시 claim 및 소스 경합,
Heartbeat, Lease 만료·이전 token, 저장 롤백, 수동 등록 호환성을 검증합니다.
위의 독립 PostgreSQL 16 컨테이너 절차로 전체 테스트를 실행하세요.
개발 DB를 `TEST_DATABASE_URL`로 지정하지 마세요.

이전 동기화 단계는 사용자가 로컬 Mac 터미널의 독립 PostgreSQL 16 컨테이너에서 백엔드 테스트와
TypeScript/Vite 빌드를 성공적으로 검증했다고 보고했습니다. 테스트 컨테이너는 종료했으며 개발 DB는 변경하지 않았습니다.
아래 Discovery 단계의 검증 결과는 별도로 기록합니다.

## Discovery API + React UI

기존 `job_listings`를 ATS·수동 공고의 공통 데이터 접근 지점으로 유지합니다.
스키마·마이그레이션·Worker·수동 등록 API를 유지하며 AI 분석·취업 자격·비자·랭킹은 구현하지 않습니다.

### API

- `GET /api/v1/jobs`: `{items, page, page_size, total, total_pages, source_options}` 반환.
  `source_options`는 현재 필터와 무관하게 저장된 공고가 있는 소스 목록입니다.
- `GET /api/v1/jobs/{id}`: 목록 필드에 `raw_text`, `description_text`, `source_updated_at`을 추가합니다.
  없는 ID는 404, 잘못된 UUID는 422입니다.
- 기존 `POST /api/v1/jobs`, `GET /api/v1/tasks/{task_id}`는 유지합니다.
- `POST /api/v1/ingestions/sync`: 활성 소스의 `source_sync`를 큐에 등록합니다. 요청은 `{"source_id":"UUID"}`,
  응답은 HTTP 202와 `{task_id, source_id, status, status_url}`입니다. HTTP 요청에서 ATS를 직접 조회하지 않습니다.

목록·상세 공통 필드:
`id`, `title`, `company_name`, `location_text`, `department`, `origin` (`manual`/`ats`),
`source_id`, `provider`, `board_token`, `external_job_id`, `source_url`, `remote_mention`,
`created_at`, `published_at`, `ingested_at`, `updated_at`.
누락된 원본 정보는 null이며, 시각은 시간대가 포함된 ISO 8601입니다.
안전하지 않은 원본 URL은 DB 값을 바꾸지 않고 응답에서 null로 표시합니다.
원본 HTML·JSON은 DB에 보존하지만 공개 조회 응답에 포함하지 않습니다.
상세의 `raw_text`도 React의 일반 텍스트로만 렌더링합니다.

| 쿼리 | 의미 |
| --- | --- |
| `page`, `page_size` | 기본 1·20, 페이지 크기 1–100, 페이지 번호 최대 1,000,000 |
| `q` | 제목·회사·위치·설명의 대소문자 무시 부분 검색 |
| `location`, `country_text`, `region_text` | 위치 원문에 대한 부분 검색. 여러 조건은 AND |
| `source_id` | ATS 소스 UUID |
| `origin` | `manual` 또는 `ats`; 생략하면 전체 |
| `remote_mention` | `PRESENT`, `NOT_MENTIONED`, `UNKNOWN` |
| `sort` | `created_desc`(기본), `published_desc`, `updated_desc` |

검색 문자열은 최대 200자이며 `%`, `_`, 역슬래시는 일반 문자로 처리합니다.
목록 정렬에는 ID 보조 정렬과 NULLS LAST를 적용합니다. 게시일이 없다고 등록일로 대체하지 않습니다.
페이지 결과와 총 건수는 하나의 SQL 문으로 조회합니다. 페이지 이동 사이에 데이터가 바뀌면 offset의 위치도 달라질 수 있습니다.
범위를 벗어난 페이지는 200과 빈 `items`를 반환합니다.
전체 건수 집계와 부분 검색은 대규모 데이터에서 추가 인덱스·성능 검토가 필요합니다.

`remote_mention`은 **위치 원문만** 확인합니다.
영어 `remote`, `telecommute`, `telecommuting`, `work from home` 및 한국어 `원격`, `재택` 표현을 찾습니다.
`not remote`도 관련 표현을 언급하므로 PRESENT입니다. NULL·빈 위치·공백뿐인 위치는 UNKNOWN입니다.
이는 실제 원격근무 가능 여부나 해외 거주자의 근무 허용 여부를 의미하지 않습니다.
Rome만 있는 공고를 Italy로 자동 분류하거나, 수동 원문에서 국가·회사·비자를 추론하지 않습니다.

### 관리자 동기화 인증

서버의 `.env`에 `INGESTION_ADMIN_TOKEN`을 설정하세요. `.env.example`은 형식 안내이며 실제 비밀값을 포함하지 않습니다.
Compose는 이 변수를 API 컨테이너에만 전달합니다. 로컬 백엔드는 기존 설정의 `.env`를 읽습니다.
`VITE_*`에는 관리자 토큰을 넣지 마세요. React에는 관리자 동기화 호출 기능이 없습니다.
미설정·빈 토큰은 503, 인증 실패는 401, 없는 소스는 404, 비활성 소스 및 중복 키 충돌은 409,
잘못된 요청은 422입니다. 정상 인증에는 상수 시간 비교를 사용합니다.

```bash
# 관리자 터미널에서만 호출합니다. 토큰은 환경변수에 미리 설정하세요.
curl -X POST http://localhost:8000/api/v1/ingestions/sync \
  -H "Authorization: Bearer $INGESTION_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: source-sync-request-001' \
  -d '{"source_id":"기존 소스 UUID"}'
```

`Idempotency-Key`는 선택 사항이며 1–255자입니다. 기존 `background_jobs.idempotency_key` 고유 제약과
PostgreSQL `ON CONFLICT`를 사용하므로 동시 요청과 프로세스 재시작에도 같은 작업 ID를 반환합니다.
작업이 완료되었으면 응답의 `status`도 completed입니다. 다른 소스·작업에 같은 키를 사용하면 409입니다.
다시 수집하려면 새 키를 사용하거나 헤더를 생략하세요. 이 API는 소스를 생성하지 않습니다.
관리자 API 보호가 전체 애플리케이션 인증을 의미하지는 않으며 기존 개발 환경의 접근 범위는 유지하세요.

### React 화면

검색·필터·정렬·페이지·선택 공고(`job`)가 URL 쿼리에 반영됩니다.
새로고침·브라우저 뒤로/앞으로 이동을 지원하고 이전 요청은 AbortController로 취소합니다.
목록과 상세에 각각 로딩·오류·재시도를 제공하고, 빈 결과와 정보 없음 상태를 표시합니다.
데스크톱은 목록/상세 2열, 모바일은 1열입니다. 수동 등록은 하단 접이식 폼으로 유지하며
성공 시 목록을 갱신하고 등록한 공고의 상세를 표시합니다.
원본 링크는 http/https만 허용하고 새 탭에 noopener/noreferrer를 적용합니다.

### 검증 및 로컬 확인

이 단계의 Codex 실행 결과:

- pytest: **51 passed, 48 skipped, 1 warning**. PostgreSQL 의존 테스트 48개는 TEST_DATABASE_URL이 없어 건너뛰었습니다.
- Ruff: 통과.
- `npm run typecheck`, `npm run build`: 통과.
- Docker 소켓 접근 거부로 독립 PostgreSQL 컨테이너를 시작하지 못했습니다.
- SQL 생성은 PostgreSQL dialect로 별도 검사했지만 실제 PostgreSQL 실행을 대체하지 않습니다.
- React 정적 렌더링으로 URL 검색값 복원, 초기 로딩, HTML 이스케이프와 안전한 링크를 검사해 통과했습니다.
- 브라우저에서의 시각적·상호작용 점검은 이 환경에서 수행하지 못했습니다.
- 경고는 기존 Starlette TestClient의 httpx 사용 중단 예정 안내입니다.

전체 테스트는 위의 독립 PostgreSQL 컨테이너 절차로 실행하세요. 개발 DB를 TEST_DATABASE_URL로 사용하지 마세요.
공통 PostgreSQL fixture는 테스트별 임의 스키마만 생성·제거합니다.

UI를 개발 DB에 쓰기 없이 점검하려면 독립 컨테이너 실행 후 **모든 터미널에서 해당 테스트 DB URL을 명시**합니다.
아래는 저장소 루트에서 실행합니다. 먼저 TEST_DATABASE_URL이 독립 테스트 컨테이너 주소인지 확인하세요.

```bash
# 테스트용 DB의 스키마만 준비합니다.
: "${TEST_DATABASE_URL:?독립 테스트 DB 주소를 먼저 설정하세요}"
(cd backend && DATABASE_URL="$TEST_DATABASE_URL" ../.venv/bin/alembic upgrade head)
# API 터미널
: "${TEST_DATABASE_URL:?독립 테스트 DB 주소를 먼저 설정하세요}"
DATABASE_URL="$TEST_DATABASE_URL" .venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
# 별도 터미널
npm run dev --prefix frontend
```

http://localhost:5173 에서 빈 목록 → 수동 등록 → 상세 → 키워드 검색 → 뒤로 가기를 확인하세요.
이 테스트 DB에 설정된 ATS 소스가 있다면 관리자 동기화 API와 Worker로 공고를 수집할 수 있습니다.
Worker에도 `DATABASE_URL="$TEST_DATABASE_URL"`을 명시하세요.
API·Worker를 종료한 뒤 해당 임시 컨테이너만 종료합니다. 개발 볼륨을 제거하지 마세요.


## CV Analysis-first Phase 1 — 백엔드

이 단계는 React 화면을 바꾸지 않습니다. CV와 JD 텍스트를 비공개 임시 분석 API로 받고
Gemini 요구사항 추출 → CV 근거 비교 → 서버 검증을 실행합니다.
Greenhouse, Discovery, 공개 수동 공고 등록 및 source_sync는 유지합니다.
분석 JD를 공개 `job_listings`에 넣지 않으며 공개 분석·프로필 테이블도 변경하지 않습니다.
새 마이그레이션 `0003_cv_match.py`는 `analysis_sessions`, `cv_match_analyses`만 추가합니다.
기존 0001/0002는 수정하지 않았습니다. 기존 DB를 초기화하지 말고 승인한 DB에 정상 upgrade만 적용하세요.

### 서버 설정

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=
CV_MATCH_RETENTION_HOURS=24
CV_MATCH_COOKIE_SECURE=true
```

키와 모델은 모두 서버 환경변수로 명시해야 합니다. 미설정 시 생성 API는 503입니다.
모델은 Gemini generateContent API의 responseJsonSchema 구조화 출력을 지원하는 모델을 선택합니다. GEMINI_MODEL에는 모델 ID 또는 models/ 접두사를 포함한 ID를 지정할 수 있습니다.
API와 Worker 모두에 키·모델을 전달하세요. 프론트엔드 또는 VITE 변수에 넣지 않습니다.
기존 httpx로 공식 Gemini generateContent REST API를 호출하므로 추가 SDK 설치는 필요 없습니다.
API 키는 x-goog-api-key 헤더로만 전달하며 URL 쿼리에 넣지 않습니다.
QA Agent에서 사용하던 키를 서버 환경변수 GEMINI_API_KEY로 제공할 수 있습니다. 다른 프로젝트의 비밀 파일을 자동으로 읽거나 복사하지 않습니다.

기본 보관은 24시간(설정 가능 1–168시간), 익명 소유권 세션은 7일입니다.
기본 제한은 세션당 보관 중인 분석 10개, 전체 pending/processing 100개, 최근 24시간 전체 요청 200개입니다.
`CV_MATCH_SESSION_LIMIT`, `CV_MATCH_GLOBAL_PENDING_LIMIT`, `CV_MATCH_GLOBAL_DAILY_LIMIT`로 조정할 수 있습니다.
DB transaction advisory lock으로 제한 검사를 직렬화합니다. 삭제된 요청도 24시간 요청 한도에 포함합니다.
이는 비용 상한 자체가 아니므로 운영 시 공급자 예산 설정과 외부 요청 제한도 필요합니다.

HTTPS에서는 Secure 쿠키를 유지합니다. **독립 테스트 DB를 사용하는 로컬 HTTP 테스트에서만**
`CV_MATCH_COOKIE_SECURE=false`로 설정합니다.
허용 Origin은 `CV_MATCH_ALLOWED_ORIGINS` JSON 배열로 설정하며 CORS와 쓰기 요청에 함께 적용합니다.
기본은 localhost:5173 및 localhost:8000입니다. 브라우저 클라이언트는 credentials를 포함해야 합니다.
Origin 없는 curl 같은 클라이언트도 기존 세션의 생성·삭제에는 CSRF 토큰이 필요합니다.

### API 계약

1. `GET /api/v1/analyses/policy`: 외부 AI 전송·보관·삭제 안내, policy_version, 입력 제한을 반환합니다.
2. `POST /api/v1/analyses`: 명시적 동의와 정책 버전을 포함한 JSON 요청.
3. `GET /api/v1/analyses/{id}`: 소유 세션에 한해 pending/processing/completed/failed와 결과를 반환합니다.
4. `DELETE /api/v1/analyses/{id}`: 소유 세션·CSRF 검증 후 입력·결과 삭제와 작업 취소, 204 반환.
5. 기존 `GET /api/v1/tasks/{id}`: cv_compare 작업에만 추가 소유권 검사를 적용합니다.

생성 요청:

```json
{
  "cv_text": "30자 이상의 CV 원문",
  "jd_text": "30자 이상의 JD 원문",
  "consent": true,
  "policy_version": "cv-match-gemini-1"
}
```

문서별 30–40,000자, 요청 본문 350,000바이트 제한입니다.
원문 Unicode·줄바꿈은 정규화하지 않고 그대로 보존합니다.
consent는 실제 JSON boolean true여야 합니다. 첫 요청에서 회원가입 없이
HttpOnly 소유권 쿠키와 별도 CSRF 쿠키를 발급합니다. DB에는 토큰 해시만 저장합니다.
재요청·삭제에는 생성 응답의 csrf_token을 `X-CSRF-Token`으로 전달하세요.
같은 브라우저의 쿠키가 사라지면 익명 분석을 복구할 수 없습니다.

202 응답:

```json
{
  "analysis_id": "uuid",
  "task_id": "uuid",
  "status": "pending",
  "status_url": "/api/v1/analyses/uuid",
  "expires_at": "ISO 8601 timestamp",
  "csrf_token": "browser-session-csrf-token"
}
```

조회 응답은 `{analysis_id, task_id, status, expires_at, result, error}`입니다.
소유권 불일치·삭제·만료는 404, 동의/입력 오류는 422, 크기 초과는 413,
CSRF·Origin 오류는 403, 한도 초과는 429, LLM 미설정은 503입니다.
비공개 응답은 no-store이며 검증 오류에 문서 입력값을 반사하지 않습니다.
입력·결과·토큰은 로그에 출력하지 않으며 Worker payload는 analysis_id뿐입니다.
CV/JD를 URL 쿼리나 shell 명령 인자에 넣지 마세요.

### 결과와 근거 검증

`result`의 Pydantic 계약:

- `schema_version`, `requirements`, `assessments`, `excluded_eligibility_evidence`
- `cv_suggestions`, `matched_count`, `unverified_count`
- `score: null`, `work_eligibility: NOT_ASSESSED`
- `limitations`, `provider`, `model`, `prompt_version`

요구사항은 필수 REQUIRED·우대 PREFERRED·UNSPECIFIED를 구분합니다.
근거는 `{start,end,quote}`이며 Python Unicode code point의 [start,end) 위치입니다.
브라우저의 UTF-16 인덱스와는 다르므로 향후 UI 연결 시 변환이 필요합니다.
서버가 `원문[start:end] == quote`를 검사하고 범위·중복 ID·요건별 평가 누락도 검사합니다.
MATCHED에는 적어도 하나의 유효한 CV 근거가 필요합니다.
확인되지 않은 항목은 UNVERIFIED입니다. CV_GAP/SKILL_GAP·점수·취업 자격 판정은 허용하지 않습니다.

개선 제안은 정확한 기존 근거를 드러내거나 추가 경험을 확인하는 서버 템플릿으로 제한합니다.
모델의 자유 서술 rationale는 사용자 경력을 근거 없이 단정할 수 있어 결과에 그대로 저장하지 않고
판정에 따른 보수적인 설명으로 대체합니다. 자동 CV 문장 작성은 하지 않습니다.
원문 인용의 정확성이 의미적 적합성이나 JD 추출의 완전성을 보장하지는 않습니다.
작은 언어모델 평가 데이터셋과 사람의 검토가 추가로 필요합니다.

### Worker·재시도·삭제

기존 큐의 별도 `cv_compare` 작업을 처리합니다. 기존 job_extract/job_analyze의 NOT_IMPLEMENTED는 유지합니다.
HTTP 호출 중 DB 트랜잭션을 유지하지 않고 기존 Heartbeat가 Lease를 연장합니다.
각 모델 호출 직전과 결과 저장 시 소유 세션·만료·작업 Lease를 확인합니다.
삭제는 task → analysis 순서로 잠금을 얻고 Lease를 취소하므로 늦은 Worker 결과가 다시 저장되지 않습니다.
네트워크·일시 HTTP 오류·잘못된 구조·인용 불일치는 기존 시도 한도/백오프를 적용합니다.
Retry-After도 적용하며 인증·영구 HTTP 오류·모델 거부는 즉시 최종 실패합니다.
실패 메시지는 원문이나 공급자 응답 대신 오류 코드만 기록합니다.
재시도는 파이프라인 전체를 다시 실행하므로 모델 호출 비용이 중복될 수 있습니다.

만료 시 즉시 API 조회와 다음 모델 호출을 차단합니다. Worker는 60초 간격으로 최대 100건씩 정리합니다.
Worker가 중단되어 있거나 백로그가 크면 물리 삭제는 지연될 수 있습니다.
독립된 정리 명령도 제공합니다(실행 대상 DATABASE_URL을 반드시 확인하세요):

```bash
PYTHONPATH=backend .venv/bin/python -m app.services.matching.cleanup
```

삭제 후 입력·결과 DB 행을 제거하고 작업 payload/result_ref를 비웁니다. 비식별 작업 tombstone은 남습니다.
진행 중인 외부 요청·프로세스 메모리를 즉시 회수하거나 이미 전송한 문서를 되돌릴 수는 없습니다.
Gemini 데이터 사용·보관 조건은 계정과 서비스 이용 조건에 따라 달라집니다. 무보관이나 학습 제외를 보장하지 않습니다.
[Gemini 공식 약관](https://ai.google.dev/gemini-api/terms)을 실제 운영 계정 조건과 함께 확인하세요.
Gemini에 OpenAI 전용 store 파라미터를 보내거나 같은 보관 정책이라고 가정하지 않습니다.
DB·백업 암호화 및 백업 삭제 정책은 운영 환경에서 별도로 구성해야 합니다.

### 검증과 실제 API 호출

결정적 단위 테스트는 외부 통신 없는 mock LLM과 httpx.MockTransport를 사용합니다.
실제 PostgreSQL 테스트는 별도 파일이며 독립 TEST_DATABASE_URL이 없으면 건너뜁니다.

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/test_match_engine.py
# 독립 PostgreSQL 컨테이너 주소를 설정한 경우에만 실행하세요.
: "${TEST_DATABASE_URL:?독립 테스트 DB URL을 먼저 설정하세요}"
PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/test_match_postgres.py backend/tests/test_migrations.py
```

실제 Gemini 호출은 별도 opt-in 합성 데이터 테스트입니다. 키/모델이 없으면 건너뜁니다.
서버 환경 또는 저장소 루트의 비공개 .env에 GEMINI_API_KEY와 GEMINI_MODEL을 설정한 뒤 실행하세요.

```bash
RUN_GEMINI_SMOKE=1 PYTHONPATH=backend .venv/bin/python -m pytest -q backend/tests/test_match_live.py
```

이 테스트는 외부 요청을 하며 요금이 발생할 수 있습니다. DB는 사용하지 않습니다. 실제 사용자의 CV를 테스트에 넣지 않습니다.
현재 Codex 실행에서 실제 Gemini 호출은 하지 않았습니다(키 미설정).
PostgreSQL 컨테이너 시작도 Docker 소켓 권한으로 거부되어 실제 DB 통합 검증은 남아 있습니다.

HTTP API 전체 흐름을 확인하려면 위의 독립 테스트 컨테이너를 사용하세요.
그 DB에만 `alembic upgrade head`로 0003까지 적용한 뒤 API·Worker를 같은 DB로 실행합니다.
요청 JSON은 별도 비공개 파일에 작성하고 `curl --data-binary @파일경로`로 전송하세요.
처음에는 `curl -c 쿠키파일`로 쿠키를 저장하고, 이후 `curl -b 쿠키파일`과
`X-CSRF-Token`을 사용합니다. 생성된 status_url을 polling하고 완료 후 DELETE로 정리합니다.
쿠키파일과 입력 파일도 개인정보이므로 저장소에 추가하지 말고 점검 후 삭제하세요.


### Gemini 전환 호환성

새 분석은 provider=gemini이며 기존 provider=openai 결과도 조회할 수 있습니다.
저장된 JSON과 PostgreSQL 레코드, 마이그레이션은 수정하지 않습니다.
새 동의 정책 버전은 `cv-match-gemini-1`입니다. 기존 `cv-match-1`로 새 요청을 보내면 422입니다.
이전 정책의 pending 작업은 Gemini로 전송하지 않고 CONSENT_RENEWAL_REQUIRED 최종 실패로 처리합니다.
동의 갱신은 기존 행을 덮어쓰지 않고 새 정책으로 새 분석을 생성하는 방식입니다.
이전 입력과 결과에는 기존 만료·삭제 정책이 계속 적용됩니다.

Gemini 요청은 systemInstruction과 user contents를 분리하며 generationConfig에
responseMimeType=application/json과 Pydantic responseJsonSchema를 전달합니다.
모델 출력 이후 Pydantic과 기존 인용·오프셋 검증을 그대로 실행합니다. 공급자가 일부 스키마 제약을 적용하지 않더라도 로컬 Pydantic 검증은 유지합니다.
사고(thought) 파트는 결과 JSON에서 제외합니다. 안전 차단은 재시도하지 않고,
MAX_TOKENS·잘못된 JSON 등은 기존 횟수 제한과 백오프를 적용합니다.
공급자 교체가 분석 정확도 향상을 의미하지는 않으며 실제 모델의 의미적 품질은 별도 검증이 필요합니다.

이번 Gemini 전환 실행 결과는 아래 최종 검증 기록을 참고하세요.

최종 검증 기록:

- 전체 pytest: **100 passed, 63 skipped, 1 warning**.
- 건너뛴 항목: PostgreSQL 필요 테스트 62개, 실제 Gemini opt-in 테스트 1개.
- Ruff, TypeScript, Vite 빌드: 통과.
- Compose YAML과 API·Worker 전용 Gemini 환경변수 배치: 검사 통과.
- Gemini mock HTTP로 두 단계 분석, 스키마·근거 검증, 차단·출력 중단·재시도,
  키 로그 미노출, 기존 결과 호환성과 동의 정책 변경을 검사했습니다.
- 기존 결과 조회와 대기 작업 동의 검사의 실제 PostgreSQL 동작은 미검증입니다.
- 실제 Gemini 호출 및 모델별 구조화 출력 호환성·분석 품질도 미검증입니다.
- 키와 모델이 현재 환경에 설정되지 않았으며 QA Agent의 비밀 파일은 읽거나 복사하지 않았습니다.

### Gemini HTTP 오류·타임아웃 진단

Gemini 요청에서 `candidateCount`를 제거했습니다. 응답은 기존과 같이 단일 후보만 허용합니다.
`responseJsonSchema`와 모든 Pydantic 제약(`maxItems`, `minItems`, 문자열 길이, 숫자 범위 등)은 변경하지 않았습니다.
Pydantic 결과 검증과 원문 인용·위치 검증도 유지합니다.

`MatchError` 문자열과 Worker 로그·비공개 분석 응답의 `error`에 안전한 진단을 추가합니다.

```text
code=LLM_HTTP_ERROR http_status=400 error_type=HTTP_BAD_REQUEST stage=extraction
code=LLM_READ_TIMEOUT error_type=READ_TIMEOUT stage=comparison
```

- HTTP 실패: `code=LLM_HTTP_ERROR`, 숫자 상태와 그 상태만으로 분류한 오류 유형.
  예: HTTP_UNAUTHENTICATED(401), HTTP_PERMISSION_DENIED(403), HTTP_RATE_LIMITED(429), HTTP_SERVER_ERROR(5xx).
- ReadTimeout: `LLM_READ_TIMEOUT` / READ_TIMEOUT. HTTP 응답이 없으므로 http_status를 넣지 않습니다.
- 그 외 타임아웃: `LLM_TIMEOUT` / TIMEOUT. 기타 요청 오류는 기존 LLM_NETWORK_ERROR / NETWORK_ERROR.
- 파이프라인의 MatchError에는 실패한 `extraction` 또는 `comparison` 단계를 추가합니다.
  근거 검증 오류 코드와 기존 재시도 여부·횟수 제한·백오프는 유지합니다.
- Worker의 `last_error`도 이 진단을 포함합니다. 기존 API의 dict[str,str] 계약을 유지하기 위해
  응답의 http_status는 문자열입니다. 예외의 http_status 속성은 정수입니다.
- HTTP 오류 응답의 JSON·메시지·원문·응답 헤더는 진단용으로 읽거나 기록하지 않습니다.
  API 키, CV, JD, 인증 헤더나 원본 예외 문자열도 포함하지 않습니다.

HTTP 400이라는 사실만으로 스키마 거절 또는 특정 요청 필드 오류를 확정하지 않습니다.
실제 실패 응답을 확인하지 않았으므로 candidateCount 제거가 보고된 실패를 해결했는지도 아직 미검증입니다.
스키마 단순화는 실제 오류 원인이 확인된 후 별도 최소 변경으로 처리합니다.

이번 작업의 검증은 `RUN_GEMINI_SMOKE=0`으로 실제 Gemini 테스트를 강제 비활성화했습니다.
실제 호출은 이번 작업에서 실행하지 않습니다.

이번 진단 개선의 실행 결과:

- `RUN_GEMINI_SMOKE=0` 전체 pytest: **119 passed, 64 skipped, 1 warning**.
- 건너뛴 항목은 PostgreSQL 필요 테스트 63개와 실제 Gemini 테스트 1개입니다.
- Ruff, TypeScript, Vite 빌드: 통과.
- 임시 PostgreSQL 컨테이너는 Docker 소켓 권한으로 시작하지 못했습니다. 개발 DB는 사용하지 않았습니다.
- 실제 Gemini 요청은 실행하지 않았으므로 보고된 HTTP 실패의 근본 원인과 해결 여부는 아직 확정하지 않았습니다.
