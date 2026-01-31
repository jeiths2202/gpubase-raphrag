# System Prompting Feature - PDCA Plan

## Feature Overview

**Feature Name**: System Prompting Admin UI
**Created**: 2026-01-31
**Status**: Planning
**Priority**: High

### Goal
Admin 페이지에 "System Prompting" 탭을 추가하여 하드코딩된 프롬프트를 UI에서 관리할 수 있도록 합니다.

---

## 1. Current State Analysis (현황 분석)

### 1.1 Prompt Storage Summary

| Storage Type | Count | Location | Maintainability |
|--------------|-------|----------|-----------------|
| **Text Files** | 13 | `app/api/agents/prompts/` | ✅ Good |
| **Middleware Files** | 3 | `app/api/agents/prompts/middleware/` | ✅ Good |
| **Python Classes** | 20+ | `app/api/prompts/` | ⚠️ Requires deploy |
| **Hardcoded in Services** | 3 | Various services | ❌ Poor |
| **Master Constraint** | 1 | `master_system_constraint.py` | 🔒 Critical |

### 1.2 Agent Prompt Files (10 files)

| File | Agent | Size | Multi-lang |
|------|-------|------|------------|
| `rag_agent.txt` | RAG Agent | 2.1 KB | KO, EN, JA |
| `code_agent.txt` | Code Agent | 600 B | EN only |
| `vision_agent.txt` | Vision Agent | 650 B | EN only |
| `ims_agent.txt` | IMS Agent | 1.2 KB | KO, EN, JA |
| `opencode_agent.txt` | OpenCode Agent | 2.5 KB | KO, EN, JA |
| `planner_agent.txt` | Planner Agent | 800 B | EN only |
| `enhancement_analyst_agent.txt` | Enhancement Analyst | 1.5 KB | EN only |
| `enhancement_architect_agent.txt` | Enhancement Architect | 1.5 KB | EN only |
| `enhancement_coder_agent.txt` | Enhancement Coder | 1.2 KB | EN only |
| `enhancement_qa_agent.txt` | Enhancement QA | 700 B | EN only |

### 1.3 Middleware Prompt Files (3 files)

| File | Purpose | Size |
|------|---------|------|
| `middleware/rag_system.txt` | RAG tool guidelines | 400 B |
| `middleware/code_system.txt` | Code tool guidelines | 900 B |
| `middleware/ims_system.txt` | IMS tool guidelines | 400 B |

### 1.4 Hardcoded Prompts in Python Services

| File | Location | Description | Priority |
|------|----------|-------------|----------|
| `agents/agents/rag_agent.py` | Lines 45-88 | Default RAG prompt | Medium |
| `services/keyword_extraction_service.py` | Line 50+ | Keyword extraction prompt | Medium |
| `services/llm_query_expansion_service.py` | Lines 213, 230 | Translation prompts (KO→JA, EN→JA) | Low |

### 1.5 Python Prompt Classes (`app/api/prompts/`)

| File | Classes | Languages |
|------|---------|-----------|
| `base.py` | PromptTemplate, MultiLanguagePromptTemplate, PromptRegistry | - |
| `system_prompts.py` | 5 personas + 4 domain prompts | KO, EN |
| `rag_prompts.py` | 6 prompt classes | KO, EN, JA |
| `mindmap_prompts.py` | ConceptExtractionPrompt | KO, EN, JA |

---

## 2. Requirements (요구사항)

### 2.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Admin UI에서 모든 프롬프트 조회 | Must |
| FR-02 | 프롬프트 내용 편집 및 저장 | Must |
| FR-03 | 프롬프트 버전 히스토리 관리 | Should |
| FR-04 | 프롬프트 롤백 기능 | Should |
| FR-05 | 프롬프트 변경 사항 실시간 적용 | Must |
| FR-06 | 다국어 프롬프트 관리 (KO, EN, JA) | Should |
| FR-07 | 프롬프트 검증/테스트 | Could |
| FR-08 | 프롬프트 변경 감사 로그 | Should |

### 2.2 Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | Admin 권한만 접근 가능 | Must |
| NFR-02 | 프롬프트 로딩 < 100ms | Should |
| NFR-03 | 변경 시 재시작 없이 적용 | Must |
| NFR-04 | 프롬프트 크기 제한 (10KB) | Should |
| NFR-05 | Master Constraint 수정 불가 (읽기 전용) | Must |

---

## 3. Architecture Design (아키텍처 설계)

### 3.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Admin Dashboard                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────────┐ │
│  │   Users  │ │ Scoring  │ │   Prompts    │ │   Enhancement   │ │
│  │   Tab    │ │   Tab    │ │     Tab      │ │      Tab        │ │
│  └──────────┘ └──────────┘ └──────────────┘ └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Backend API Layer                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              /api/v1/admin/prompts                          │ │
│  │  GET    /                    - List all prompts             │ │
│  │  GET    /{prompt_id}         - Get prompt detail            │ │
│  │  PUT    /{prompt_id}         - Update prompt                │ │
│  │  GET    /{prompt_id}/history - Get version history          │ │
│  │  POST   /{prompt_id}/rollback/{version_id} - Rollback       │ │
│  │  POST   /{prompt_id}/test    - Test prompt                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Service Layer                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              PromptConfigService                            │ │
│  │  - get_all_prompts()                                        │ │
│  │  - get_prompt(prompt_id)                                    │ │
│  │  - update_prompt(prompt_id, content)                        │ │
│  │  - get_prompt_history(prompt_id)                            │ │
│  │  - rollback_prompt(prompt_id, version_id)                   │ │
│  │  - validate_prompt(prompt_id, content)                      │ │
│  │  - reload_runtime_prompts()                                 │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Storage Layer                                  │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │   File System       │  │      PostgreSQL                  │  │
│  │   (Primary Source)  │  │      (History + Runtime Cache)   │  │
│  │   prompts/*.txt     │  │   prompt_configs table           │  │
│  │                     │  │   prompt_history table           │  │
│  └─────────────────────┘  └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Model

```sql
-- prompt_configs: 현재 활성 프롬프트 설정
CREATE TABLE prompt_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id VARCHAR(100) UNIQUE NOT NULL,    -- e.g., 'rag_agent', 'code_agent'
    category VARCHAR(50) NOT NULL,              -- 'agent', 'middleware', 'system', 'domain'
    name VARCHAR(200) NOT NULL,                 -- Human-readable name
    description TEXT,
    content TEXT NOT NULL,                      -- Prompt content
    language VARCHAR(10) DEFAULT 'en',          -- 'en', 'ko', 'ja'
    is_readonly BOOLEAN DEFAULT FALSE,          -- Master constraint = readonly
    source_file VARCHAR(255),                   -- Original file path (for sync)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by UUID REFERENCES users(id)
);

-- prompt_history: 변경 히스토리
CREATE TABLE prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_id VARCHAR(100) NOT NULL,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by UUID REFERENCES users(id),
    UNIQUE(prompt_id, version_number)
);

-- Indexes
CREATE INDEX idx_prompt_configs_category ON prompt_configs(category);
CREATE INDEX idx_prompt_history_prompt_id ON prompt_history(prompt_id);
CREATE INDEX idx_prompt_history_changed_at ON prompt_history(changed_at DESC);
```

### 3.3 Prompt Categories

| Category | Prompts | Editable | Notes |
|----------|---------|----------|-------|
| `agent` | RAG, Code, Vision, IMS, OpenCode, Planner, Enhancement* | ✅ Yes | Agent system prompts |
| `middleware` | RAG System, Code System, IMS System | ✅ Yes | Tool usage guidelines |
| `system` | Master Constraint | ❌ Read-only | Critical security constraint |
| `persona` | Assistant, Code Assistant, Analyst, etc. | ✅ Yes | Python-based personas |
| `domain` | Entity Extraction, Summarization, Translation, Keyword | ✅ Yes | Domain-specific prompts |

---

## 4. Implementation Plan (구현 계획)

### 4.1 Phase 1: Backend API (Priority: Must)

#### 4.1.1 Files to Create

| File | Purpose |
|------|---------|
| `app/api/routers/admin_prompts.py` | API endpoints |
| `app/api/services/prompt_config_service.py` | Business logic |
| `app/api/infrastructure/postgres/prompt_config_repository.py` | Data access |
| `app/api/models/prompt_config.py` | Pydantic models |

#### 4.1.2 API Endpoints

```python
# app/api/routers/admin_prompts.py

@router.get("/prompts")
async def list_prompts() -> List[PromptSummary]:
    """모든 프롬프트 목록 조회"""

@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: str) -> PromptDetail:
    """프롬프트 상세 조회"""

@router.put("/prompts/{prompt_id}")
async def update_prompt(prompt_id: str, request: PromptUpdateRequest) -> PromptDetail:
    """프롬프트 수정"""

@router.get("/prompts/{prompt_id}/history")
async def get_prompt_history(prompt_id: str) -> List[PromptHistory]:
    """버전 히스토리 조회"""

@router.post("/prompts/{prompt_id}/rollback/{version_id}")
async def rollback_prompt(prompt_id: str, version_id: UUID) -> PromptDetail:
    """특정 버전으로 롤백"""

@router.post("/prompts/{prompt_id}/test")
async def test_prompt(prompt_id: str, request: PromptTestRequest) -> PromptTestResult:
    """프롬프트 테스트 실행"""

@router.post("/prompts/sync")
async def sync_prompts_from_files() -> SyncResult:
    """파일시스템에서 DB로 동기화"""
```

### 4.2 Phase 2: Frontend UI (Priority: Must)

#### 4.2.1 Files to Create

| File | Purpose |
|------|---------|
| `kms-portal-ui/src/components/admin/prompts/index.tsx` | PromptTab main component |
| `kms-portal-ui/src/components/admin/prompts/PromptList.tsx` | Prompt list sidebar |
| `kms-portal-ui/src/components/admin/prompts/PromptEditor.tsx` | Monaco editor component |
| `kms-portal-ui/src/components/admin/prompts/PromptHistory.tsx` | Version history panel |
| `kms-portal-ui/src/components/admin/prompts/PromptTest.tsx` | Test panel |
| `kms-portal-ui/src/api/prompts.api.ts` | API client |

#### 4.2.2 UI Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  Admin Dashboard > System Prompting                                 │
├────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐ ┌────────────────────────────────────────────┐ │
│ │ Prompt List     │ │  Prompt Editor                             │ │
│ │                 │ │  ┌────────────────────────────────────────┐│ │
│ │ [Agent]         │ │  │ Name: RAG Agent System Prompt          ││ │
│ │  ├ RAG Agent    │ │  │ Category: agent                        ││ │
│ │  ├ Code Agent   │ │  │ Language: en                           ││ │
│ │  ├ Vision Agent │ │  └────────────────────────────────────────┘│ │
│ │  ├ IMS Agent    │ │  ┌────────────────────────────────────────┐│ │
│ │  └ OpenCode     │ │  │                                        ││ │
│ │                 │ │  │  (Monaco Editor)                       ││ │
│ │ [Middleware]    │ │  │                                        ││ │
│ │  ├ RAG System   │ │  │  You are a RAG agent...                ││ │
│ │  ├ Code System  │ │  │                                        ││ │
│ │  └ IMS System   │ │  │                                        ││ │
│ │                 │ │  │                                        ││ │
│ │ [System] 🔒     │ │  └────────────────────────────────────────┘│ │
│ │  └ Master       │ │  [Save] [Reset] [Test]                     │ │
│ │                 │ │                                            │ │
│ │ [Persona]       │ ├────────────────────────────────────────────┤ │
│ │  ├ Assistant    │ │  Version History                          │ │
│ │  ├ Code Assist  │ │  ┌────────────────────────────────────────┐│ │
│ │  └ Analyst      │ │  │ v3 - 2026-01-31 - Added context rules  ││ │
│ │                 │ │  │ v2 - 2026-01-30 - Updated format       ││ │
│ └─────────────────┘ │  │ v1 - 2026-01-29 - Initial              ││ │
│                     │  └────────────────────────────────────────┘│ │
│                     └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### 4.3 Phase 3: Runtime Integration (Priority: Must)

#### 4.3.1 Prompt Loading Strategy

```python
# 1. 시작 시 초기화
async def init_prompts():
    """서버 시작 시 프롬프트 초기화"""
    # 파일시스템에서 프롬프트 로드
    file_prompts = load_prompts_from_files()

    # DB에서 override 설정 로드
    db_overrides = await load_prompts_from_db()

    # 병합 (DB가 우선)
    merged = merge_prompts(file_prompts, db_overrides)

    # 런타임 캐시에 저장
    PromptCache.set_all(merged)

# 2. 프롬프트 업데이트 시
async def update_prompt(prompt_id: str, content: str):
    """프롬프트 업데이트 및 핫 리로드"""
    # DB 저장
    await save_to_db(prompt_id, content)

    # 히스토리 기록
    await save_history(prompt_id, content)

    # 런타임 캐시 갱신 (재시작 없이 즉시 적용)
    PromptCache.update(prompt_id, content)
```

#### 4.3.2 Modified Files

| File | Change |
|------|--------|
| `app/api/agents/adapters/deep_agent_adapter.py` | PromptCache 사용하도록 수정 |
| `app/api/agents/agents/rag_agent.py` | PromptCache 사용하도록 수정 |
| `app/api/prompts/base.py` | PromptCache 통합 |

### 4.4 Phase 4: Translation Support (Priority: Should)

#### 4.4.1 Multi-language Structure

```
prompts/
├── rag_agent.txt           # Default (English)
├── rag_agent.ko.txt        # Korean
├── rag_agent.ja.txt        # Japanese
```

#### 4.4.2 Database Schema Extension

```sql
-- 다국어 지원을 위한 언어별 레코드
-- prompt_id + language = unique
ALTER TABLE prompt_configs
ADD CONSTRAINT unique_prompt_language UNIQUE (prompt_id, language);
```

---

## 5. Task Breakdown (작업 분해)

### Phase 1: Backend (Day 1-2)

| Task ID | Task | Effort | Dependencies |
|---------|------|--------|--------------|
| BE-01 | DB 마이그레이션 스크립트 작성 | 2h | - |
| BE-02 | Pydantic 모델 정의 | 1h | - |
| BE-03 | Repository 클래스 구현 | 3h | BE-01 |
| BE-04 | Service 클래스 구현 | 4h | BE-02, BE-03 |
| BE-05 | Router 엔드포인트 구현 | 3h | BE-04 |
| BE-06 | 파일→DB 동기화 기능 | 2h | BE-04 |
| BE-07 | 단위 테스트 | 2h | BE-05 |

### Phase 2: Frontend (Day 2-3)

| Task ID | Task | Effort | Dependencies |
|---------|------|--------|--------------|
| FE-01 | API 클라이언트 구현 | 1h | BE-05 |
| FE-02 | PromptTab 메인 컴포넌트 | 2h | FE-01 |
| FE-03 | PromptList 컴포넌트 | 2h | FE-02 |
| FE-04 | PromptEditor (Monaco) 컴포넌트 | 4h | FE-02 |
| FE-05 | PromptHistory 컴포넌트 | 2h | FE-02 |
| FE-06 | Admin Dashboard에 탭 추가 | 1h | FE-02 |
| FE-07 | 다국어 번역 추가 (en, ko, ja) | 1h | FE-02 |

### Phase 3: Integration (Day 3-4)

| Task ID | Task | Effort | Dependencies |
|---------|------|--------|--------------|
| INT-01 | PromptCache 클래스 구현 | 2h | BE-04 |
| INT-02 | deep_agent_adapter 수정 | 2h | INT-01 |
| INT-03 | rag_agent 수정 | 1h | INT-01 |
| INT-04 | 핫 리로드 테스트 | 2h | INT-02, INT-03 |
| INT-05 | E2E 테스트 | 2h | FE-07, INT-04 |

### Phase 4: Polish (Day 4-5)

| Task ID | Task | Effort | Dependencies |
|---------|------|--------|--------------|
| POL-01 | 다국어 프롬프트 UI | 3h | FE-04 |
| POL-02 | 프롬프트 테스트 기능 | 4h | BE-05 |
| POL-03 | 문서화 | 2h | All |
| POL-04 | 코드 리뷰 및 정리 | 2h | All |

---

## 6. Risk Analysis (위험 분석)

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Master Constraint 수정으로 보안 취약점 발생 | High | Low | Read-only 플래그로 수정 불가 처리 |
| 프롬프트 변경으로 RAG 품질 저하 | Medium | Medium | 버전 히스토리 + 롤백 기능 |
| 런타임 캐시 동기화 실패 | Medium | Low | 주기적 DB 체크 + 수동 리로드 버튼 |
| 대용량 프롬프트로 성능 저하 | Low | Low | 크기 제한 (10KB) + 페이지네이션 |

---

## 7. Success Criteria (성공 기준)

| Criteria | Measurement |
|----------|-------------|
| Admin UI에서 모든 프롬프트 조회 가능 | 16개 이상 프롬프트 목록 표시 |
| 프롬프트 편집 및 저장 | 저장 후 1초 내 적용 확인 |
| 버전 히스토리 조회 | 최소 5개 버전 기록 유지 |
| 롤백 기능 동작 | 이전 버전 복원 후 정상 동작 |
| Master Constraint 보호 | 수정 시도 시 에러 반환 |

---

## 8. References

### Related Files

- `app/api/agents/prompts/` - 현재 프롬프트 파일들
- `app/api/prompts/` - Python 프롬프트 모듈
- `app/api/agents/master_system_constraint.py` - 마스터 제약
- `app/api/routers/admin_scoring.py` - 유사한 Admin API 패턴 참조
- `kms-portal-ui/src/components/admin/scoring/` - 유사한 Admin UI 패턴 참조

### Dependencies

- Monaco Editor (프론트엔드 코드 에디터)
- PostgreSQL (히스토리 저장)
- Redis (optional, 캐시 레이어)

---

## 9. Approval

| Role | Name | Date | Status |
|------|------|------|--------|
| Feature Owner | - | - | Pending |
| Tech Lead | - | - | Pending |
| QA | - | - | Pending |

---

**Next Step**: `/pdca design system-prompting` 으로 상세 설계 문서 작성
