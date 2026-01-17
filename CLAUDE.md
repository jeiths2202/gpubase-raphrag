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

## Windows Tool Paths

| Tool | Path |
|------|------|
| GitHub CLI | `"/c/Program Files/GitHub CLI/gh.exe"` |

## Database Connection

> **중요**: PostgreSQL 및 Neo4j 접속 정보는 항상 `/opt/kms/.env` 파일을 참조하세요.

```bash
# .env 파일에서 DB 접속정보 확인
cat /opt/kms/.env | grep -E "POSTGRES|NEO4J"
```

| Database | 환경변수 |
|----------|----------|
| PostgreSQL | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` |

## Notes for Claude

- Use `Task` tool with `Explore` agent for broad searches
- Read sub-CLAUDE.md files for detailed context on specific areas
- Always run tests after modifications
- Update translations in all 3 locales (en, ko, ja) for UI changes
- Use full path for `gh.exe` on Windows (see Windows Tool Paths above)
- **DB 접속 시 항상 `.env` 파일의 접속정보 사용**

---

## 🚨 CRITICAL: Session Context vs Database Separation

> **이 원칙은 KMS 시스템의 핵심 아키텍처입니다. 반드시 준수하세요!**

### 두 가지 컨텍스트 소스

| 구분 | Admin Database | User Session Context |
|------|----------------|----------------------|
| **소스** | Admin이 정식 업로드한 문서 | 사용자가 채팅에서 첨부한 파일/URL |
| **저장소** | Neo4j Vector Index, PostgreSQL | 메모리 (세션 한정) |
| **수명** | 영구 저장 | 해당 세션에서만 유효 |
| **검색** | vector_search, graph_query 도구 | file_context 직접 참조 |
| **공유** | 모든 사용자 접근 가능 | 해당 사용자만 접근 |

### 처리 우선순위

```
사용자 질문: "첨부파일 요약해줘"

1. file_context (첨부 파일) 있는지 확인
   └─ 있음 → file_context에서 직접 답변 (도구 사용 X)
   └─ 없음 → vector_search 등 DB 도구 사용

2. "문서에서 찾아줘" 같은 일반 질문
   └─ file_context 있으면 → 먼저 file_context 검색
   └─ file_context 없거나 정보 부족 → DB 도구 사용
```

### 구현 위치

| 파일 | 역할 |
|------|------|
| `app/api/agents/executor.py:396-446` | file_context/url_context를 프롬프트에 삽입 |
| `app/api/agents/adapters/deep_agent_adapter.py` | Deep Agent에서 file_context 처리 |
| `app/api/agents/prompts/rag_agent.txt` | 컨텍스트 우선순위 지시 |
| `kms-portal-ui/.../useFileAttachment.ts` | 프론트엔드 파일 첨부 처리 |
| `kms-portal-ui/.../useStreamingChat.ts:306-322` | file_context API 전송 |

### 절대 금지 사항

```python
# ❌ NEVER: 사용자 첨부 파일을 DB에 저장
await vector_store.add_document(user_attached_file)

# ❌ NEVER: file_context를 무시하고 바로 DB 검색
if user_query.contains("첨부"):
    return await vector_search(query)  # Wrong!

# ✅ CORRECT: file_context 우선 확인
if context.file_context:
    # 첨부 파일에서 직접 답변
    return answer_from_file_context(context.file_context, query)
else:
    # DB 검색으로 폴백
    return await vector_search(query)
```

### 코드 수정 시 체크리스트

- [ ] 사용자 첨부 파일이 DB에 저장되지 않는지 확인
- [ ] file_context가 있을 때 우선 처리되는지 확인
- [ ] 세션 종료 시 첨부 컨텍스트가 정리되는지 확인
- [ ] Deep Agent에서도 file_context를 올바르게 처리하는지 확인

---

# Code Review Rules for FastAPI

## 🔄 자동 리뷰 트리거

> **중요**: 기능 구현 또는 수정 완료 후 반드시 아래 4가지 품질 기준으로 자동 리뷰를 수행하세요.

### 트리거 조건
- [ ] 새로운 엔드포인트 추가
- [ ] 기존 API 수정
- [ ] Service/Repository 클래스 변경
- [ ] Pydantic 모델 추가/수정
- [ ] 새로운 의존성 주입 추가

---

## 📊 4대 품질 기준 리뷰

### 1. 유지보수성 (Maintainability)

**체크리스트:**
- [ ] Pydantic Settings로 설정 분리 (`app/api/core/config.py`)
- [ ] 하드코딩된 값(URL, 타임아웃, 매직넘버) 없음
- [ ] 의존성 주입(`Depends`) 활용
- [ ] 에러 핸들링 일관성 (커스텀 예외 클래스 사용)
- [ ] 단일 책임 원칙: 함수당 하나의 역할

**금지 패턴:**
```python
# ❌ Bad: 하드코딩
DATABASE_URL = "postgresql://localhost/mydb"
TIMEOUT = 30

# ✅ Good: Settings 사용
from app.api.core.config import settings
settings.database_url
settings.request_timeout
```

**변경 영향 분석:**
- DB 변경 시 수정 파일 3개 이하인가?
- 새 인증 방식 추가 시 기존 코드 수정 없이 가능한가?

---

### 2. 가독성 (Readability)

**체크리스트:**
- [ ] 모든 함수에 타입 힌트 적용
- [ ] Pydantic 모델에 `Field(description=, example=)` 포함
- [ ] 엔드포인트에 `summary`, `description`, `response_model` 지정
- [ ] 복잡한 로직에 한글 주석 허용 (비즈니스 로직)
- [ ] 함수명: 동사+명사 (`get_user_by_id`, `create_document`)

**필수 패턴:**
```python
# ❌ Bad: 타입 힌트 없음, 설명 없음
class UserCreate(BaseModel):
    name: str
    email: str

# ✅ Good: 완전한 문서화
class UserCreate(BaseModel):
    """사용자 생성 요청 스키마"""
    name: str = Field(..., min_length=2, max_length=50, 
                      description="사용자 이름", example="홍길동")
    email: EmailStr = Field(..., description="이메일 주소",
                           example="user@example.com")
```

**복잡도 기준:**
- 함수 길이: 30줄 이하
- 중첩 깊이: 3단계 이하
- 매개변수: 5개 이하 (초과 시 DTO 사용)

---

### 3. 확장가능성 (Extensibility)

**체크리스트:**
- [ ] Router → Service → Repository 레이어 분리
- [ ] 인터페이스/추상 클래스로 추상화
- [ ] 새 기능 추가 시 기존 코드 수정 없이 확장 가능
- [ ] 플러그인/어댑터 패턴 적용 (agents 참고)

**레이어 분리 패턴:**
```python
# ❌ Bad: 라우터에서 직접 DB 접근
@router.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    return user

# ✅ Good: Service 레이어 분리
@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
) -> UserResponse:
    return await user_service.get_by_id(user_id)
```

**확장 시나리오 테스트:**
- 새 LLM 모델 추가 → adapters/ 폴더에 파일 추가만으로 가능한가?
- 새 DB 지원 추가 → Repository 인터페이스 구현만으로 가능한가?

---

### 4. 구조화 (Structure)

**체크리스트:**
- [ ] 도메인별 라우터 분리 (`app/api/routers/`)
- [ ] schemas/models/services 레이어 명확
- [ ] 순환 import 없음
- [ ] 테스트 구조가 소스 구조와 일치

**프로젝트 구조 준수:**
```
app/api/
├── routers/          # 엔드포인트 (얇은 레이어)
├── services/         # 비즈니스 로직
├── repositories/     # DB 접근
├── schemas/          # Pydantic 모델
├── models/           # ORM 모델
├── core/             # 설정, 보안, 공통
└── agents/           # Agent 시스템
```

**의존성 흐름 검증:**
```
[Router] → [Service] → [Repository] → [DB]
    ↓           ↓
[Schemas]   [Models]

❌ 역방향 금지: Service → Router, Repository → Service
```

---

## 🚫 금지 패턴 (Hard Rules)

| 패턴 | 이유 | 대안 |
|------|------|------|
| `from sqlalchemy import create_engine` | sync 엔진 사용 금지 | `create_async_engine` |
| `os.getenv()` 직접 호출 | 설정 분산 | `from app.api.core.config import settings` |
| `except Exception:` | 모든 예외 캐치 | 구체적 예외 (`ValueError`, `HTTPException`) |
| 라우터에서 직접 DB 쿼리 | 레이어 위반 | Service 레이어 사용 |
| `time.sleep()` | 블로킹 호출 | `await asyncio.sleep()` |
| 전역 변수로 상태 관리 | 테스트 불가 | Depends 또는 Zustand(프론트) |

---

## ✅ 필수 패턴 (Must Have)

| 패턴 | 예시 |
|------|------|
| async/await 일관성 | `async def` + `await` 쌍 |
| 의존성 주입 | `Depends(get_db)`, `Depends(get_current_user)` |
| HTTP 상태 코드 | `HTTPException(status_code=404, detail="Not found")` |
| 응답 모델 지정 | `@router.get(..., response_model=UserResponse)` |
| 트랜잭션 관리 | `async with session.begin():` |

---

## 📋 리뷰 출력 형식

기능 구현 완료 후 아래 형식으로 자체 리뷰 결과를 출력:

```markdown
## 코드 리뷰 결과

| 기준 | 점수 | 주요 이슈 | 개선 필요 |
|------|------|----------|----------|
| 유지보수성 | ?/10 | | ✅/❌ |
| 가독성 | ?/10 | | ✅/❌ |
| 확장가능성 | ?/10 | | ✅/❌ |
| 구조화 | ?/10 | | ✅/❌ |

### 발견된 안티패턴
- [ ] 위치: `파일:라인` - 설명

### 개선 코드 (필요시)
\```python
# Before
...
# After
...
\```

### 체크리스트 완료
- [x] 타입 힌트 완료
- [x] Pydantic Field 설명 추가
- [ ] 테스트 코드 작성 필요
```

---

## 🔧 리뷰 후 액션

1. **점수 7점 미만** → 즉시 리팩토링
2. **안티패턴 발견** → 해당 라인 수정 후 재리뷰
3. **모든 항목 8점 이상** → PR/커밋 진행
4. **테스트 미작성** → `tests/` 폴더에 테스트 추가

---

## 💡 리뷰 트리거 명령어

```bash
# Claude Code에서 사용
"방금 구현한 코드를 4대 품질 기준으로 리뷰해줘"
"이 파일의 유지보수성과 확장가능성을 점검해줘"
"안티패턴을 찾고 개선 코드를 제시해줘"
```

