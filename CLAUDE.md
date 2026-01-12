# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference (System Reminders)

> **Current Goal**: When working on tasks, always maintain focus on the specific request. Use TodoWrite to track multi-step tasks.

> **Code Style**: Python (Black, type hints), TypeScript (ESLint, strict types), Korean comments for business logic.

> **Before Editing**: Always read the file first. Prefer editing existing files over creating new ones.

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
| GPU | NVIDIA A100-SXM4-40GB × 8 |

## Agent Workflow Guidelines

### Recommended Approach
1. **Explore First**: Use `Task` tool with `subagent_type=Explore` to understand the codebase before making changes
2. **Plan**: For complex tasks, use `/ultrathink` or break down into smaller steps with TodoWrite
3. **Execute**: Make incremental changes, commit frequently
4. **Verify**: Run tests after changes, check logs for errors

### Sub-Agent Usage
| Agent | When to Use |
|-------|-------------|
| `Explore` | Finding files, understanding architecture, searching code patterns |
| `Plan` | Designing implementation strategy for complex features |
| `Bash` | Git operations, running tests, server management |

### Context Management Tips
- **50+ tool calls**: Consider starting a new session
- **60% context usage**: Run `/compact` to summarize and free context
- **Repeated information**: Use this CLAUDE.md instead of re-explaining

## Development Commands

### Backend
```bash
# Development server (auto-reload)
python -m app.api.main --mode develop

# Production server
python -m app.api.main --mode product

# Install dependencies
pip install -r requirements-api.txt

# Check logs
tail -f logs/backend_$(date +%Y%m%d).log
```

### Frontend
```bash
cd kms-portal-ui

npm install          # Install dependencies
npm run dev          # Development server (port 3000)
npm run build        # Production build
npm run test:run     # Run tests
```

### Testing
```bash
# All tests
./scripts/run_local_tests.sh

# Backend only
python -m pytest tests/api/test_auth_endpoints.py -v

# Frontend only
cd kms-portal-ui && npm run test:run
```

## Architecture Quick Map

### Backend (`app/api/`)
```
app/api/
├── main.py              # Entry point, middleware setup
├── core/
│   ├── deps.py          # Dependency injection (94KB - main DI)
│   ├── config.py        # Settings from environment
│   └── security_middleware.py
├── routers/             # API endpoints (/api/v1/*)
├── services/            # Business logic
├── models/              # Pydantic schemas
├── adapters/            # External services (LLM, embedding)
└── agents/              # AI Agent system
    ├── orchestrator.py  # Agent routing & execution
    ├── parallel_executor.py  # Multi-agent tasks
    ├── types.py         # AgentContext, AgentResult
    └── adapters/        # Deep Agent integration
```

### Frontend (`kms-portal-ui/src/`)
```
src/
├── pages/               # Route components
├── components/          # Reusable UI
│   └── AgentChat/       # AI Agent chat interface
├── store/               # Zustand state management
├── hooks/               # Custom React hooks
├── i18n/                # Translations (en, ko, ja)
└── api/                 # Backend API clients
```

### Key Patterns
1. **Query Router**: Auto-classifies queries → VECTOR, GRAPH, HYBRID, CODE
2. **Hexagonal Architecture**: Ports/adapters for external services
3. **Deep Agent**: LangGraph-based agents with tool calling
4. **Cookie + Header Auth**: JWT via HttpOnly cookie or Authorization header

## Common Tasks Cheatsheet

### Adding a New API Endpoint
1. Create route in `app/api/routers/`
2. Add service logic in `app/api/services/`
3. Register router in `app/api/main.py`
4. Add tests in `tests/api/`

### Adding a New Frontend Page
1. Create page component in `kms-portal-ui/src/pages/`
2. Add route in `App.tsx`
3. Add translations in `i18n/locales/*/`
4. Add navigation in `components/Sidebar.tsx`

### Debugging Agent Issues
```bash
# Check backend logs for agent execution
grep -E "\[.*Agent\]|\[Orchestrator\]" logs/backend_*.log | tail -50

# Test agent API directly
curl -X POST http://localhost:9000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "agent_type": "rag"}'
```

## Environment Setup

```bash
# Required in .env
JWT_SECRET_KEY=        # min 32 chars
ENCRYPTION_MASTER_KEY= # min 32 chars
ENCRYPTION_SALT=       # min 16 chars
NEO4J_PASSWORD=        # database password

# Optional
ADMIN_INITIAL_PASSWORD=  # creates admin at startup
ENABLE_DEEP_AGENT=true   # enable Deep Agent framework
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
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

## Coding Conventions

### Python
- Use type hints for all functions
- Docstrings for public methods (Korean OK for business logic)
- Async functions with `async def` for I/O operations
- Error handling: specific exceptions, not bare `except`

### TypeScript
- Strict mode enabled
- Prefer functional components with hooks
- Use Zustand for global state
- CSS modules or inline styles with CSS variables

### Git Commits
```
feat: Add new feature
fix: Bug fix
refactor: Code restructure
style: Formatting, CSS
chore: Build, deps, config
docs: Documentation only
```

## Troubleshooting

### Backend won't start
```bash
# Check if port is in use
netstat -ano | findstr :9000

# Check Python environment
python --version  # Should be 3.10+
pip list | grep fastapi
```

### Frontend build fails
```bash
# Clear cache and reinstall
cd kms-portal-ui
rm -rf node_modules package-lock.json
npm install
```

### Agent not responding
1. Check if LLM server is running (port 12800)
2. Check `OLLAMA_BASE_URL` in .env
3. Review logs: `grep "Agent" logs/backend_*.log`

## API Documentation

Interactive docs: http://localhost:9000/docs

Key endpoints:
- `POST /api/v1/auth/login` - User authentication
- `POST /api/v1/query` - RAG query with auto-routing
- `POST /api/v1/agent/stream` - AI Agent streaming
- `POST /api/v1/enterprise/stream` - Multi-agent orchestration
- `GET /api/v1/documents` - Document management

## Notes for Claude

### When exploring this codebase:
- Use `Task` tool with `Explore` agent for broad searches
- The main entry points are `app/api/main.py` and `kms-portal-ui/src/App.tsx`
- Agent system is in `app/api/agents/` - start with `orchestrator.py`

### When making changes:
- Always run tests after modifications
- Check both dark and light themes for UI changes
- Update translations in all 3 locales (en, ko, ja)
- Commit with descriptive messages following conventions above

### Context optimization:
- This file contains key info - avoid re-reading architecture docs
- For specific implementations, read the actual source files
- Use `git diff` to understand recent changes
