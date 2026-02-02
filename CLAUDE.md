# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Quick Reference

> **Code Style**: Python (Black, type hints), TypeScript (ESLint, strict types), Korean comments OK for business logic.

> **Before Editing**: Always read the file first. Prefer editing existing files over creating new ones.

> **Context Management**: 50+ tool calls → new session, 60% context → `/compact`

---

## 🔑 API Login & Testing (IMPORTANT - READ FIRST)

> **Claude Code가 API 테스트 시 반드시 참조할 것!**

### 로그인 정보
| 항목 | 값 |
|------|-----|
| API URL | `http://localhost:9000` |
| 인증 파일 | `scripts/login.json` |
| Admin 계정 | `admin` / `SecureAdm1nP@ss2024!` |

### API 테스트 명령어
```bash
# 1. 로그인 토큰 획득
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @scripts/login.json | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# 2. RAG 쿼리 테스트
curl -s -X POST http://localhost:9000/api/v1/agents/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"task": "쿼리 내용", "agent_type": "rag"}'

# 또는 스크립트 사용
./scripts/api_test.sh "tjesmgr 기능"
./scripts/api_test.sh "에러코드 -5212" rag
```

### Docker 컨테이너 관리
```bash
docker ps | grep kms                    # 상태 확인
docker restart kms-backend-local        # 백엔드 재시작
docker logs kms-backend-local --tail 50 # 로그 확인
```

### Windows 직접 실행 (Docker 없이)

> **PowerShell 스크립트로 Backend/Frontend 직접 실행**

```powershell
# 서버 관리 스크립트
.\scripts\server.ps1 all start       # 전체 시작
.\scripts\server.ps1 all stop        # 전체 중지
.\scripts\server.ps1 all restart     # 전체 재시작
.\scripts\server.ps1 status          # 상태 확인

# 개별 서비스
.\scripts\server.ps1 backend start   # 백엔드만 시작
.\scripts\server.ps1 frontend start  # 프론트엔드만 시작
.\scripts\server.ps1 backend logs 100  # 백엔드 로그 (최근 100줄)
```

### 환경 파일 구성

| 파일 | 용도 | 사용 시점 |
|------|------|----------|
| `.env` | 현재 활성 설정 | 항상 참조됨 |
| `.env.local` | Windows 직접 실행용 (원격 서버 192.168.8.11) | `copy .env.local .env` |
| `.env.docker` | Docker 컨테이너용 (컨테이너명 사용) | `copy .env.docker .env` |

```powershell
# Windows 직접 실행으로 전환
copy .env.local .env
.\scripts\server.ps1 all start

# Docker 실행으로 전환
copy .env.docker .env
docker-compose -f docker-compose-local.yml --profile cpu up -d
```

---

## Project Overview

**HybridRAG KMS** - A multilingual GPU-based Hybrid RAG (Retrieval-Augmented Generation) Knowledge Management System combining graph-based and vector-based retrieval with NVIDIA NIM containers.

### Tech Stack
| Layer | Technology |
|-------|------------|
| Backend | FastAPI (Python 3.10+) |
| Frontend | React 18 + TypeScript + Vite |
| Database | Neo4j (Graph + Vector Index) |
| **Vision LLM** | **MiniCPM-V 2.6 (port 12803)** ← 현재 활성 |
| Code LLM | Mistral NeMo 12B (port 12802) |
| Embeddings | NV-EmbedQA-Mistral 7B v2 (port 12801) |
| GPU | NVIDIA A100-SXM4-40GB x 8 |

### 🔄 GPU Configuration (Current - MiniCPM-V)

> **현재 활성 설정**: Vision-Language 모델로 PDF 이미지/차트/표 직접 분석 가능

| 항목 | 값 |
|------|-----|
| Container | `minicpm-vision-graphrag` |
| Model | `openbmb/MiniCPM-V-2_6` |
| GPU | Device 5, 6 (Tensor Parallel) |
| Port | 12803 |
| Max Context | 4096 tokens |
| API | OpenAI-compatible (vLLM) |

```bash
# 상태 확인
docker ps | grep minicpm-vision-graphrag

# 로그 확인
docker logs minicpm-vision-graphrag --tail 50

# API 테스트
curl http://localhost:12803/v1/models
```

### 🔙 GPU Configuration (Backup - Nemotron)

> **롤백용 설정**: 기존 텍스트 기반 RAG LLM (필요시 복원)

| 항목 | 값 |
|------|-----|
| Container | `nemotron-nano` |
| Model | Nemotron Nano 9B |
| GPU | Device 4, 5 |
| Port | 12800 |
| API | OpenAI-compatible |

```bash
# 롤백 방법
# 1. MiniCPM-V 중지
docker stop minicpm-vision-graphrag

# 2. Nemotron 시작 (docker-compose-local.yml 수정 후)
# GPU device: 4,5로 변경, port: 12800
docker-compose -f docker-compose-local.yml up -d nemotron-nano

# 3. .env에서 LLM 설정 변경
# LLM_BASE_URL=http://localhost:12800/v1
```

## Project Structure

```
gpubase-raphrag/
├── app/api/                  # FastAPI backend (325 files) → see app/api/CLAUDE.md
├── kms-portal-ui/            # React frontend (132 files) → see kms-portal-ui/CLAUDE.md
├── e2e/                      # E2E tests (Playwright) → see E2E Testing section
├── tests/                    # Unit/Integration tests (pytest)
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
python -m pytest tests/api/test_auth_endpoints.py -v   # Backend unit tests
cd kms-portal-ui && npm run test:run                   # Frontend unit tests
cd e2e && node e2e_sentence_test.js                    # E2E Hallucination test
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

## 📚 Manual Summary System (Two-Stage Retrieval)

> **목적**: 사용자가 "TJES가 뭐야?", "-5212 에러 알려줘" 같은 비구조화 질문을 할 때, 요약본에서 먼저 컨텍스트를 추출하여 RAG 검색을 보강합니다.

### Architecture

```
사용자 질문: "-5212 에러 원인이 뭐야?"
    ↓
SummarySearchService.enrich_query()
    ↓
요약본 검색 (파일 시스템 기반, <10ms)
    ├─ error-codes/BASE-5000.md → 에러 정보 추출
    └─ glossary/T.md → 용어 정보 추출
    ↓
보강된 쿼리: "질문 + [에러 -5212: BASE/DSALC_ERR_DATASET_NOT_FOUND]"
    ↓
Vector/Graph DB 검색 (정확도 향상)
```

### Directory Structure

```
uploads/summaries/
├── index.md                 # 마스터 인덱스
├── index.json               # JSON 인덱스 (프로그래밍용)
├── error-codes/             # 에러 코드 사전 (46개 파일, ~1,200개 에러)
│   ├── BASE-5000.md         # 5000번대 에러
│   ├── AIM-21000.md         # AIM 모듈 에러
│   └── ...
├── glossary/                # 용어 사전 (26개 파일, A-Z)
│   ├── T.md                 # TJES, TACF, TSO 등
│   └── ...
├── commands/                # 📌 OpenFrame 명령어 사전
│   ├── OpenFrame_TJES_MVS.md    # tjesmgr, tjesmgr BOOT 등
│   ├── OpenFrame_HIDB.md        # hidbmgr 명령어
│   └── ...
├── configs/                 # 설정 파라미터 사전
│   └── OpenFrame_*.md
├── apis/                    # API 함수 사전
│   └── OpenFrame_*.md
└── terms/                   # 기술 용어 정의
    └── OpenFrame_*.md
```

### Summaries Content Types

| 폴더 | 내용 | 예시 |
|------|------|------|
| error-codes/ | 에러 코드, 원인, 해결방법 | `-5212: DATASET_NOT_FOUND` |
| glossary/ | 약어, 전문용어 정의 | `TJES: Tmax Job Entry Subsystem` |
| **commands/** | **OpenFrame 관리 명령어** | `tjesmgr BOOT`, `hidbmgr START` |
| configs/ | 설정 파라미터 상세 | `oframe.conf 옵션` |
| apis/ | 프로그래밍 API 함수 | `DSALC_*` 함수 목록 |
| terms/ | 도메인 전문 용어 | `Batch Processing`, `JCL` |

### Key Files

| 파일 | 역할 |
|------|------|
| `scripts/manual_processor/` | PDF 분석 및 요약본 생성 스크립트 |
| `scripts/manual_processor/main.py` | CLI: `process-all`, `extract-errors`, `rebuild-index` |
| `app/api/services/summary_search_service.py` | RAG Agent용 요약본 검색 서비스 |
| `uploads/summaries/` | 생성된 요약본 저장소 |

### Service API

```python
from app.api.services.summary_search_service import get_summary_search_service

service = get_summary_search_service()

# 에러 코드 검색
error = await service.search_error_code("-5212")
# → {"code": "-5212", "name": "DSALC_ERR_DATASET_NOT_FOUND", "module": "BASE", ...}

# 용어 검색
term = await service.search_glossary("TJES")
# → {"term": "TJES", "full_name": "Tmax Job Entry Subsystem", ...}

# 쿼리 보강 (RAG Agent 연동)
enriched = await service.enrich_query("-5212 에러 원인")
# → "-5212 에러 원인\n\n컨텍스트: [에러 -5212: BASE - DSALC_ERR_DATASET_NOT_FOUND]"
```

### Commands

```bash
# 요약본 전체 생성 (Error Codes + Glossary)
python -m scripts.manual_processor.main process-all

# 에러 코드만 추출
python -m scripts.manual_processor.main extract-errors

# 📌 포괄적 정보 추출 (Commands, Configs, APIs, Terms)
python -m scripts.manual_processor.main extract-comprehensive

# 인덱스 재생성
python -m scripts.manual_processor.main rebuild-index
```

### OpenFrame 명령어 요약본 예시 (commands/OpenFrame_TJES_MVS.md)

```markdown
## tjesmgr 명령어

### BOOT
- **구문**: `tjesmgr BOOT [node_name]`
- **설명**: TJES 노드를 초기화합니다
- **출처**: OpenFrame_TJES_MVS.pdf, p.45

### CANCEL
- **구문**: `tjesmgr CANCEL jobname`
- **설명**: 실행 중인 Job을 취소합니다
```

> **중요**: 이 요약본들은 Graph DB Entity 추출의 소스로도 활용됩니다.

### Graph DB Entity 연동 (Summary → Entity)

요약본의 명령어/용어를 Graph DB Entity로 변환하여 검색 정확도를 향상시킵니다.

```
uploads/summaries/commands/OpenFrame_TJES_MVS.md
    ↓ (parse & extract)
Entity 노드 생성: tjesmgr, BOOT, CANCEL, CHANGE...
    ↓
Chunk 노드와 MENTIONS 관계 연결
    ↓
Graph 검색에서 "tjesmgr 에러" → 관련 Chunk 탐색 가능
```

**관련 파일:**
| 파일 | 역할 |
|------|------|
| `app/api/services/knowledge_graph_service.py` | ENTITY_PATTERNS 정의, Entity 추출 |
| `scripts/manual_processor/extractors/` | 요약본 생성 |
| `scripts/populate_entities_from_summaries.py` | 요약본 → Entity 변환 스크립트 |

### RAG Agent Integration

RAG Agent는 검색 전에 `SummarySearchService`를 호출하여 쿼리를 보강합니다:
1. 에러 코드 패턴 감지 (`-\d{4,5}`) → 에러 정보 추가
2. 기술 용어 감지 (`[A-Z]{2,}`) → 용어 정보 추가
3. 보강된 컨텍스트와 함께 vector_search 수행

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

## 🧪 E2E Testing (Playwright)

> **목적**: RAG 검색 품질 검증 및 Hallucination(환각) 감지를 위한 브라우저 자동화 테스트

### Framework & Setup

| 항목 | 값 |
|------|-----|
| Framework | Playwright (Chromium) |
| Language | JavaScript (Node.js) |
| Location | `e2e/` |
| Prerequisites | `npm install playwright` |

### Test Files

| 파일 | 용도 |
|------|------|
| `e2e_sentence_test.js` | **메인 테스트** - 45개 문장 기반 Hallucination 감지 |
| `e2e_keyword_test.js` | 키워드 기반 RAG 검색 테스트 |
| `e2e_tjesmgr.js` | tjesmgr 명령어 전용 테스트 |
| `e2e_tacfmgr.js` | tacfmgr 명령어 전용 테스트 |
| `e2e_hidbmgr.js` | hidbmgr 명령어 전용 테스트 |
| `e2e_close_modal.js` | UI 모달 상호작용 테스트 |
| `debug_nav.js` | 네비게이션 디버깅 헬퍼 |
| `extract_keywords.py` | 테스트용 키워드 추출 스크립트 |

### Running E2E Tests

```bash
cd e2e

# 메인 Hallucination 테스트 (45개 케이스)
node e2e_sentence_test.js

# 키워드 검색 테스트
node e2e_keyword_test.js

# 개별 명령어 테스트
node e2e_tjesmgr.js
node e2e_tacfmgr.js
node e2e_hidbmgr.js
```

### Test Coverage

테스트 대상 OpenFrame 컴포넌트:

| 카테고리 | 테스트 항목 |
|----------|------------|
| Manager 명령어 | `tjesmgr`, `tacfmgr`, `hidbmgr`, `ndbmgr`, `oscmgr`, `osimgr`, `volmgr`, `catmgr` |
| Utilities | `idcams`, `iebgener`, `iebcopy`, `dfsort`, `dsmigin`, `dsmigout` |
| JCL | `JOB`, `EXEC`, `DD` statements |
| Config 파일 | `tjes.conf`, `osc.conf`, `tacf.conf`, `ds.conf` |
| Error Codes | `ABEND S0C7`, `S0C4`, `S806` |
| VSAM Types | `KSDS`, `ESDS`, `GDG`, `PDS` |
| System 명령어 | `tmboot`, `tmdown`, `ofboot`, `ofdown`, `jesinit`, `jesdown` |

### Hallucination Detection

테스트는 다음 패턴으로 Hallucination을 감지합니다:

```javascript
// 예: "tjesmgr"를 질문했는데 "oscmgr"가 응답에 포함되면 Hallucination
{
  keyword: 'tjesmgr',
  query: 'tjesmgrについて説明してください。',
  expected: ['tjesmgr', 'TJES'],      // 기대 키워드
  notExpected: ['oscmgr', 'osimgr']   // 있으면 안되는 키워드 (Hallucination)
}
```

### Test Results

결과 파일:
- `sentence_test_results.json` - 문장 테스트 결과
- `test_results.json` - 키워드 테스트 결과
- `keywords.json` - 추출된 키워드 목록 (300개)
- `hallucination_*.png` - Hallucination 발생 시 스크린샷

결과 형식:
```json
{
  "total": 45,
  "passed": 24,
  "failed": 21,
  "hallucinations": [...],
  "noResults": [...],
  "errors": []
}
```

### Test Improvement Workflow

1. E2E 테스트 실행 → Hallucination 케이스 확인
2. `hallucination_*.png` 스크린샷 분석
3. RAG 검색 로직 또는 Summary 데이터 개선
4. 재테스트로 검증

### Key Files

| 파일 | 역할 |
|------|------|
| `e2e/e2e_sentence_test.js` | 메인 테스트 로직 |
| `e2e/keywords.json` | 테스트 키워드 목록 |
| `e2e/sentence_test_results.json` | 최신 테스트 결과 |

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

