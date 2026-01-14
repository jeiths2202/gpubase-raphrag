# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

> **Code Style**: Python (Black, type hints), TypeScript (ESLint, strict types), Korean comments OK for business logic.

> **Before Editing**: Always read the file first. Prefer editing existing files over creating new ones.

> **Context Management**: 50+ tool calls → new session, 60% context → `/compact`

## Project Overview

**HybridRAG KMS** - A multilingual GPU-based Hybrid RAG (Retrieval-Augmented Generation) Knowledge Management System combining graph-based and vector-based retrieval with NVIDIA NIM containers.

### Tech Stack
| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.10+) |
| Frontend | React 18 + TypeScript + Vite |
| Database | Neo4j (Graph + Vector Index) |
| RAG LLM | Nemotron Nano 9B (port 12800) |
| Code LLM | Mistral NeMo 12B (port 12802) |
| Embeddings | NV-EmbedQA-Mistral 7B v2 (port 12801) |
| GPU | NVIDIA A100-SXM4-40GB x 8 |

## Project Structure

```
gpubase-raphrag/
├── app/api/                  # FastAPI backend (325 files) → see app/api/CLAUDE.md
├── kms-portal-ui/            # React frontend (132 files) → see kms-portal-ui/CLAUDE.md
├── tests/                    # Test suite (pytest)
├── scripts/                  # Utility scripts
├── docker/                   # Docker configuration
├── docs/                     # Documentation
├── migrations/               # DB migrations
└── logs/                     # Runtime logs
```

### Sub-CLAUDE.md Files
| Path | Content |
|------|---------|
| `app/api/CLAUDE.md` | Backend structure, API endpoints, services |
| `app/api/agents/CLAUDE.md` | Agent system, Deep Agents implementation |
| `kms-portal-ui/CLAUDE.md` | Frontend structure, components, stores |

## Development Commands

### Backend
```bash
python -m app.api.main --mode develop    # Dev server (auto-reload)
python -m app.api.main --mode product    # Production
pip install -r requirements-api.txt      # Install deps
```

### Frontend
```bash
cd kms-portal-ui
npm install          # Install dependencies
npm run dev          # Dev server (port 3000)
npm run build        # Production build
```

### Testing
```bash
./scripts/run_local_tests.sh                           # All tests
python -m pytest tests/api/test_auth_endpoints.py -v   # Backend
cd kms-portal-ui && npm run test:run                   # Frontend
```

## Port Allocations

| Port | Service |
|------|---------|
| 3000 | React frontend |
| 9000 | FastAPI backend |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |
| 12800 | Nemotron LLM |
| 12801 | Embeddings |
| 12802 | Mistral Code |

## Environment Setup

```bash
# Required in .env (see docs/SECURITY_KEYS_SETUP.md for key generation)
JWT_SECRET_KEY=        # min 32 chars - JWT signing
ENCRYPTION_MASTER_KEY= # min 32 chars - OAuth token encryption (Fernet/AES)
ENCRYPTION_SALT=       # min 16 chars - PBKDF2 key derivation salt
NEO4J_PASSWORD=        # database password

# Optional
ADMIN_INITIAL_PASSWORD=  # creates admin at startup
ENABLE_DEEP_AGENT=true   # enable Deep Agent framework
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

**보안 키 생성:** `docs/SECURITY_KEYS_SETUP.md` 참조

## Coding Conventions

### Python
- Type hints for all functions
- Async functions with `async def` for I/O
- Specific exceptions, not bare `except`

### TypeScript
- Strict mode enabled
- Functional components with hooks
- Zustand for global state

### Git Commits
```
feat: Add new feature
fix: Bug fix
refactor: Code restructure
style: Formatting, CSS
chore: Build, deps, config
docs: Documentation only
```

## Key Entry Points

| Component | File |
|-----------|------|
| Backend | `app/api/main.py` |
| Frontend | `kms-portal-ui/src/App.tsx` |
| Agent System | `app/api/agents/orchestrator.py` |
| Deep Agents | `app/api/agents/adapters/deep_agent_adapter.py` |

## Notes for Claude

- Use `Task` tool with `Explore` agent for broad searches
- Read sub-CLAUDE.md files for detailed context on specific areas
- Always run tests after modifications
- Update translations in all 3 locales (en, ko, ja) for UI changes
