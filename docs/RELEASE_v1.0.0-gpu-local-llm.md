# Release Notes: v1.0.0-gpu-local-llm

**Release Date**: 2026-01-24
**Branch**: `feature/gpu-local-llm-stable`
**Previous Version**: `v1.0.0-cpu-local-llm`

---

## Overview

`v1.0.0-gpu-local-llm`은 기존 CPU 기반 RAG 시스템을 GPU 가속 기반의 **AI Driven RAG 시스템**으로 업그레이드한 버전입니다.

주요 개선사항:
- **AI Driven RAG**: Auto Agent 기반 지능형 질의 처리
- **Hallucination Prevention**: 5단계 다중 방어 아키텍처
- **Auto LLM Learning**: 사용자 피드백 기반 자동 학습

---

## Hardware Requirements

### GPU Version (v1.0.0-gpu-local-llm)
| Component | Requirement |
|-----------|-------------|
| GPU | NVIDIA A100 40GB x 8 (권장) 또는 RTX 4090 24GB x 2 (최소) |
| RAM | 128GB+ |
| Storage | NVMe SSD 1TB+ |
| CUDA | 12.1+ |

### CPU Version (v1.0.0-cpu-local-llm) 비교
| Component | CPU Version | GPU Version |
|-----------|-------------|-------------|
| LLM Inference | Ollama (CPU) | NVIDIA NIM (GPU) |
| Embedding | Local CPU | NV-EmbedQA-Mistral (GPU) |
| Response Time | 5-15초 | 0.5-2초 |
| Concurrent Users | ~10명 | ~100명+ |

---

## Table of Contents

1. [AI Driven RAG System](#1-ai-driven-rag-system)
2. [Hallucination Prevention](#2-hallucination-prevention)
3. [Auto LLM Learning](#3-auto-llm-learning)
4. [Architecture Diagram](#4-architecture-diagram)
5. [API Changes](#5-api-changes)
6. [Configuration](#6-configuration)
7. [Migration Guide](#7-migration-guide)

---

## 1. AI Driven RAG System

### 1.1 Auto Agent Orchestrator

CPU 버전의 단순 RAG 파이프라인을 **Meta-Agent 기반 지능형 오케스트레이션**으로 업그레이드했습니다.

```
[CPU Version - Simple Pipeline]
Query → Vector Search → LLM Generation → Response

[GPU Version - AI Driven Pipeline]
Query → Clarification → Planner Agent → Parallel Sub-agents → Verifier Agent → Response
```

#### 핵심 컴포넌트

| Component | 역할 | 파일 |
|-----------|------|------|
| **Planner Agent** | 작업 분해 및 실행 계획 수립 | `app/api/agents/auto_agent/planner_agent.py` |
| **Verifier Agent** | 결과 검증 및 Grounding 체크 | `app/api/agents/auto_agent/verifier_agent.py` |
| **Memory Manager** | 대화 컨텍스트 관리 | `app/api/agents/auto_agent/memory_manager.py` |
| **Confidence Scorer** | 응답 신뢰도 평가 | `app/api/agents/auto_agent/confidence_scorer.py` |

#### 실행 흐름

```python
# Auto Agent Execution Flow
async def execute(self, task: str) -> AutoAgentExecutionResult:
    # 1. Load context from memory
    context = await self.memory_manager.load_context()

    # 2. MANDATORY: Create execution plan
    plan = await self.planner_agent.create_plan(task, context)

    # 3. Execute sub-agents in parallel
    results = await self.parallel_executor.execute(plan.tasks)

    # 4. MANDATORY: Verify results against original task
    verified = await self.verifier_agent.verify(task, results)

    # 5. Compose final answer (strip reasoning)
    return self.answer_composer.compose(verified)
```

### 1.2 Query Clarification (신규 기능)

애매한 용어가 포함된 질의를 사전 감지하여 사용자에게 명확화를 요청합니다.

**예시**: "MFS 설정 방법" 질의 시
```
┌─────────────────────────────────────────┐
│  'MFS'가 여러 의미를 가질 수 있습니다:    │
│                                         │
│  ○ JEUS MFS (Managed File System)       │
│  ○ Tmax MFS (Message File System)       │
│  ○ WebtoB MFS (Multi-File System)       │
│                                         │
│  ☐ 이 선택을 기억하기                    │
│                                         │
│         [확인]    [취소]                 │
└─────────────────────────────────────────┘
```

#### 주요 기능

| 기능 | 설명 |
|------|------|
| **Ambiguous Term Detection** | DB에 등록된 애매한 용어 자동 감지 |
| **User Preference Memory** | "기억하기" 선택 시 다음 질의부터 자동 적용 |
| **ML-based Recommendation** | 임베딩 유사도 기반 관련 용어 추천 (Phase 2) |
| **Auto Resolution** | 저장된 선호도로 자동 해결 |

#### API Endpoints

```bash
# 질의 명확화 필요 여부 확인
POST /api/v1/clarification/check
{
  "query": "MFS 설정 방법",
  "user_id": "user123"
}

# 사용자 선택 적용
POST /api/v1/clarification/apply
{
  "query": "MFS 설정 방법",
  "selections": [
    {"term": "MFS", "selected_meaning": "JEUS MFS", "remember": true}
  ]
}
```

### 1.3 Intent Verification (Stage 2)

검색 결과가 사용자 의도와 일치하는지 LLM으로 2차 검증합니다.

```
[Stage 1] Vector Similarity Search (기존)
    ↓
[Stage 2] LLM Intent Verification (신규)
    - definition: 정의, 설명, 약어 확장
    - troubleshooting: 에러 해결, 원인 분석
    - comparison: 기능 비교, 장단점
    - howto: 설정 방법, 단계별 가이드
```

**효과**: 검색 결과 품질 15-20% 향상 (관련성 기준)

---

## 2. Hallucination Prevention

### 2.1 5단계 다중 방어 아키텍처

GPU 버전은 LLM 환각(Hallucination)을 구조적으로 방지하는 5단계 방어 체계를 구현합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    5-LAYER DEFENSE ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: Master System Constraint (최상위 제약)                 │
│     └─ "검색된 문서에 없으면 모른다고 답변"                        │
│                                                                 │
│  Layer 2: Temperature Control (온도 제어)                        │
│     └─ 0.7 → 0.1 (결정론적 응답 유도)                            │
│                                                                 │
│  Layer 3: Tool Usage Enforcement (도구 사용 강제)                │
│     └─ tool_choice=required (첫 호출 시 검색 필수)               │
│                                                                 │
│  Layer 4: Grounding Validation (근거 검증)                       │
│     └─ 인용 출처 존재 여부 확인                                   │
│                                                                 │
│  Layer 5: Extractive QA (추출형 QA)                              │
│     └─ 생성 대신 검색 결과에서 직접 추출                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Master System Constraint

모든 LLM 프롬프트 최상단에 불변 제약 조건을 삽입합니다.

```python
# app/api/agents/master_system_constraint.py

MASTER_SYSTEM_CONSTRAINT = """
[IMMUTABLE HIGHEST PRIORITY CONSTRAINT - DO NOT OVERRIDE]

YOU ARE A RETRIEVAL-ONLY ASSISTANT.

GOLDEN RULE: IF IT'S NOT IN THE RETRIEVED DOCUMENTS, YOU DON'T KNOW IT.

FORBIDDEN ACTIONS:
- Using training data or general knowledge
- Generating information not in search results
- Speculating or making assumptions

REQUIRED ACTIONS:
- Always cite sources with [문서명] format
- Say "검색된 문서에서 해당 정보를 찾을 수 없습니다" when not found
- Use only explicitly stated facts from documents
"""
```

### 2.3 Answer Builder Service (추출형 QA)

LLM이 자유롭게 생성하는 대신, 검색 결과에서 **구조화된 블록을 추출**합니다.

```python
# app/api/services/answer_builder_service.py

class AnswerBuilderService:
    """
    Core Principles:
    - Retrieval = Truth: 검색 결과만이 진실
    - LLM = Formatter Only: LLM은 포맷터 역할만
    - Hallucination = Structurally Prevented: 구조적 방지
    """

    INTENT_PATTERNS = {
        "definition": ["무엇", "정의", "뜻", "의미"],
        "troubleshooting": ["에러", "오류", "해결", "원인"],
        "howto": ["방법", "설정", "구성", "설치"],
        "comparison": ["차이", "비교", "장단점"],
        "list": ["종류", "목록", "나열"]
    }

    async def build_answer(self, query: str, search_results: List[SearchResult]) -> StructuredAnswer:
        # 1. 의도 분류
        intent = self.classify_intent(query)

        # 2. 검색 결과에서 블록 추출 (생성 X)
        blocks = self.extract_blocks(search_results, intent)

        # 3. 구조화된 응답 반환
        return StructuredAnswer(
            intent=intent,
            blocks=blocks,
            citations=self.extract_citations(search_results)
        )
```

### 2.4 Answer Formatter Service (읽기 전용 포맷팅)

추출된 블록의 **내용을 변경하지 않고** 포맷만 조정합니다.

```python
# app/api/services/answer_formatter_service.py

class AnswerFormatterService:
    """
    ALLOWED OPERATIONS:
    - Reorder blocks for better flow
    - Add predefined transition phrases
    - Adjust heading levels

    FORBIDDEN OPERATIONS:
    - Add new facts or information
    - Modify original content text
    - Remove source citations
    """

    BLOCK_ORDER_PRIORITY = [
        BlockType.NO_ANSWER,      # 항상 첫 번째
        BlockType.HEADING,
        BlockType.TEXT,
        BlockType.LIST,
        BlockType.CODE,
        BlockType.TABLE,
        BlockType.QUOTE,
        BlockType.IMAGE,
        BlockType.SOURCE_CITATION  # 항상 마지막
    ]
```

### 2.5 Thinking Tag Filtering

LLM의 내부 추론 과정(`<think>...</think>`)을 사용자에게 노출하지 않습니다.

```python
# app/api/agents/executor.py

def filter_thinking_tags(response: str) -> str:
    """Strip thinking patterns from LLM output"""
    # Remove <think>...</think> tags
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

    # Remove other thinking patterns
    patterns = [
        r'Let me think.*?\.',
        r'I need to.*?\.',
        r'First, I.*?\.'
    ]
    for pattern in patterns:
        response = re.sub(pattern, '', response, flags=re.IGNORECASE)

    return response.strip()
```

---

## 3. Auto LLM Learning

### 3.1 개요

사용자 피드백(👍/👎)을 자동으로 학습하여 응답 품질을 지속적으로 개선합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    AUTO LLM LEARNING PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query ──→ System Response ──→ User Feedback (👍/👎)       │
│                                           │                     │
│                    ┌──────────────────────┴────────────────┐    │
│                    │                                       │    │
│              Verified Knowledge               Learning LLM      │
│                 Store (DB)                    Service (GPU)     │
│              (similarity ≥ 0.85)           (confidence ≥ 0.6)  │
│                    │                              │             │
│                    └──────────┬───────────────────┘             │
│                               │                                 │
│                    Daily QLoRA Fine-tuning                      │
│                      (00:00 UTC)                                │
│                               │                                 │
│                    Updated Model Adapters                       │
│                               │                                 │
│                    Improved Responses                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Verified Knowledge Store

👍 피드백을 받은 Q&A 쌍을 저장하고, 유사 질의에 우선 활용합니다.

```python
# app/api/services/verified_knowledge_service.py

class VerifiedKnowledgeService:
    MIN_SIMILARITY_THRESHOLD = 0.85

    async def search_verified(self, query: str) -> Optional[VerifiedKnowledge]:
        """Search for verified knowledge with similarity >= 0.85"""
        query_embedding = await self.embed(query)

        results = await self.repository.search_by_embedding(
            query_embedding,
            threshold=self.MIN_SIMILARITY_THRESHOLD
        )

        if results:
            return results[0]  # Highest similarity match
        return None

    async def store_verified(self, query: str, answer: str, user_id: str):
        """Store positively-rated Q&A pair"""
        knowledge = VerifiedKnowledge(
            query=query,
            answer=answer,
            query_embedding=await self.embed(query),
            source="user_feedback",
            verified_by=user_id,
            created_at=datetime.utcnow()
        )
        await self.repository.save(knowledge)
```

### 3.3 Learning LLM Service

**QLoRA (Quantized Low-Rank Adaptation)**를 사용하여 메모리 효율적으로 파인튜닝합니다.

```python
# app/api/services/learning_llm_service.py

class LearningLLMService:
    """
    Model: Qwen2.5-7B-Instruct + QLoRA
    VRAM: ~8GB (4-bit quantization)
    Training: Daily at 00:00 UTC
    """

    def __init__(self):
        self.model_name = "Qwen/Qwen2.5-7B-Instruct"
        self.adapter_path = "/opt/kms/models/qlora_adapters/"
        self.min_confidence = 0.6
        self.high_confidence = 0.8

    async def generate(self, query: str) -> LearningLLMResponse:
        """Generate response with confidence score"""
        response = await self.model.generate(query)
        confidence = self.calculate_confidence(response)

        return LearningLLMResponse(
            answer=response,
            confidence=confidence,
            used_adapter=self.current_adapter_version
        )
```

### 3.4 Smarter RAG Priority

응답 생성 시 다음 우선순위를 따릅니다:

```
Priority 1: Verified Knowledge (similarity ≥ 0.85)
    └─ 사용자가 검증한 정확한 답변

Priority 2: Learning LLM (confidence ≥ 0.6)
    └─ 학습된 패턴 기반 답변

Priority 3: General RAG
    └─ 문서 검색 + LLM 생성
```

### 3.5 Training Pipeline

```bash
# 자동 학습 스케줄 (매일 00:00 UTC)
VERIFIED_KNOWLEDGE_TRAINING_SCHEDULE="0 0 * * *"

# 수동 학습 트리거
POST /api/v1/verified-knowledge/training/trigger
{
  "min_samples": 100,      # 최소 학습 샘플 수
  "include_unlearn": true  # 👎 피드백 반영
}
```

### 3.6 Feedback API

```bash
# 빠른 피드백 (👍/👎)
POST /api/v1/feedback/quick
{
  "message_id": "msg_123",
  "conversation_id": "conv_456",
  "feedback_type": "positive",  # or "negative"
  "query": "JEUS 설치 방법",
  "answer": "1. 다운로드..."
}

# 상세 피드백
POST /api/v1/feedback/detailed
{
  "message_id": "msg_123",
  "feedback_type": "negative",
  "categories": ["inaccurate", "incomplete"],
  "comment": "버전 정보가 잘못되었습니다"
}

# 피드백 통계
GET /api/v1/feedback/stats?user_id=user123
```

---

## 4. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         v1.0.0-gpu-local-llm Architecture                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────────────────────────────────────────┐    │
│  │   Frontend  │    │                  Backend (FastAPI)               │    │
│  │  (React 18) │    │                                                  │    │
│  │             │    │  ┌─────────────────────────────────────────┐    │    │
│  │ ┌─────────┐ │    │  │           Query Clarification           │    │    │
│  │ │AgentChat│─┼────┼─→│  (Ambiguous Term Detection + Resolve)   │    │    │
│  │ └─────────┘ │    │  └──────────────────┬──────────────────────┘    │    │
│  │             │    │                     │                           │    │
│  │ ┌─────────┐ │    │  ┌──────────────────▼──────────────────────┐    │    │
│  │ │Feedback │─┼────┼─→│         Auto Agent Orchestrator         │    │    │
│  │ │  UI     │ │    │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  │    │    │
│  │ └─────────┘ │    │  │  │ Planner │→ │Executor │→ │Verifier │  │    │    │
│  │             │    │  │  └─────────┘  └────┬────┘  └─────────┘  │    │    │
│  └─────────────┘    │  └────────────────────┼────────────────────┘    │    │
│                     │                       │                         │    │
│                     │       ┌───────────────┼───────────────┐         │    │
│                     │       │               │               │         │    │
│                     │  ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐   │    │
│                     │  │   RAG   │    │    IMS    │   │   Code    │   │    │
│                     │  │  Agent  │    │   Agent   │   │   Agent   │   │    │
│                     │  └────┬────┘    └───────────┘   └───────────┘   │    │
│                     │       │                                         │    │
│                     │  ┌────▼────────────────────────────────────┐    │    │
│                     │  │        Hallucination Prevention         │    │    │
│                     │  │  ┌─────────────────────────────────┐    │    │    │
│                     │  │  │ Master Constraint │ Temp 0.1    │    │    │    │
│                     │  │  │ Tool Enforce │ Grounding Check  │    │    │    │
│                     │  │  │ Answer Builder │ Answer Formatter│   │    │    │
│                     │  │  └─────────────────────────────────┘    │    │    │
│                     │  └─────────────────────────────────────────┘    │    │
│                     │                                                  │    │
│                     │  ┌─────────────────────────────────────────┐    │    │
│                     │  │           Auto LLM Learning             │    │    │
│                     │  │  ┌─────────────┐  ┌─────────────────┐   │    │    │
│                     │  │  │  Verified   │  │   Learning LLM  │   │    │    │
│                     │  │  │  Knowledge  │  │   (QLoRA 7B)    │   │    │    │
│                     │  │  │   Store     │  │                 │   │    │    │
│                     │  │  └──────┬──────┘  └────────┬────────┘   │    │    │
│                     │  │         └────────┬─────────┘            │    │    │
│                     │  │                  │                      │    │    │
│                     │  │         Daily Training (00:00)          │    │    │
│                     │  └─────────────────────────────────────────┘    │    │
│                     └──────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         GPU Infrastructure                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │ Nemotron    │  │ NV-EmbedQA  │  │  Mistral    │  │  Learning   │   │  │
│  │  │ Nano 9B     │  │ Mistral 7B  │  │  NeMo 12B   │  │  LLM 7B     │   │  │
│  │  │ (RAG LLM)   │  │ (Embedding) │  │ (Code LLM)  │  │ (QLoRA)     │   │  │
│  │  │ Port 12800  │  │ Port 12801  │  │ Port 12802  │  │ cuda:1      │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. API Changes

### 신규 API Endpoints

| Endpoint | Method | 설명 |
|----------|--------|------|
| `/api/v1/clarification/check` | POST | 질의 명확화 필요 여부 확인 |
| `/api/v1/clarification/apply` | POST | 명확화 선택 적용 |
| `/api/v1/clarification/terms` | GET | 애매한 용어 목록 |
| `/api/v1/clarification/preferences` | GET | 사용자 선호도 조회 |
| `/api/v1/feedback/quick` | POST | 빠른 피드백 (👍/👎) |
| `/api/v1/feedback/detailed` | POST | 상세 피드백 |
| `/api/v1/feedback/stats` | GET | 피드백 통계 |
| `/api/v1/verified-knowledge/search` | GET | 검증된 지식 검색 |
| `/api/v1/verified-knowledge/training/trigger` | POST | 수동 학습 트리거 |
| `/api/v1/verified-knowledge/learning-llm/status` | GET | Learning LLM 상태 |

### 변경된 API

| Endpoint | 변경사항 |
|----------|----------|
| `/api/v1/agent/stream` | Auto Agent 지원, `use_auto_agent` 파라미터 추가 |
| `/api/v1/query` | Intent Verification (Stage 2) 적용 |

---

## 6. Configuration

### Environment Variables (신규)

```bash
# .env

# === Auto Agent ===
ENABLE_AUTO_AGENT=true
AUTO_AGENT_MAX_RETRIES=2
AUTO_AGENT_TIMEOUT_SECONDS=120

# === Query Clarification ===
ENABLE_QUERY_CLARIFICATION=true
CLARIFICATION_MIN_CONFIDENCE=0.6

# === Hallucination Prevention ===
LLM_TEMPERATURE=0.1
ENABLE_MASTER_CONSTRAINT=true
ENABLE_GROUNDING_CHECK=true

# === Learning LLM ===
ENABLE_LEARNING_LLM=true
LEARNING_LLM_AUTO_LOAD=false
LEARNING_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LEARNING_LLM_DEVICE=cuda:1
LEARNING_LLM_LOAD_IN_4BIT=true

# === Verified Knowledge ===
VERIFIED_KNOWLEDGE_MIN_SIMILARITY=0.85
VERIFIED_KNOWLEDGE_TRAINING_SCHEDULE="0 0 * * *"

# === GPU LLM Services ===
NIM_LLM_URL=http://localhost:12800
NIM_EMBEDDING_URL=http://localhost:12801
NIM_CODE_LLM_URL=http://localhost:12802
```

---

## 7. Migration Guide

### CPU → GPU 마이그레이션

1. **하드웨어 준비**
   ```bash
   # NVIDIA 드라이버 확인
   nvidia-smi

   # CUDA 버전 확인 (12.1+ 필요)
   nvcc --version
   ```

2. **NIM 컨테이너 배포**
   ```bash
   # docker-compose로 GPU 서비스 시작
   docker-compose -f docker/docker-compose.gpu.yml up -d
   ```

3. **환경 변수 업데이트**
   ```bash
   # .env 파일에 GPU 설정 추가
   cp .env.example.gpu .env
   vim .env  # GPU 관련 설정 확인
   ```

4. **데이터베이스 마이그레이션**
   ```bash
   # 신규 테이블 생성
   python -m app.api.migrations.run

   # 필요한 테이블:
   # - ambiguous_terms
   # - user_term_preferences
   # - verified_knowledge
   # - learning_llm_training_batches
   ```

5. **서비스 재시작**
   ```bash
   ./scripts/server.sh all restart
   ```

---

## Appendix

### A. File Locations

| Feature | Files |
|---------|-------|
| Auto Agent | `app/api/agents/auto_agent/*.py` |
| Query Clarification | `app/api/services/query_clarification_service.py` |
| Hallucination Prevention | `app/api/agents/master_system_constraint.py` |
| Answer Builder | `app/api/services/answer_builder_service.py` |
| User Feedback | `app/api/services/user_feedback_service.py` |
| Verified Knowledge | `app/api/services/verified_knowledge_service.py` |
| Learning LLM | `app/api/services/learning_llm_service.py` |

### B. Related Documentation

- [SMARTER_RAG_SYSTEM.md](./SMARTER_RAG_SYSTEM.md) - Smarter RAG 시스템 상세
- [SMARTER_RAG_GPU_SETUP.md](./SMARTER_RAG_GPU_SETUP.md) - GPU 설정 가이드
- [tech-seminar-hallucination-prevention.md](./tech-seminar-hallucination-prevention.md) - 환각 방지 기술 세미나
- [DEEP_AGENTS_INTEGRATION.md](./DEEP_AGENTS_INTEGRATION.md) - Deep Agents 통합 가이드

---

**Copyright 2026 HybridRAG KMS Team**
