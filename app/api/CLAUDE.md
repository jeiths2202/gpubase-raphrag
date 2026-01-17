# Backend CLAUDE.md

FastAPI 백엔드 상세 가이드입니다.

## Directory Structure

```
app/api/
├── main.py                   # Entry point, middleware setup
├── core/
│   ├── deps.py               # Dependency injection (105KB - main DI)
│   ├── config.py             # Settings from environment
│   ├── security_middleware.py
│   ├── cookie_auth.py        # HttpOnly cookie auth
│   ├── tracing.py            # E2E tracing
│   └── cache.py              # Caching layer
├── routers/                  # API endpoints (18 routers)
│   ├── agents.py             # AI agent orchestration
│   ├── query.py              # RAG query routing
│   ├── conversations.py      # Chat management
│   ├── documents.py          # Document ingestion
│   ├── admin.py              # Admin operations
│   ├── auth.py               # Authentication
│   ├── enterprise.py         # Multi-agent orchestration
│   ├── ims_chat.py           # IMS integration
│   ├── vision.py             # Image processing
│   └── enhancements.py       # Enhancement requests
├── services/                 # Business logic (40+ services)
│   ├── rag_service.py        # Core RAG pipeline
│   ├── auth_service.py       # Authentication
│   ├── conversation_service.py
│   ├── document_parser.py    # Multi-format parsing
│   └── enhancement_queue_manager.py
├── models/                   # Pydantic schemas (30+ models)
├── adapters/                 # External services
│   ├── langchain/            # LLM & embedding adapters
│   ├── ollama/               # Ollama integration
│   └── vision/               # OpenAI/Anthropic vision
├── agents/                   # AI Agent system → see agents/CLAUDE.md
├── chains/                   # LangChain pipelines
│   ├── rag_chain.py
│   └── retrieval_chain.py
├── repositories/             # Data access layer
├── connectors/               # External data sources
│   ├── confluence_connector.py
│   ├── github_connector.py
│   └── notion_connector.py
├── events/                   # Event-driven architecture
│   ├── event_bus.py
│   └── domain_events.py
└── ims_crawler/              # IMS system integration
```

## Key API Endpoints

| Endpoint | Method | 용도 |
|----------|--------|------|
| `/api/v1/auth/login` | POST | 사용자 인증 |
| `/api/v1/auth/register` | POST | 회원가입 |
| `/api/v1/query` | POST | RAG 쿼리 (auto-routing) |
| `/api/v1/query/stream` | POST | RAG 스트리밍 |
| `/api/v1/agent/stream` | POST | AI Agent 스트리밍 |
| `/api/v1/enterprise/stream` | POST | Multi-agent orchestration |
| `/api/v1/conversations` | GET/POST | 대화 관리 |
| `/api/v1/conversations/{id}/messages` | GET/POST | 메시지 관리 |
| `/api/v1/documents` | GET/POST | 문서 관리 |
| `/api/v1/ims/search` | POST | IMS 검색 |
| `/api/v1/enhancements` | POST | 기능 개선 요청 |
| `/api/v1/admin/users` | GET/POST | 사용자 관리 |

**API Docs**: http://localhost:9000/docs

## Core Components

### Dependency Injection (`core/deps.py`)
- 105KB의 메인 DI 컨테이너
- 모든 서비스 인스턴스화 및 의존성 주입
- `get_*` 함수들로 의존성 제공

### Authentication
- JWT + HttpOnly Cookie 기반
- `core/cookie_auth.py`: 쿠키 인증 로직
- `core/security_middleware.py`: 보안 미들웨어
- Header (`Authorization: Bearer`) 또는 Cookie 지원

### RAG Pipeline
```
Query → QueryClassifier → Router
           ↓
    VECTOR / GRAPH / HYBRID / CODE
           ↓
    RetrievalChain → GenerationChain
           ↓
        Response
```

## Key Patterns

1. **Query Router**: 쿼리 자동 분류 → VECTOR, GRAPH, HYBRID, CODE
2. **Hexagonal Architecture**: Ports/Adapters for external services
3. **Repository Pattern**: 데이터 접근 추상화
4. **Event-Driven**: Domain events via event bus

## Adding New Endpoint

1. `routers/` 에 라우터 생성 또는 기존 라우터에 추가
2. `services/` 에 비즈니스 로직 구현
3. `models/` 에 Pydantic 스키마 정의
4. `main.py` 에 라우터 등록 (새 라우터인 경우)
5. `tests/api/` 에 테스트 추가

```python
# routers/example.py
from fastapi import APIRouter, Depends
from app.api.core.deps import get_current_user

router = APIRouter(prefix="/example", tags=["example"])

@router.get("/")
async def get_example(user = Depends(get_current_user)):
    return {"message": "Hello"}
```

## Troubleshooting

### Backend won't start
```bash
netstat -ano | findstr :9000     # Check port usage
python --version                  # Should be 3.10+
pip list | grep fastapi           # Check dependencies
```

### Database connection issues
```bash
# Check Neo4j
curl http://localhost:7474

# Check PostgreSQL (if used)
psql -h localhost -U postgres -c "SELECT 1"
```

### Logging
```bash
# Check backend logs
tail -f logs/backend_$(date +%Y%m%d).log

# Filter specific logs
grep -E "\[ERROR\]|\[WARNING\]" logs/backend_*.log | tail -50
```

## Key Files Reference

| 작업 | 파일 |
|------|------|
| 새 라우터 추가 | `routers/*.py`, `main.py` |
| 비즈니스 로직 | `services/*.py` |
| 데이터 모델 | `models/*.py` |
| 외부 서비스 연동 | `adapters/*.py` |
| 데이터 접근 | `repositories/*.py` |
| 이벤트 처리 | `events/*.py` |
| Agent 시스템 | `agents/` → see `agents/CLAUDE.md` |
