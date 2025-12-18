# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CVAT (Computer Vision Annotation Tool) is an interactive video and image annotation tool for computer vision. It's a full-stack application with:
- **Backend**: Django REST API with PostgreSQL, Redis (inmem + ondisk), ClickHouse for analytics
- **Frontend**: React/Redux single-page application with TypeScript
- **Workers**: Background RQ workers for import, export, annotation, webhooks, quality reports, consensus, chunks, and utils (notifications/cleaning)
- **Infrastructure**: Docker Compose deployment with Traefik reverse proxy, OPA for authorization

## Build and Development Commands

### Docker-based Development (Recommended)
```bash
# Start full development stack
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Rebuild and start (after code changes)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# With serverless functions (AI models)
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f components/serverless/docker-compose.serverless.yml up -d
```

### Frontend Development
```bash
# Install dependencies (uses yarn workspaces)
corepack enable yarn
yarn --immutable

# Build all frontend packages
yarn build:cvat-data
yarn build:cvat-core
yarn build:cvat-canvas
yarn build:cvat-canvas3d
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

### Backend Commands (inside container or with Django settings)
```bash
# Run Django tests
docker compose -f docker-compose.yml -f docker-compose.dev.yml run cvat_server python manage.py test cvat/apps

# Make/check migrations
docker run --rm cvat/server:dev python manage.py makemigrations --check
docker run --rm cvat/server:dev python manage.py migrate

# Generate API schema
docker run --rm cvat/server:dev python manage.py spectacular > cvat/schema.yml

# Create superuser
docker exec -it cvat_server python manage.py createsuperuser
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

# Canvas 3D tests (requires headed mode)
npx cypress run --headed --browser chrome --config-file cypress_canvas3d.config.js
```

### OPA Authorization Tests
```bash
python cvat/apps/iam/rules/tests/generate_tests.py
docker compose run --rm cvat_opa test cvat/apps/*/rules
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
- `cvat-data/` - Data parsing utilities (video frames, point clouds)
- `cvat-core/` - API client library, business logic, models
- `cvat-canvas/` - 2D annotation canvas (SVG-based, uses svg.js)
- `cvat-canvas3d/` - 3D annotation canvas (Three.js-based)
- `cvat-ui/` - React application with Redux state management

Dependencies flow: `cvat-data` <- `cvat-core` <- `cvat-canvas/cvat-canvas3d` <- `cvat-ui`

### UI Plugin System
The cvat-ui supports plugins via the `CLIENT_PLUGINS` environment variable (colon-separated paths). The default SAM plugin is always included. Plugins must export from `src/ts/index.tsx`.
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
- `lambda_manager/` - Serverless function management for AI models
- `redis_handler/` - Redis data caching and storage utilities

### Key Backend Patterns
- Authorization via OPA (Open Policy Agent) with Rego rules in `cvat/apps/*/rules/`
- Background jobs via django-rq with specialized workers (import, export, annotation, etc.)
- Two Redis instances: inmem (cache/queue) and ondisk (kvrocks for persistent data)
- File uploads via TUS protocol for resumable uploads

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

## Local Development without Docker

VS Code launch configurations are provided in `.vscode/launch.json` for running the server and workers locally:
- `server: django` - Run Django dev server on localhost:7000
- `server: RQ - *` - Individual RQ worker configurations
- `server: debug` - Compound configuration to run all services together

Prerequisites for local development: PostgreSQL, Redis instances must be accessible (can use Docker Compose services with exposed ports from `docker-compose.dev.yml`).
