# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HybridRAG KMS** - A multilingual GPU-based Hybrid RAG (Retrieval-Augmented Generation) Knowledge Management System combining graph-based and vector-based retrieval with NVIDIA NIM containers.

### Tech Stack
- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: Neo4j (Graph + Vector Index)
- **LLMs**:
  - Nemotron Nano 9B (RAG queries, port 12800)
  - Mistral NeMo 12B (code generation, port 12802)
- **Embeddings**: NV-EmbedQA-Mistral 7B v2 (port 12801)
- **GPU**: NVIDIA A100-SXM4-40GB × 8

## Development Commands

### Backend
```bash
# Start API server (development mode with auto-reload)
python -m app.api.main --mode develop

# Start API server (production mode)
python -m app.api.main --mode product

# Install dependencies
pip install -r requirements-api.txt
```

### Frontend
```bash
cd frontend

# Install dependencies
npm install

# Development server (port 3000)
npm run dev

# Production build
npm run build
```

### Testing
```bash
# Run all local tests (backend + frontend)
./scripts/run_local_tests.sh

# Backend only
./scripts/run_local_tests.sh backend

# Frontend unit tests only
./scripts/run_local_tests.sh frontend

# With coverage
./scripts/run_local_tests.sh --coverage

# Run single backend test file
python -m pytest tests/api/test_auth_endpoints.py -v

# Run single frontend test
cd frontend && npm run test:run -- src/__tests__/theme.test.tsx

# Playwright E2E tests
cd frontend && npx playwright test
```

## Architecture

### Backend Structure (`app/api/`)
```
app/api/
├── main.py              # FastAPI app entry, middleware, router registration
├── core/                # Framework infrastructure
│   ├── deps.py          # Dependency injection (AuthService, 94KB - main DI container)
│   ├── config.py        # Application settings from environment
│   ├── secrets_manager.py # Secret validation at startup
│   └── security_middleware.py # CSP, CORS, security headers
├── routers/             # API endpoint definitions (/api/v1/*)
├── services/            # Business logic layer
├── models/              # Pydantic models and database schemas
├── adapters/            # External service adapters (LLM, embedding, vision)
└── pipeline/            # Vision LLM orchestration
```

### Frontend Structure (`frontend/src/`)
```
frontend/src/
├── App.tsx              # Root component, routing, auth guards
├── pages/               # Page components (LoginPage, MainDashboard, KnowledgeApp)
├── components/          # Reusable UI (MindmapViewer, NodePanel, LanguageSelector)
├── services/api.ts      # Backend API client with auth interceptors
├── store/               # Zustand stores (authStore, preferencesStore)
├── hooks/               # Custom hooks (useTranslation, useLanguagePolicy)
├── i18n/                # Internationalization (en, ko, ja locales)
└── styles/              # CSS and theme tokens
```

### Key Design Patterns

1. **Query Router**: Automatic classification of queries into VECTOR, GRAPH, HYBRID, or CODE strategies based on multilingual keyword patterns and embedding similarity.

2. **Hexagonal Architecture**: Backend uses ports/adapters pattern for external services (LLM, embeddings, vector store, graph store).

3. **App Mode System**: `APP_ENV` controls develop/product behavior - logging verbosity, error details, token tracking.

4. **Cookie + Header Auth**: JWT tokens sent via HttpOnly cookies (preferred) or Authorization header (fallback).

## Environment Setup

Copy `.env.example` to `.env` and set required secrets:
```bash
# Required secrets (app fails without these)
JWT_SECRET_KEY=        # min 32 chars: openssl rand -base64 32
ENCRYPTION_MASTER_KEY= # min 32 chars
ENCRYPTION_SALT=       # min 16 chars
NEO4J_PASSWORD=        # database password

# Optional
ADMIN_INITIAL_PASSWORD= # creates admin user at startup
GOOGLE_CLIENT_ID=       # for Google OAuth
```

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

Key endpoint groups:
- `/auth/*` - Authentication (login, refresh, logout)
- `/query` - RAG queries with automatic strategy routing
- `/documents/*` - Document upload and management
- `/mindmap/*` - LLM-based concept extraction and visualization
- `/vision/*` - Vision LLM for image/chart analysis
- `/knowledge-article/*` - Knowledge registration workflow
- `/enterprise/*` - MFA, audit logs, collaboration

Interactive docs: `http://localhost:8000/docs`

## Testing Architecture

- **Backend tests** (`tests/`): Use mock adapters to avoid GPU/external dependencies
- **Frontend unit tests**: Vitest with React Testing Library
- **E2E tests**: Playwright for browser automation
- **Visual regression**: Snapshot testing for theme/accessibility

Mock services in `tests/mocks/` and `app/api/adapters/mock/` simulate LLM, embeddings, and database operations.

## Port Allocations

| Port  | Service                    |
|-------|---------------------------|
| 3000  | React frontend            |
| 8000  | FastAPI backend           |
| 7474  | Neo4j HTTP                |
| 7687  | Neo4j Bolt                |
| 12800 | Nemotron LLM (GPU 7)      |
| 12801 | NeMo Embeddings (GPU 4,5) |
| 12802 | Mistral Code LLM (GPU 0)  |
