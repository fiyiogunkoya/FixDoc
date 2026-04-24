# FixDoc SaaS Scaffolding Plan

## Context

FixDoc is a mature Python CLI tool (1,328 tests, 27 modules) for cloud engineers to capture and search infrastructure fixes. It stores data locally in JSON+Markdown at `~/.fixdoc/` and syncs via git. There is no backend, API, or web UI.

The goal is to scaffold the **project structure** for a SaaS version — framework configs, data models, API contracts, Docker Compose, and Makefile targets. No working features; just a solid foundation to build on incrementally.

**Stack decisions:**
- Backend: FastAPI (Python) — duplicated models (no shared package)
- Database: PostgreSQL via SQLAlchemy + Alembic
- Frontend: Next.js (React/TypeScript) + Tailwind CSS
- Auth: AWS Cognito (JWT verification on backend, Amplify on frontend)
- Deployment: AWS native (ECS/Fargate, RDS, CloudFront) — Terraform deferred to later
- Repo: Monorepo — new directories alongside existing CLI

## Directory Structure

```
FixDoc/
├── src/fixdoc/              # EXISTING (unchanged)
├── tests/                   # EXISTING (unchanged)
├── scenarios/               # EXISTING (unchanged)
├── fixdoc-web/              # EXISTING (unchanged)
│
├── backend/                 # NEW
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/.gitkeep
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── dependencies.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   └── cors.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── team.py
│   │   │   ├── fix.py
│   │   │   ├── pending_entry.py
│   │   │   ├── outcome.py
│   │   │   └── project.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── user.py
│   │   │   ├── team.py
│   │   │   ├── fix.py
│   │   │   ├── pending.py
│   │   │   ├── outcome.py
│   │   │   └── analyze.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── auth.py
│   │   │   ├── fixes.py
│   │   │   ├── search.py
│   │   │   ├── pending.py
│   │   │   ├── analyze.py
│   │   │   ├── outcomes.py
│   │   │   ├── teams.py
│   │   │   └── projects.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── fix_service.py
│   │   │   ├── search_service.py
│   │   │   ├── pending_service.py
│   │   │   ├── analyze_service.py
│   │   │   ├── outcome_service.py
│   │   │   ├── team_service.py
│   │   │   └── sync_service.py
│   │   └── repositories/
│   │       ├── __init__.py
│   │       ├── fix_repository.py
│   │       ├── pending_repository.py
│   │       ├── outcome_repository.py
│   │       ├── team_repository.py
│   │       └── project_repository.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       └── test_health.py
│
├── frontend/                # NEW
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.mjs
│   ├── Dockerfile
│   ├── .env.local.example
│   ├── .gitignore
│   ├── public/
│   │   └── .gitkeep
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   ├── globals.css
│       │   ├── (auth)/
│       │   │   ├── login/page.tsx
│       │   │   └── callback/page.tsx
│       │   ├── fixes/
│       │   │   ├── page.tsx
│       │   │   └── [id]/page.tsx
│       │   ├── pending/
│       │   │   └── page.tsx
│       │   ├── analyze/
│       │   │   └── page.tsx
│       │   ├── outcomes/
│       │   │   └── page.tsx
│       │   └── settings/
│       │       ├── page.tsx
│       │       └── team/page.tsx
│       ├── components/
│       │   ├── ui/
│       │   │   ├── Button.tsx
│       │   │   ├── Card.tsx
│       │   │   ├── Table.tsx
│       │   │   ├── Badge.tsx
│       │   │   ├── Input.tsx
│       │   │   └── Modal.tsx
│       │   ├── layout/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── Header.tsx
│       │   │   └── Footer.tsx
│       │   └── auth/
│       │       └── AuthGuard.tsx
│       ├── lib/
│       │   ├── api.ts
│       │   ├── auth.ts
│       │   └── utils.ts
│       ├── hooks/
│       │   ├── useAuth.ts
│       │   ├── useFixes.ts
│       │   └── usePending.ts
│       └── types/
│           ├── fix.ts
│           ├── pending.ts
│           ├── outcome.ts
│           └── api.ts
│
├── docker-compose.saas.yml  # NEW
├── .env.example             # NEW (root-level)
├── Makefile                 # UPDATED (add saas-* targets)
└── .gitignore               # UPDATED (add backend/frontend ignores)
```

## Backend Details

### pyproject.toml
- Name: `fixdoc-backend`, Python 3.9+
- Dependencies: fastapi, uvicorn[standard], sqlalchemy>=2.0, alembic, psycopg2-binary, pydantic>=2.0, pydantic-settings, python-jose[cryptography], httpx
- Dev: pytest, pytest-asyncio, httpx

### app/main.py — FastAPI app factory
- `create_app()` factory function
- Registers CORS middleware
- Includes all routers under `/api/v1` prefix
- Lifespan handler for DB pool setup/teardown

### app/config.py — Pydantic Settings
```python
class Settings(BaseSettings):
    database_url: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    cognito_region: str = "us-east-1"
    cors_origins: list[str] = ["http://localhost:3000"]
    environment: str = "development"
    debug: bool = False
    model_config = SettingsConfigDict(env_prefix="FIXDOC_")
```

### app/database.py
- SQLAlchemy `create_engine()` with pool config
- `SessionLocal` sessionmaker
- `Base` declarative base
- `get_db()` generator

### app/dependencies.py
- `get_db()` — yields DB session
- `get_current_user()` — decodes Cognito JWT, returns user dict
- `get_optional_user()` — returns None if no auth header

### app/middleware/auth.py
- `CognitoJWTVerifier` class
- Fetches JWKS from Cognito endpoint, caches keys
- `verify_token(token)` — decodes JWT, validates iss/aud/exp/token_use

### SQLAlchemy Models (7 tables)
- `users`: id (UUID), cognito_sub (unique), email, display_name, created_at, updated_at
- `teams`: id (UUID), name, slug (unique), owner_id (FK), created_at
- `team_members`: team_id, user_id, role (owner/member/viewer), joined_at
- `fixes`: mirrors CLI Fix fields + team_id, created_by_id, project_id. Index on content_hash, team_id
- `pending_entries`: mirrors CLI PendingEntry + project_id, created_by_id
- `outcomes`: mirrors CLI Outcome + project_id, created_by_id
- `projects`: id (UUID), name, slug (unique per team), team_id (FK), git_remote_url, created_at, created_by_id

### Pydantic Schemas
- `common.py`: PaginationParams, PaginatedResponse[T], ErrorResponse
- `fix.py`: FixCreate, FixUpdate, FixResponse, FixSearchParams
- `pending.py`: PendingEntryCreate, PendingEntryResponse, PendingBulkCreate
- `outcome.py`: OutcomeCreate, OutcomeApplyUpdate, OutcomeResponse
- `analyze.py`: AnalyzeRequest, AnalyzeResponse
- `user.py`: UserResponse, UserUpdate
- `team.py`: TeamCreate, TeamResponse, TeamMemberAdd, TeamMemberResponse

### API Routes (all `/api/v1`)
- `GET /health`, `GET /ready`
- `POST /auth/callback`, `POST /auth/refresh`, `GET /auth/me`
- `GET/POST /fixes`, `GET/PUT/DELETE /fixes/{id}`
- `GET /search`, `GET /search/similar`
- `GET/POST /pending`, `POST /pending/{id}/resolve`, `POST /pending/{id}/supersede`
- `POST /analyze`, `POST /analyze/k8s`
- `GET/POST /outcomes`, `PUT /outcomes/{id}/apply`, `GET /outcomes/{id}`
- `GET/POST /teams`, `GET/POST/DELETE /teams/{id}/members`
- `GET/POST /projects`, `PUT/DELETE /projects/{id}`

### Services (stub method signatures)
- `fix_service.py`: create_fix, get_fix, list_fixes, update_fix, delete_fix, search_fixes
- `search_service.py`: find_similar, search
- `pending_service.py`: create_entries, list_entries, resolve, supersede
- `analyze_service.py`: run_impact_analysis, run_k8s_analysis
- `outcome_service.py`: create_outcome, update_apply_result, list_outcomes
- `team_service.py`: create_team, add_member, remove_member, list_teams
- `sync_service.py`: push_fixes, pull_fixes

### Repositories (stub query methods)
- `fix_repository.py`: create, get_by_id, get_by_prefix, list_all, search, find_by_content_hash, update, delete, count
- `pending_repository.py`: create, list_by_project, find_by_context, update_status, remove
- `outcome_repository.py`: create, get_by_id, find_by_fingerprint, update_apply_result, list_all
- `team_repository.py`: create, get_by_id, get_by_slug, list_for_user, add_member, remove_member
- `project_repository.py`: create, get_by_id, list_for_team, update, delete

### Dockerfile
- Multi-stage: Python 3.11-slim
- Install deps, copy app, expose 8000
- CMD: `uvicorn app.main:create_app --host 0.0.0.0 --port 8000 --factory`

### Tests scaffold
- `conftest.py`: test DB fixture (SQLite in-memory), TestClient, mock auth user
- `test_health.py`: stub tests for /health and /ready

## Frontend Details

### package.json
- next 14, react 18, aws-amplify 6, axios
- Dev: typescript 5, tailwindcss 3, eslint, eslint-config-next

### Configuration
- `tsconfig.json`: strict mode, `@/*` path alias
- `next.config.ts`: API rewrites to backend, standalone output
- `tailwind.config.ts`: content paths, FixDoc brand colors (dark theme from fixdoc-web), custom fonts
- `postcss.config.mjs`: tailwindcss + autoprefixer

### Pages (App Router)
- `layout.tsx`: root layout with AuthProvider, Sidebar, Header
- `page.tsx`: dashboard stub (fix count, pending count, recent outcomes)
- `(auth)/login/page.tsx`: redirects to Cognito hosted UI
- `(auth)/callback/page.tsx`: handles OAuth callback
- `fixes/page.tsx`: search + paginated fix list stub
- `fixes/[id]/page.tsx`: fix detail stub
- `pending/page.tsx`: pending entries list stub
- `analyze/page.tsx`: plan upload + score display stub
- `outcomes/page.tsx`: outcomes list stub
- `settings/page.tsx`: user profile stub
- `settings/team/page.tsx`: team management stub

### Components
- `ui/`: Button, Card, Table, Badge, Input, Modal — Tailwind-styled
- `layout/`: Sidebar, Header, Footer
- `auth/`: AuthGuard (redirects unauthenticated users)

### Lib
- `api.ts`: axios instance, token injection interceptor, 401 redirect, typed API functions
- `auth.ts`: Amplify config, getCurrentUser, getAccessToken, signOut
- `utils.ts`: formatters, helpers

### Hooks
- `useAuth.ts`: auth state wrapper
- `useFixes.ts`: fetch/mutate fixes
- `usePending.ts`: fetch/mutate pending entries

### Types
- `fix.ts`, `pending.ts`, `outcome.ts`, `api.ts`: TypeScript interfaces mirroring Pydantic schemas

### Dockerfile
- Multi-stage: Node 20-alpine
- Install, build Next.js, run standalone
- Expose 3000

## Docker Compose + Dev Experience

### docker-compose.saas.yml
- `postgres`: PostgreSQL 16 Alpine, port 5432, healthcheck
- `backend`: builds from backend/Dockerfile, hot-reload volumes, connects to Postgres
- `frontend`: builds from frontend/Dockerfile, hot-reload volumes, proxies to backend

### .env.example
- `FIXDOC_DATABASE_URL`, `FIXDOC_COGNITO_*`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_COGNITO_*`

### Makefile additions
- `saas-up` / `saas-down`: start/stop Docker Compose
- `saas-db-migrate` / `saas-db-reset`: Alembic migrations
- `saas-test-backend` / `saas-test-frontend`: run tests
- `saas-lint` / `saas-fmt`: lint and format

### .gitignore additions
- `backend/__pycache__/`, `backend/.env`
- `frontend/node_modules/`, `frontend/.next/`, `frontend/.env.local`

## Implementation Steps

### Step 1: Backend foundation
Create `backend/` directory with:
- `pyproject.toml`
- `app/__init__.py`, `app/main.py`, `app/config.py`, `app/database.py`, `app/dependencies.py`
- `app/middleware/__init__.py`, `app/middleware/auth.py`, `app/middleware/cors.py`
- All `__init__.py` files for packages

### Step 2: Backend models
Create `app/models/`:
- `__init__.py` (imports all models for Alembic)
- `user.py`, `team.py`, `fix.py`, `pending_entry.py`, `outcome.py`, `project.py`

### Step 3: Backend schemas
Create `app/schemas/`:
- `common.py`, `user.py`, `team.py`, `fix.py`, `pending.py`, `outcome.py`, `analyze.py`

### Step 4: Backend routers
Create `app/routers/`:
- `health.py`, `auth.py`, `fixes.py`, `search.py`, `pending.py`, `analyze.py`, `outcomes.py`, `teams.py`, `projects.py`
- Each with endpoint stubs (raise NotImplementedError or return placeholder)

### Step 5: Backend services + repositories
Create `app/services/` and `app/repositories/`:
- All service and repository files with class/method stubs (pass bodies)

### Step 6: Alembic setup
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/.gitkeep`

### Step 7: Backend Dockerfile + tests
- `Dockerfile`
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_health.py`

### Step 8: Frontend foundation
- `package.json`, `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`, `postcss.config.mjs`
- `Dockerfile`, `.env.local.example`, `.gitignore`
- `src/app/layout.tsx`, `src/app/page.tsx`, `src/app/globals.css`

### Step 9: Frontend pages
- All page stubs under `src/app/`

### Step 10: Frontend components + lib + hooks + types
- All component, lib, hook, and type files

### Step 11: Docker Compose + DX
- `docker-compose.saas.yml`
- `.env.example`
- Update `Makefile` with saas-* targets
- Update `.gitignore`

## Verification

1. **Backend**: `cd backend && pip install -e . && python -c "from app.main import create_app; app = create_app(); print('OK')"` — app factory should create without errors
2. **Backend tests**: `cd backend && pytest tests/test_health.py` — health test should pass
3. **Frontend**: `cd frontend && npm install && npm run build` — Next.js should build without errors
4. **Docker Compose**: `docker compose -f docker-compose.saas.yml up --build` — all 3 services should start
5. **Existing CLI**: `pytest` (from root) — all 1,328 tests still pass (nothing changed)
