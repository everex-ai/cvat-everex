# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CVAT (Computer Vision Annotation Tool) is an interactive video and image annotation tool for computer vision. This is the **Everex fork** which has removed 3D annotation support and serverless AI functions. It's a full-stack application with:
- **Backend**: Django REST API with PostgreSQL, Redis (inmem + ondisk), ClickHouse for analytics
- **Frontend**: React/Redux single-page application with TypeScript
- **Workers**: Background RQ workers for import, export, annotation, webhooks, quality reports, consensus, chunks, and utils (cleaning)
- **Infrastructure**: Docker Compose deployment with Traefik reverse proxy, OPA for authorization

### Removed Features (Everex Fork)
- 3D annotation support (`cvat-canvas3d` package removed)
- Serverless AI/ML functions (`lambda_manager` app removed)
- Point cloud annotation formats

## Git Workflow

- **GitHub repo**: `everex-ai/mlops-imagelab` (renamed from `everex-ai/cvat-everex`). The `origin` remote may still use the old URL — `git push`/`pull` follow GitHub's redirect, but `gh pr create` fails against the old name; pass `-R everex-ai/mlops-imagelab` or update the remote URL.
- **Working branch**: `main` (Everex PRs target this branch). The GitHub default branch (`origin/HEAD`) is `develop`, inherited from upstream — always pass `--base main` explicitly when creating PRs.
- **Upstream**: `https://github.com/cvat-ai/cvat.git` (official CVAT repo)
- **Git hooks**: Lefthook runs `lint-staged` on pre-commit for `*.{js,jsx,ts,tsx}` files

## Build and Development Commands

### Docker-based Development (Recommended)
```bash
# Start full development stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Rebuild and start (after code changes)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Run on a local workstation at http://localhost:8081 — add the local override
# (untracked docker-compose.local.yml: re-points prod bind mounts to ~/cvat-everex-data,
# rewrites Traefik Host rules and CSRF origins for localhost, remaps the export
# worker debug port 9092 → 127.0.0.1:9192 to avoid collisions)
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.local.yml up -d
```

`deploy.sh` is the **production-host** deploy script (runs `git pull`, sets `CVAT_VERSION=dev`, rebuilds the stack) — do not run it on a local machine.

**Important — the base `docker-compose.yml` is pinned for production deployment, not localhost.** Traefik routes by `Host` header (`cvat-everex.mora.center` / `192.168.1.101`) on port `8081` (→ container `8080`); plain `http://localhost:8081` will NOT reach the UI without the matching `Host` header. Traefik admin maps `8091` (→ `8090`) but its dashboard entrypoint is commented out. To reach the UI from a browser, use `docker-compose.local.yml` (above), send the right `Host` header, add a hosts-file entry, or run the UI dev server (`yarn start:cvat-ui` on `localhost:3000`). Production volumes bind-mount to `/mnt/ssd/cvat_latest/`.

### Container Naming Convention
All Everex containers (and Compose service keys) use the `_everex` suffix: `cvat_server_everex`, `cvat_ui_everex`, `cvat_db_everex`, `cvat_redis_inmem_everex`, `cvat_redis_ondisk_everex`, etc. Use these exact names with `docker exec`/`docker logs` and as the service name for `docker compose run`. The Compose project name is `cvat-everex`, so the actual Docker network is `cvat-everex_cvat_everex` (verify with `docker network ls`) — use that for `docker network` / `--network` commands. The server image is `cvat/server:${CVAT_VERSION:-v2.52.0}` (there is no `:dev` tag — the dev override rebuilds this same tag).

### Frontend Development
```bash
# Install dependencies (uses yarn workspaces, requires Yarn 4.9.2 via corepack)
corepack enable yarn
yarn --immutable

# Build all frontend packages (order matters due to dependencies)
yarn build:cvat-data
yarn build:cvat-core
yarn build:cvat-canvas
yarn build:cvat-ui

# Start UI dev server (runs on localhost:3000, connects to API at localhost:7000)
yarn start:cvat-ui

# Custom host/port for UI dev server
CVAT_UI_HOST=0.0.0.0 CVAT_UI_PORT=3001 yarn start:cvat-ui

# Type checking
yarn workspace cvat-ui run type-check
yarn workspace cvat-core run type-check

# Lint frontend
yarn run eslint .
```

### Backend Commands (run against the running stack)
Use the `_everex` service/container names — bare `cvat_server` does not exist in this fork.
```bash
# Run Django tests (one-off container)
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm cvat_server_everex python manage.py test cvat/apps

# Make/check migrations (against the running container)
docker exec cvat_server_everex python manage.py makemigrations --check
docker exec cvat_server_everex python manage.py migrate

# Generate API schema
docker exec cvat_server_everex python manage.py spectacular > cvat/schema.yml

# Create superuser
docker exec -it cvat_server_everex python manage.py createsuperuser
```

### SDK Generation
```bash
pip3 install -r cvat-sdk/gen/requirements.txt
./cvat-sdk/gen/generate.sh
```

## Testing

### Python Tests (REST API, SDK, CLI)
```bash
# Install test dependencies
pip install -r tests/python/requirements.txt -e './cvat-sdk[masks,pytorch]' -e ./cvat-cli

# Run all Python tests
pytest tests/python/

# Run specific test file
pytest tests/python/rest_api/test_tasks.py

# Run tests matching pattern
pytest tests/python/ -k "test_task_data"

# With coverage
pytest tests/python/ --cov --cov-report=json
```

### E2E Tests (Cypress)
```bash
cd tests
yarn --immutable

# Run Cypress tests
npx cypress run --browser chrome --spec 'cypress/e2e/actions_tasks/**/*.js'
```

### OPA Authorization Tests
```bash
python cvat/apps/iam/rules/tests/generate_tests.py
docker compose run --rm cvat_opa_everex test cvat/apps/*/rules
```

## Linting

### Python
```bash
# Black formatter
black --check --diff .

# isort
isort --check --diff --resolve-all-configs .

# Pylint
pylint -j0 .

# Bandit security scanner
bandit -a file --ini .bandit --recursive .

# Typos spell checker
typos
```

### JavaScript/TypeScript
```bash
yarn run eslint .
yarn run stylelint '**/*.css' '**/*.scss'
npx remark --quiet --frail -i .remarkignore .
```

## Architecture

### Frontend Package Structure (Yarn Workspaces)
- `cvat-data/` - Data parsing utilities (video frames, image archives)
- `cvat-core/` - API client library, business logic, models
- `cvat-canvas/` - 2D annotation canvas (SVG-based, uses svg.js)
- `cvat-ui/` - React application with Redux state management

Dependencies flow: `cvat-data` <- `cvat-core` <- `cvat-canvas` <- `cvat-ui`

### UI State Management
Redux store slices (in `cvat-ui/src/reducers/`): auth, projects, tasks, jobs, about, formats, plugins, notifications, annotation, settings, shortcuts, userAgreements, review, export, import, consensus, cloudStorages, organizations, webhooks, invitations, requests, serverAPI, navigation, bulkActions. Uses Redux Thunk middleware.

### UI Plugin System
The cvat-ui includes `plugins/sam` by default. Additional plugins via the `CLIENT_PLUGINS` environment variable (colon-separated paths). Plugins must export from `src/ts/index.tsx`.
```bash
CLIENT_PLUGINS=/path/to/plugin1:/path/to/plugin2 yarn start:cvat-ui
```

### Browser Support
Chrome >= 99, Firefox >= 110, >2% market share (no IE11)

### Backend Django Apps (`cvat/apps/`)
- `engine/` - Core models (Task, Job, Label, Shape), views, task creation, data handling
- `iam/` - Identity/access management, OPA authorization rules
- `organizations/` - Multi-tenant organization support
- `dataset_manager/` - Import/export in various annotation formats (COCO, YOLO, Pascal VOC, etc.)
- `quality_control/` - Annotation quality reports and ground truth management
- `consensus/` - Multi-annotator consensus merging
- `webhooks/` - External webhook integrations
- `events/` - Analytics events (stored in ClickHouse)
- `redis_handler/` - Redis data caching and storage utilities
- `access_tokens/` - Personal access token management
- `health/` - Health check endpoints
- `log_viewer/` - Log viewing utilities

### Key Backend Patterns
- Authorization via OPA (Open Policy Agent) with Rego rules in `cvat/apps/*/rules/`
- Background jobs via django-rq with specialized workers (import, export, annotation, etc.)
- Two Redis instances: inmem (cache/queue) and ondisk (kvrocks for persistent data)
- File uploads via TUS protocol for resumable uploads
- Server runs nginx + uvicorn (ASGI) via supervisord (`supervisord/server.conf`), workers run RQ via supervisord (`supervisord/worker.conf`) with custom worker class `cvat.rqworker.DefaultWorker`

### Settings
- `cvat/settings/base.py` - Base Django settings
- `cvat/settings/development.py` - Development overrides
- `cvat/settings/production.py` - Production settings
- `cvat/settings/testing.py` - Test settings

## Code Style

### Python
- Black formatter with 100 char line length
- isort for import sorting (profile: black)
- Target Python 3.10+

### TypeScript/JavaScript
- ESLint with Airbnb config
- 4-space indentation
- 120 char max line length
- Single quotes

## Debug Ports (docker-compose.dev.yml)
- Server: 9090
- Worker annotation: 9091
- Worker export: 9092
- Worker import: 9093
- Worker quality_reports: 9094
- Worker consensus: 9096

Set `CVAT_DEBUG_ENABLED=yes` environment variable to enable debugging.

## RQ Workers
This fork uses workers with `_everex` suffix:
- `cvat_worker_utils_everex` - Notifications/cleaning
- `cvat_worker_import_everex` - Data import
- `cvat_worker_export_everex` - Data export
- `cvat_worker_annotation_everex` - Annotation processing
- `cvat_worker_webhooks_everex` - Webhook delivery
- `cvat_worker_quality_reports_everex` - Quality report generation
- `cvat_worker_chunks_everex` - Chunk processing
- `cvat_worker_consensus_everex` - Consensus merging

## Local Development without Docker

VS Code launch configurations are provided in `.vscode/launch.json`:
- `server: django` - Run Django dev server on localhost:7000
- `server: RQ - *` - Individual RQ worker configurations (import, export, annotation, webhooks, quality reports, cleaning, chunks, consensus)
- `server: debug` - Compound configuration to run all services together
- `server: REST API tests` / `sdk: tests` / `cli: tests` - Test runners

Prerequisites for local development: PostgreSQL, Redis instances must be accessible (can use Docker Compose services with exposed ports from `docker-compose.dev.yml`).

## Package-Specific Documentation

Each frontend package and SDK has its own CLAUDE.md with detailed architecture:
- `cvat-data/CLAUDE.md` - Video/image decoding with H.264 (Broadway.js) and zip archives
- `cvat-core/CLAUDE.md` - API client library, plugin system, session management
- `cvat-canvas/CLAUDE.md` - 2D SVG-based annotation canvas (MVC pattern, handler classes)
- `cvat-sdk/CLAUDE.md` - Python SDK with auto-generated OpenAPI client
- `cvat-cli/CLAUDE.md` - CLI tool command structure and authentication
