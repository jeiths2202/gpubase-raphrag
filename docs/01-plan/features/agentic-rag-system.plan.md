# Plan: Agentic RAG System

> **Feature**: Side 메뉴 "Analytics" → "Agentic RAG" 교체 + 제품별 Agent 기반 RAG 시스템 구현
> **Created**: 2026-02-07
> **Status**: Draft
> **Priority**: High

---

## 1. 현재 상태 분석 (As-Is)

### 1.1 기존 OpenFrame RAG 시스템

| 구성요소 | 현재 구현 | 파일 |
|----------|----------|------|
| **Router** | `/api/v1/openframe-rag/*` (8 엔드포인트) | `app/api/routers/openframe_rag.py` |
| **Service** | `OpenFrameRAGService` (1030줄, 모놀리식) | `app/api/services/openframe_rag_service.py` |
| **Models** | `ProductId` enum (8제품+AUTO+OTHER) | `app/api/models/openframe_rag.py` |
| **Product Router** | 키워드+정규식 기반 분류 (결정론적) | `app/api/services/product_router_service.py` |
| **DeepSeek** | 8제품 병렬 검색+합성 | `app/api/services/deep_seek_service.py` |
| **Frontend** | `OpenFrameRAGPage.tsx` (1031줄) | `kms-portal-ui/src/pages/OpenFrameRAGPage.tsx` |
| **LLM Fallback** | TRT-LLM NIM → Learning LLM (QLoRA) → Context-only | `openframe_rag_service.py` |

### 1.2 기존 Agent 시스템

| 구성요소 | 현재 구현 | 파일 |
|----------|----------|------|
| **Orchestrator** | Intent 분류 → Agent 라우팅 | `app/api/agents/orchestrator.py` |
| **RAG Agent** | unified_search, comprehensive_search, graph_query | `app/api/agents/agents/rag_agent.py` |
| **AnswerBuilder** | 규칙 기반 추출 (환각 구조적 차단) | `app/api/services/answer_builder_service.py` |
| **Deep Agent** | LangGraph 기반, tool calling | `app/api/agents/adapters/deep_agent_adapter.py` |

### 1.3 기존 Sidebar 메뉴 구조

```
Sidebar.tsx NAV_ITEMS:
├── agent        → /agent        (Bot 아이콘)
├── openAgent    → /open-agent   (Sparkles 아이콘)
├── openframeRag → /openframe-rag (Cpu 아이콘)
├── mindmap      → /mindmap      (Brain 아이콘)
├── ims          → /ims          (Database 아이콘)
├── faq          → /faq          (HelpCircle 아이콘)
├── documents    → /documents    (FileText, admin only)
├── analytics    → /analytics    (BarChart3, admin only) ← PlaceholderPage
└── improvements → /improvements (Lightbulb 아이콘)
```

**핵심 발견**: `analytics`는 현재 `PlaceholderPage` (미구현 상태) → 교체에 리스크 없음

### 1.4 현재 시스템의 문제점

1. **모놀리식 서비스**: `OpenFrameRAGService`가 분류/검색/생성을 모두 담당 (1030줄)
2. **LLM 의존적 검색**: 검색 단계에서도 LLM 개입 가능 → 환각 위험
3. **교차 오염**: 제품별 격리 없이 모든 검색이 동일 파이프라인 통과
4. **응답 검증 부재**: LLM 생성 응답의 사후 검증 레이어 없음
5. **제품별 특화 부재**: 모든 제품이 동일한 프롬프트/검색 전략 사용

---

## 2. 목표 상태 (To-Be)

### 2.1 핵심 아키텍처

```
┌─────────────────────────────────────────────────┐
│           사용자 프롬프트 (Agentic RAG Page)       │
└──────────────────┬──────────────────────────────┘
                   ▼
┌──────────────────────────────────┐
│  질문 라우터 (다단계 확인 구조)      │
│  1차: 키워드+BM25 기반 후보 선택    │
│  2차: 점수 차이 < 임계값 → 되묻기   │
│  3차: 최고 점수 Agent로 라우팅      │
└──────────────────┬───────────────┘
                   ▼
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
 [Agent A]      [Agent B]     [Agent C]
 OpenFrame      JEUS/Tmax     Tibero
 (MVS/Base/     (WAS/미들웨어) (DB/SQL)
  ASM/COBOL)
    │              │              │
    ▼              ▼              ▼
 구조화 검색     구조화 검색     구조화 검색    ← LLM 없이 검색
 (커맨드,       (설정,         (SQL,
  파라미터,      에러코드,       파라미터,
  에러코드)      튜닝)          성능)
    │              │              │
    └──────────────┼──────────────┘
                   ▼
┌──────────────────────────────────┐
│  질문 유형 판별                     │
│  ├─ 정형 질문 → 템플릿 기반 응답    │  ← LLM 불필요 (환각 0%)
│  └─ 비정형 질문 → 제한된 LLM 생성   │  ← 인용 강제 + 사후 검증
└──────────────────┬───────────────┘
                   ▼
┌──────────────────────────────────┐
│  사후 검증 레이어                    │
│  - 응답 문장별 소스 유사도 검사      │
│  - 🟢 확인됨 / 🟡 추정됨 / 🔴 미확인 │
│  - 근거 없는 문장 제거              │
└──────────────────────────────────┘
```

### 2.2 설계 원칙

| 원칙 | 설명 |
|------|------|
| **검색=결정론적** | 검색/매칭 단계는 LLM 없이 키워드+구조화 DB로 수행 |
| **LLM=전달 도구** | LLM은 "지식의 원천"이 아닌 "검색 결과 포맷팅 도구"로만 사용 |
| **제품별 격리** | 각 Agent가 독립적 지식 도메인 관리 → 교차 오염 방지 |
| **모르면 물어본다** | 분류 불확실 시 사용자에게 되묻기 (잘못 라우팅보다 낫다) |
| **정형=템플릿** | 커맨드/에러코드/파라미터 질문은 템플릿 기반 (환각 0%) |
| **비정형=검증** | LLM 필요 시 인용 강제 + 사후 검증 레이어 통과 필수 |

---

## 3. 구현 범위

### 3.1 Frontend 변경

| 작업 | 상세 | 영향 파일 |
|------|------|----------|
| **F-1** | Sidebar: `analytics` → `agenticRag` 교체 | `Sidebar.tsx` |
| **F-2** | Route: `/analytics` → `/agentic-rag` 교체 | `App.tsx` |
| **F-3** | `AgenticRAGPage.tsx` 신규 생성 | `pages/AgenticRAGPage.tsx` |
| **F-4** | i18n: 3개 언어 번역 추가 (en, ko, ja) | `locales/*/common.json` |
| **F-5** | 제품 선택 UI (카드형 or 드롭다운) | `AgenticRAGPage.tsx` 내부 |
| **F-6** | 되묻기 UI (분류 불확실 시) | `AgenticRAGPage.tsx` 내부 |
| **F-7** | 신뢰도 배지 표시 (🟢🟡🔴) | `AgenticRAGPage.tsx` 내부 |
| **F-8** | 소스 인용 패널 (출처 문서 표시) | `AgenticRAGPage.tsx` 내부 |

### 3.2 Backend 변경

| 작업 | 상세 | 영향 파일 |
|------|------|----------|
| **B-1** | `AgenticRAGService` 신규 생성 (오케스트레이터) | `services/agentic_rag_service.py` |
| **B-2** | `ProductAgent` 베이스 클래스 + 제품별 Agent | `agents/agents/product_agents/` |
| **B-3** | `QueryRouter` 개선 (다단계 확인 구조) | `services/query_router_service.py` |
| **B-4** | `TemplateResponseBuilder` 정형 응답 생성기 | `services/template_response_builder.py` |
| **B-5** | `ResponseVerifier` 사후 검증 레이어 | `services/response_verifier_service.py` |
| **B-6** | `StructuredKnowledgeStore` 구조화 DB 인터페이스 | `services/structured_knowledge_store.py` |
| **B-7** | API Router (`/api/v1/agentic-rag/*`) | `routers/agentic_rag.py` |
| **B-8** | Pydantic 모델 정의 | `models/agentic_rag.py` |

### 3.3 기존 코드 재활용

| 기존 컴포넌트 | 재활용 방식 |
|--------------|-----------|
| `ProductRouterService` | `QueryRouter`의 1차 분류기로 래핑하여 사용 |
| `OpenFrameRAGService._vector_search()` | Agent별 검색 메서드로 위임 |
| `OpenFrameRAGService._graph_search()` | Agent별 검색 메서드로 위임 |
| `AnswerBuilderService` | 템플릿 기반 응답의 포맷팅에 활용 |
| `ProductId` enum | 그대로 사용 (모델 공유) |
| `LearningLLMService` | 비정형 질문의 LLM 생성에 사용 |
| `DeepSeekService` | 전 제품 검색 모드에서 재활용 |

---

## 4. 제품별 Agent 설계

### 4.1 Agent 구조

```python
# 베이스 클래스
class ProductAgent(BaseAgent):
    product_id: ProductId
    knowledge_domains: List[str]  # ["commands", "error_codes", "configs"]
    template_patterns: Dict[str, str]  # 정형 응답 템플릿

# 제품별 Agent 구현
class OpenFrameMVSAgent(ProductAgent)   # TJES, JCL, TACF, OSC, MVS 유틸리티
class OpenFrameBaseAgent(ProductAgent)  # VSAM, 카탈로그, 볼륨, 데이터셋
class TiberoAgent(ProductAgent)         # SQL, 파라미터, 성능, 에러코드
class TmaxAgent(ProductAgent)           # TMAX 미들웨어 설정, 튜닝
class OFASMAgent(ProductAgent)          # 어셈블러 명령어, 마이그레이션
class OFCOBOLAgent(ProductAgent)        # COBOL 변환, 런타임
class MSPAgent(ProductAgent)            # MSP/JES2/JES3
class VOS3Agent(ProductAgent)           # VOS3/ACOS
class XSPAgent(ProductAgent)            # XSP 확장
```

### 4.2 Agent별 지식 도메인

| Agent | 검색 대상 | 구조화 데이터 소스 |
|-------|----------|------------------|
| **OpenFrame MVS** | tjesmgr, tacfmgr, oscmgr 명령어, JCL, 에러코드 | `summaries/commands/OpenFrame_TJES_MVS.md`, `error-codes/BASE-*.md` |
| **OpenFrame Base** | 데이터셋, VSAM, 카탈로그, 볼륨 관리 | `summaries/commands/OpenFrame_Base.md`, `glossary/*.md` |
| **Tibero** | SQL, 파라미터, 성능 튜닝 | `summaries/commands/Tibero*.md` |
| **Tmax** | 미들웨어 설정, tmboot/tmdown | `summaries/commands/Tmax*.md` |
| **OFASM** | 어셈블러 명령어, 마이그레이션 | `summaries/commands/OFASM*.md` |
| **OFCOBOL** | COBOL 변환, 런타임 옵션 | `summaries/commands/OFCOBOL*.md` |
| **MSP** | JES2/JES3, SMS, HSM | `summaries/commands/MSP*.md` |
| **VOS3** | VOS3/ACOS 시스템 | `summaries/commands/VOS3*.md` |

---

## 5. 질문 라우터 설계 (다단계 확인)

### 5.1 분류 흐름

```
사용자 쿼리
    │
    ▼
[1단계] 기존 ProductRouterService (키워드+정규식)
    → 제품별 confidence score 계산
    │
    ▼
[2단계] 분류 결과 판정
    ├─ 최고 점수 >= 0.8 AND 2위와 차이 >= 0.3
    │   → 확정 라우팅 (되묻기 없음)
    │
    ├─ 최고 점수 0.5~0.8 OR 2위와 차이 < 0.3
    │   → 사용자에게 되묻기 (후보 제시)
    │
    └─ 최고 점수 < 0.5
        → "어떤 제품에 대한 질문인가요?" (전체 목록 제시)
```

### 5.2 되묻기 응답 형식 (SSE 이벤트)

```json
{
  "type": "clarification_needed",
  "candidates": [
    {"product": "openframe_mvs", "confidence": 0.72, "reason": "tjesmgr 키워드 감지"},
    {"product": "tmax", "confidence": 0.55, "reason": "배치 관련 용어 감지"}
  ],
  "message": "다음 중 어떤 제품에 대한 질문인가요?"
}
```

---

## 6. 응답 생성 전략

### 6.1 정형 질문 → 템플릿 기반 응답 (LLM 불필요)

**대상**: 커맨드 사용법, 파라미터 설명, 에러 코드 해석 (전체 질문의 ~70-80%)

```
[검색 결과]
  명령어: tjesmgr BOOT
  구문: tjesmgr BOOT [node_name]
  설명: TJES 노드를 초기화합니다
  파라미터: node_name (선택, 대상 노드명)
  출처: OpenFrame_TJES_MVS.pdf, p.45

[템플릿 응답]
  ## tjesmgr BOOT

  **구문**: `tjesmgr BOOT [node_name]`
  **설명**: TJES 노드를 초기화합니다.
  **파라미터**:
  - `node_name` (선택): 대상 노드명

  📖 출처: OpenFrame_TJES_MVS.pdf, p.45
```

**판별 기준**:
| 패턴 | 정형 여부 | 예시 |
|------|----------|------|
| 명령어 사용법 | 정형 | "tjesmgr BOOT 사용법", "idcams 명령어" |
| 에러 코드 | 정형 | "-5212 에러", "ABEND S0C7 원인" |
| 파라미터 설명 | 정형 | "SORTWORK DD 할당 크기", "LRECL 설정" |
| 설정 방법 | 정형 | "tjes.conf 설정", "ds.conf 옵션" |
| 비교/추천 | 비정형 | "SORT 성능 개선 방법" |
| 원인 분석 | 비정형 | "배치 잡이 안 뜨는 이유" |
| 마이그레이션 | 비정형 | "메인프레임에서 OpenFrame으로 이전 시 주의사항" |

### 6.2 비정형 질문 → 제한된 LLM 생성 + 검증

**시스템 프롬프트 규칙**:
1. 반드시 `[출처: 문서명, 페이지]` 태그와 함께 답변
2. 제공된 문서 내용에 없는 정보는 절대 포함하지 않음
3. 확실하지 않으면 "해당 내용은 문서에서 확인되지 않습니다" 응답

**사후 검증**:
- LLM 응답의 각 문장을 소스 청크와 cosine similarity 비교
- 유사도 >= 0.7 → 🟢 확인됨
- 유사도 0.4~0.7 → 🟡 추정됨 (추가 확인 권장)
- 유사도 < 0.4 → 🔴 미확인 → 해당 문장 제거 또는 경고 표시

---

## 7. API 엔드포인트 설계

### 7.1 새 엔드포인트 (`/api/v1/agentic-rag`)

| 엔드포인트 | Method | 용도 |
|-----------|--------|------|
| `/health` | GET | 서비스 상태 확인 |
| `/products` | GET | 지원 제품 목록 + Agent 상태 |
| `/classify` | POST | 쿼리 분류 (다단계 확인) |
| `/chat` | POST | 동기식 Agent 채팅 |
| `/stream` | POST | SSE 스트리밍 Agent 채팅 |
| `/stream` SSE events | - | `classification`, `clarification_needed`, `template_response`, `llm_token`, `verification`, `sources`, `done` |

### 7.2 SSE 이벤트 흐름

```
1. classification     → 제품 분류 결과
2. clarification_needed → (선택) 되묻기 필요 시
3. search_progress    → 검색 진행 상태
4. template_response  → (정형) 템플릿 기반 전체 응답
   OR
   llm_token         → (비정형) LLM 스트리밍 토큰
5. verification       → 신뢰도 검증 결과 (🟢🟡🔴)
6. sources           → 출처 문서 목록
7. done              → 완료
```

---

## 8. 구현 순서 (Phase별)

### Phase 1: Frontend 메뉴 교체 + 기본 페이지 (1일)
- [ ] Sidebar: `analytics` → `agenticRag` 교체
- [ ] App.tsx: 라우트 교체
- [ ] `AgenticRAGPage.tsx` 기본 구조 생성
- [ ] i18n 번역 추가 (en, ko, ja)

### Phase 2: Backend 모델 + 라우터 (1일)
- [ ] `models/agentic_rag.py` Pydantic 모델 정의
- [ ] `routers/agentic_rag.py` API 엔드포인트 구현
- [ ] `main.py`에 라우터 등록

### Phase 3: 다단계 질문 라우터 (1일)
- [ ] `QueryRouter` 서비스 (기존 ProductRouterService 확장)
- [ ] 되묻기 로직 구현
- [ ] 프론트엔드 되묻기 UI

### Phase 4: 제품별 Agent 구현 (2일)
- [ ] `ProductAgent` 베이스 클래스
- [ ] 주요 3개 Agent 우선 구현 (OpenFrame MVS, Tibero, Tmax)
- [ ] Agent별 구조화 검색 (커맨드, 에러코드, 설정)
- [ ] 나머지 6개 Agent 구현 (Base, OFASM, OFCOBOL, MSP, VOS3, XSP)

### Phase 5: 템플릿 기반 응답 + 검증 레이어 (2일)
- [ ] `TemplateResponseBuilder` 정형 응답 생성
- [ ] 질문 유형 판별 로직
- [ ] `ResponseVerifier` 사후 검증 레이어
- [ ] 신뢰도 배지 시스템

### Phase 6: 프론트엔드 완성 (1일)
- [ ] SSE 스트리밍 통합
- [ ] 소스 인용 패널
- [ ] 신뢰도 배지 UI
- [ ] 제품 선택 카드 UI

### Phase 7: 테스트 및 최적화 (1일)
- [ ] E2E Hallucination 테스트
- [ ] 기존 OpenFrame RAG 테스트 케이스 호환
- [ ] 성능 프로파일링

---

## 9. 기존 시스템과의 관계

### 9.1 공존 전략

| 항목 | 결정 |
|------|------|
| 기존 `/openframe-rag` | **유지** (기존 사용자 호환) |
| 새 `/agentic-rag` | **신규 추가** |
| Sidebar 메뉴 | `analytics` 제거, `agenticRag` 추가 |
| 기존 `openframeRag` 메뉴 | **유지** (점진적 마이그레이션) |

### 9.2 장기 마이그레이션 계획

```
Phase A (현재): analytics → agentic-rag 교체, 두 시스템 공존
Phase B (안정화 후): openframe-rag 기능을 agentic-rag로 통합
Phase C (완료 후): openframe-rag 제거 (또는 redirect)
```

---

## 10. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 구조화 DB 데이터 부족 | 템플릿 응답 커버리지 낮음 | 기존 요약본(summaries/) 우선 활용, 점진적 보강 |
| 제품 분류 정확도 | 잘못된 Agent 라우팅 | 되묻기 임계값 보수적 설정 (0.7 이상만 자동) |
| 검증 레이어 오탐 | 정확한 응답도 🟡로 표시 | 유사도 임계값 튜닝, 사용자 피드백 반영 |
| 기존 시스템 호환성 | 기존 사용자 혼란 | 두 시스템 공존, 점진적 마이그레이션 |

---

## 11. 성공 기준

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| 정형 질문 커버리지 | >= 70% | 템플릿 응답 비율 측정 |
| 환각 감소율 | 기존 대비 50% 이상 감소 | E2E Hallucination 테스트 (45개 케이스) |
| 제품 분류 정확도 | >= 85% | 되묻기 포함 최종 정확도 |
| 응답 시간 | 정형 < 500ms, 비정형 < 3s | 서버 로그 p95 |
| 사후 검증 통과율 | >= 90% (🟢+🟡) | 검증 레이어 로그 |

---

## 12. 영향 받는 파일 요약

### 신규 생성 파일

```
Backend:
  app/api/routers/agentic_rag.py               # API 라우터
  app/api/models/agentic_rag.py                 # Pydantic 모델
  app/api/services/agentic_rag_service.py       # 오케스트레이터
  app/api/services/query_router_service.py      # 다단계 라우터
  app/api/services/template_response_builder.py # 템플릿 응답
  app/api/services/response_verifier_service.py # 사후 검증
  app/api/services/structured_knowledge_store.py # 구조화 DB
  app/api/agents/agents/product_agents/         # 제품별 Agent 디렉토리
    __init__.py
    base_product_agent.py
    openframe_mvs_agent.py
    openframe_base_agent.py
    tibero_agent.py
    tmax_agent.py
    ofasm_agent.py
    ofcobol_agent.py
    msp_agent.py
    vos3_agent.py
    xsp_agent.py

Frontend:
  kms-portal-ui/src/pages/AgenticRAGPage.tsx    # 메인 페이지
  kms-portal-ui/src/api/agentic-rag.api.ts      # API 클라이언트
```

### 수정 파일

```
Frontend:
  kms-portal-ui/src/components/Sidebar.tsx       # 메뉴 교체
  kms-portal-ui/src/App.tsx                      # 라우트 교체
  kms-portal-ui/src/i18n/locales/en/common.json  # 번역
  kms-portal-ui/src/i18n/locales/ko/common.json  # 번역
  kms-portal-ui/src/i18n/locales/ja/common.json  # 번역

Backend:
  app/api/main.py                                # 라우터 등록
```
