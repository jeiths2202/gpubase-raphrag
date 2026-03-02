# AGENT.md

KMS 프로젝트의 AI Agent 시스템 및 QLoRA 학습 파이프라인 종합 가이드입니다.

> **관련 문서**: [CLAUDE.md](CLAUDE.md) | [app/api/agents/CLAUDE.md](app/api/agents/CLAUDE.md) | [app/api/CLAUDE.md](app/api/CLAUDE.md)

---

## 1. 시스템 개요

KMS는 3개의 독립적 AI Agent 레이어로 구성됩니다:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Teams (Pattern Layer)                   │
│  Pattern A~E: 병렬검색, 경쟁가설, 도메인전문가, 멀티제품, 자기개선  │
├─────────────────────────────────────────────────────────────────┤
│                  Agentic RAG (Core RAG Layer)                   │
│  6-Phase: 라우팅→검색→검증→생성→후검증→소스                        │
├─────────────────────────────────────────────────────────────────┤
│              Base Agent System (Foundation Layer)                │
│  9 Agents: RAG, IMS, Code, Vision, Planner, Enhancement×4      │
├─────────────────────────────────────────────────────────────────┤
│                QLoRA Training Pipeline (Offline)                │
│  CPT → SFT (22 adapters) → DPO → vLLM Serving                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Agentic RAG System (6-Phase Pipeline)

> **진입점**: `app/api/routers/agentic_rag.py` → `app/api/services/agentic_rag_service.py`

### 2.1 파이프라인 흐름

```
사용자 질문: "tjesmgrのBOOTコマンドについて教えてください"
    │
    ▼ Phase 1: Product Routing
ProductRouterService._calculate_score()
    ├─ keyword 매칭 (0.15 × weight)
    ├─ pattern 매칭 (0.3 × weight)
    └─ 결과: openframe_mvs (conf: 0.85) → CONFIRMED
    │
    ▼ Phase 2: Query Classification
QueryRouter → STRUCTURED (명령어 질문)
    │
    ▼ Phase 3: Two-Stage Retrieval
    ├─ Stage 1: Summary 검색 (<10ms, 파일시스템)
    │   └─ commands/OpenFrame_TJES_MVS.md → tjesmgr BOOT 정보
    ├─ Stage 2: PDF RAG 검색 (BM25 + keyword, LLM 미사용)
    │   └─ StructuredKnowledgeStore → PyMuPDF TOC 기반
    └─ (Optional) Web Doc Fast Path (score >= 0.9)
    │
    ▼ Phase 4: Response Generation
    ├─ STRUCTURED → Template 응답 (LLM 미사용, 환각 0%)
    └─ FREEFORM → QLoRA LLM 생성 (검색 결과에 제한)
    │
    ▼ Phase 5: Post-Verification (FREEFORM만)
ResponseVerifier → 코사인 유사도 per sentence
    │
    ▼ Phase 6: Source Attribution
ProductSources: learning_llm, vector_search, graph_search
```

### 2.2 핵심 서비스

| 서비스 | 파일 | 역할 |
|--------|------|------|
| `AgenticRAGService` | `services/agentic_rag_service.py` | 메인 오케스트레이터 |
| `ProductRouterService` | `services/product_router_service.py` | 제품 라우팅 |
| `ManualRegistryService` | `services/manual_registry_service.py` | 19개 제품 동적 탐색 |
| `DynamicProductAgentService` | `services/dynamic_product_agent_service.py` | 제품별 에이전트 생성 |
| `StructuredKnowledgeStore` | `services/structured_knowledge_store.py` | PDF 파싱 + 검색 |
| `SummarySearchService` | `services/summary_search_service.py` | 요약본 검색 |
| `WebDocSearchService` | `services/web_doc_search_service.py` | docs.tmaxsoft.com 검색 |
| `ProductContextMemory` | `services/product_context_memory.py` | LangGraph Store 기반 메모리 |

### 2.3 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **검색 단계 LLM 미사용** | 검색은 deterministic (keyword + BM25) |
| **생성만 LLM 사용** | 검색 결과에 제한된 생성 |
| **구조화 질문 우선** | 70-80% 질문은 template 응답 (환각 0%) |
| **동적 제품 탐색** | `uploads/manuals/` 스캔 → 19개 제품 자동 발견 |

### 2.4 Product Router 점수 체계

```python
# ProductRouterService._calculate_score()
keyword_score = 0.15 * weight    # 키워드 매칭
pattern_score = 0.3 * weight     # 패턴 매칭 (정규식)
max_score = 1.5                  # 정규화 분모

# 결정 임계값
CONFIRMED:             conf >= 0.8 and gap >= 0.3
CLARIFICATION_NEEDED:  0.5 <= conf < 0.8
NO_MATCH:              conf < 0.5

# 자동 확정: 후보 1개 + conf >= 0.6 → CONFIRMED
```

### 2.5 제품 ID 매핑 주의사항

```
Router 출력:  openframe_mvs      (legacy ProductId 형식)
Web Doc:     mvs_openframe_7.1  (디렉토리명 형식)
PDF 경로:    uploads/manuals/MVS_Openframe_7.1/

→ _LEGACY_TO_WEB_DOC_PID dict (agentic_rag_service.py)로 변환
```

---

## 3. Agent Teams (5 Patterns)

> **진입점**: `app/api/services/agent_teams/team_orchestrator.py`
> **Feature Flags**: `config.py` → 모두 `default=False` (OFF 시 100% 원래 동작)

### 3.1 아키텍처

```
routers/agentic_rag.py
    ↓
TeamOrchestrator.stream_chat_enhanced()
    ├─ _any_pattern_enabled() == False → AgenticRAGService.stream_chat() 직접 위임
    └─ True → Feature Flag에 따라 패턴 적용
```

### 3.2 패턴 상세

| 패턴 | Flag | 파일 | 동작 |
|------|------|------|------|
| **A: Parallel Retrieval** | `AGENT_TEAMS_PARALLEL_RETRIEVAL` | `parallel_retrieval.py` | Web Doc + PDF RAG `asyncio.gather` 병렬 검색 |
| **B: Competitive Hypothesis** | `AGENT_TEAMS_COMPETITIVE_HYPOTHESIS` | `competitive_hypothesis.py` | 다중 temperature로 경쟁 가설 → 룰 기반 평가 |
| **C: Domain Specialist** | `AGENT_TEAMS_DOMAIN_SPECIALIST` | `domain_specialist.py` | 관련 제품 QLoRA 어댑터 병렬 → confidence 선택 |
| **D: Multi-Product** | `AGENT_TEAMS_MULTI_PRODUCT` | `multi_product_collab.py` | 멀티제품 비교 → 제품별 독립 검색+LLM → 합성 |
| **E: Self-Improvement** | `AGENT_TEAMS_SELF_IMPROVEMENT` | `self_improvement.py` | 피드백 JSONL 축적 (`uploads/feedback/`) → 재학습 |

### 3.3 핵심 제약

- **Claude API 미사용** — 모든 LLM 호출은 vLLM (Qwen + QLoRA) 전용
- vLLM continuous batching → 병렬 LLM 호출 가능
- Flag OFF 시 기존 동작과 100% 동일 (zero overhead)

---

## 4. Base Agent System (Foundation)

> **상세 문서**: [app/api/agents/CLAUDE.md](app/api/agents/CLAUDE.md)

### 4.1 에이전트 목록

| Agent | 용도 | Deep Agent 지원 |
|-------|------|:--------------:|
| RAG Agent | 지식 기반 Q-A | O (권장) |
| IMS Agent | 이슈 관리 검색 | X |
| Code Agent | 코드 분석/생성 | X |
| Vision Agent | 이미지/차트 분석 | X |
| Planner Agent | 작업 계획 분해 | X |
| Enhancement Analyst | 기능 개선 분석 | X |
| Enhancement Architect | 아키텍처 설계 | X |
| Enhancement Coder | 코드 구현 | X |
| Enhancement QA | 품질 검증 | X |

### 4.2 실행 흐름

```
AgentRequest → Orchestrator → IntentClassifier → Registry → Agent.execute() → AgentResult
```

### 4.3 Deep Agents (LangGraph 기반)

```
adapters/deep_agent_adapter.py
    ├─ create_rag_deep_agent()     # vector_search, graph_query
    ├─ create_ims_deep_agent()     # IMS 이슈 검색
    ├─ create_vision_deep_agent()  # 이미지 분석
    ├─ create_code_deep_agent()    # 코드 생성/실행
    └─ create_planner_deep_agent() # 작업 분해/계획
```

| 설정 | 값 |
|------|-----|
| Recursion Limit | 25 |
| Timeout | 300s |
| Fallback | Deep Agent 실패 → 일반 Agent 자동 전환 |
| Checkpointer | MemorySaver (thread_id 기반) |

---

## 5. QLoRA 학습 파이프라인

### 5.1 학습 동기

- E2E 테스트 53% 실패율 (45개 중 21개) → LLM 환각
- 범용 LLM(Qwen 2.5)은 TmaxSoft 19개 제품 도메인 지식 부재
- 72B 풀 학습은 GPU 메모리 제약 → QLoRA (4-bit + LoRA) 채택

### 5.2 3-Phase 파이프라인

```
Phase 1: CPT (Continued Pre-Training)  ─── 도메인 지식 주입
    ↓ merge adapter
Phase 2: SFT (Supervised Fine-Tuning)  ─── 제품별 Q-A 학습 (×22 adapters)
    ↓ merge adapter
Phase 3: DPO (Direct Preference Opt.)  ─── 선호도 정렬, 환각 억제
    ↓
vLLM Serving (port 12815) ─── 24 QLoRA adapters 동적 로딩
```

### 5.3 Phase 상세

#### Phase 1: CPT

| 항목 | 값 |
|------|-----|
| 목적 | TmaxSoft 제품 도메인 지식 주입 |
| Base 모델 | Qwen2.5-72B-Instruct |
| 데이터 포맷 | Plain Text (PDF 원문, 72MB, ~34.3M tokens) |
| 문서 경계 | `<|endoftext|>` (token 151643), 4096 청크 |
| LoRA | r=64, α=128, LR=1e-5 |
| GPU | FSDP A100 ×4 (GPU 4-7) |
| 결과 | Perplexity 1.65, Loss 0.11 (2h 28m) |
| 스크립트 | `scripts/training/run_cpt_training.py` |

#### Phase 2: SFT

| 항목 | 값 |
|------|-----|
| 목적 | 제품별 instruction-response 학습 |
| Base 모델 | Qwen2.5-7B-Instruct × 22 제품 |
| 데이터 포맷 | ChatML (`<\|im_start\|>/<\|im_end\|>`) |
| LoRA | r=64, α=16, LR=2e-4 |
| 결과물 | 22개 제품별 Multi-LoRA 어댑터 |
| 학습 시간 | GPU 4개 병렬 → ~69분 전체 |
| 스크립트 | `scripts/training/train_multi_lora_v4.py` |

#### Phase 3: DPO

| 항목 | 값 |
|------|-----|
| 목적 | 환각 억제, 정확한 응답 선호 학습 |
| 데이터 | 2,000 preference 쌍 (chosen vs rejected) |
| 생성 전략 | E2E 교차제품(0.6%), 사실 변이(55.7%), Summary 교차(43.7%) |
| LoRA | r=32, α=64, LR=5e-6 |
| Beta (KL) | 0.1 |
| 결과 | 선호도 정확도 95%, Loss 75% 감소 (0.69→0.17) |
| 스크립트 | `scripts/training/run_dpo_training.py` |

### 5.4 데이터셋 버전 진화 (PDCA 반복)

```
v4 ── 22개 제품 기본 추출 (baseline)
 ↓
v5 ── 패러프레이즈 + 역번역 증강
 ↓
v6 ── 제품간 균형 조정
 ↓
v7 ── 시맨틱 클리닝 (코사인 유사도 0.95+ 중복 제거)
 ↓
v8 ── 패턴 기반 필터링 (NDB 제거, Q-A 불일치 40%+ 제거)
 ↓
v9 ── PDCA 2차 반복 정제 (현재 운용 버전)
```

### 5.5 RAFT 적용 (Retrieval Augmented Fine-Tuning)

> **논문**: "RAFT: Adapting Language Model to Domain Specific RAG" (arXiv:2403.10131)

| 개념 | KMS 적용 |
|------|----------|
| Oracle Document (D*) | Summary 기반 Two-Stage Retrieval 결과 |
| Distractor Document (Dk) | DPO 교차제품 문서 |
| Chain-of-Thought 인용 | `ResponseVerifier` 단어 겹침 검증 |
| 효과 | 무관 문서 무시 능력 강화 |

### 5.6 DPO 데이터 생성 (3가지 전략)

| 전략 | 비율 | 소스 | 방법 |
|------|------|------|------|
| E2E Cross-Product | 0.6% | `e2e/e2e_sentence_test.js` | `notExpected` 키워드로 오답 생성 |
| Factual Mutation | 55.7% | `uploads/summaries/` | 제품명/에러코드/설명 변이 |
| SFT Cross-Match | 43.7% | `multi_lora_v9_improved/` | 타 제품 정답을 오답으로 활용 |

```
스크립트: scripts/training/generate_dpo_data.py
출력:    uploads/training_text/dpo_pairs.json
포맷:    {prompt, chosen, rejected, source, metadata}
```

### 5.7 강화학습 확장 가능성 (Phase 4 후보)

| 기법 | 적용성 | 근거 |
|------|:------:|------|
| **GRPO** | ★★★★ | Critic 불필요, TRL 내장, QLoRA 호환, A100 1장 가능 |
| **RLVR** | ★★★ | 에러코드/명령어는 binary reward 가능, 자유질문은 한계 |
| PPO | ★★ | 4개 모델 동시 로딩 → GPU 메모리 제약 |
| RLAIF | ★★ | 외부 LLM API 의존 → 비용/보안 이슈 |

---

## 6. 학습 스크립트 전체 맵

### 6.1 파이프라인 실행

| 스크립트 | 용도 | 명령어 |
|----------|------|--------|
| `run_full_pipeline.py` | 전체 파이프라인 오케스트레이터 | `python scripts/training/run_full_pipeline.py --phase all --gpu 5` |
| `run_cpt_training.py` | Phase 1: CPT 학습 | `--phase cpt` |
| `train_multi_lora_v4.py` | Phase 2: SFT 학습 (22 어댑터) | `--phase sft` |
| `run_dpo_training.py` | Phase 3: DPO 학습 | `--phase dpo` |
| `merge_adapter.py` | LoRA → Base 모델 병합 | Phase 간 자동 호출 |
| `evaluate_perplexity.py` | Perplexity 평가 | CPT 후 자동 호출 |

### 6.2 데이터 준비

| 스크립트 | 용도 |
|----------|------|
| `extract_plain_text.py` | PDF → Plain Text 추출 (CPT용) |
| `prepare_mixing_data.py` | CPT 데이터 믹싱 (도메인 40%, 일본어 30%, 코드 20%, 수학 10%) |
| `convert_to_qlora.py` | 데이터셋 → QLoRA ChatML 포맷 변환 |
| `generate_dpo_data.py` | DPO preference 쌍 생성 (3가지 전략) |
| `generate_qa_dataset.py` | Q-A 데이터셋 생성 |

### 6.3 데이터 품질 관리

| 스크립트 | 버전 | 용도 |
|----------|------|------|
| `semantic_clean_dataset.py` | v7 | 코사인 유사도 0.95+ 중복 제거 |
| `augment_learning_dataset.py` | v5 | 패러프레이즈 + 역번역 증강 |
| `comprehensive_clean_v7.py` | v7 | 포괄적 클리닝 |
| `create_v8_final_dataset.py` | v8 | 패턴 필터링 (NDB 제거, 불일치 제거) |
| `improve_v9_dataset.py` | v9 | PDCA 2차 반복 정제 |
| `qa_relevance_checker.py` | — | Q-A 관련성 점검 |
| `verify_v7_quality.py` | v7 | 품질 검증 |
| `analyze_dataset_quality.py` | — | 데이터셋 품질 분석 |

### 6.4 데이터 저장 위치

| 경로 | 내용 |
|------|------|
| `uploads/training_text/` | CPT용 Plain Text (제품별 디렉토리) |
| `uploads/training_text/dpo_pairs.json` | DPO preference 쌍 |
| `uploads/summaries/multi_lora_v9_improved/` | SFT v9 데이터셋 (현재 운용) |
| `uploads/summaries/multi_lora_v4_cleaned/` ~ `v8_final/` | 이전 버전 데이터셋 |
| `uploads/feedback/` | Pattern E 피드백 JSONL (자기개선) |

---

## 7. LLM 하드웨어 및 Serving

### 7.1 현재 구성

| 항목 | 값 |
|------|-----|
| Base 모델 | Qwen 2.5 7B-Instruct |
| 어댑터 | 24 QLoRA adapters (22 제품 + 2 공통) |
| Serving | vLLM (port 12815), Multi-LoRA 동적 로딩 |
| GPU | NVIDIA A100-SXM4-40GB |
| 특수 토큰 | `<\|im_start\|>` (151644), `<\|im_end\|>` (151645), `<\|endoftext\|>` (151643) |

### 7.2 향후 배포 계획

| 항목 | 값 |
|------|-----|
| 모델 | Qwen 32B |
| GPU | A100 48GB × 4 |
| Context | 32K+ tokens |
| Batching | vLLM continuous batching → 병렬 LLM 호출 |

---

## 8. Web Doc RAG Fast Path

> **진입점**: `services/web_doc_search_service.py`

```
질문 → WebDocSearchService (keyword+IDF, <10ms)
    ├─ score < 0.9 → 일반 PDF RAG 진행
    └─ score >= 0.9 → Fast Path:
        httpx.get(page_url) → LLM generate → 응답
```

| 항목 | 값 |
|------|-----|
| 인덱스 | `uploads/web_doc_index/index.json` (643 pages, 14 components) |
| 크롤러 | `WebDocCrawlerService` → docs.tmaxsoft.com |
| 임계값 | `WEB_DOC_THRESHOLD = 0.9` |
| SSL | `verify=False` 필수 (docs.tmaxsoft.com 인증서 이슈) |
| CLI | `python -m scripts.crawl_web_docs --lang ja` |

### SSE 이벤트 순서

```
web_doc_match → web_doc_generating → llm_token(×N) → sources(domain=web_doc) → done(web_doc_url=...)
```

---

## 9. Long-term Memory

### 9.1 Product Context Memory

| 항목 | 값 |
|------|-----|
| 서비스 | `ProductContextMemory` |
| 기반 | LangGraph Store (`InMemoryStore` → 프로덕션: `PostgresStore`) |
| 용도 | 제품 라우팅 컨텍스트 세션 간 영속 |
| 우선순위 | `all_scores` > `memory` > `empty` (점수가 있으면 점수 우선) |

### 9.2 Deep Agent Memory

| 경로 | 용도 |
|------|------|
| `/memories/` | 일반 장기 메모리 |
| `/preferences/` | 사용자 선호도 |
| `/knowledge/` | 대화 축적 지식 |
| `/instructions/` | 피드백 기반 자기 개선 |

---

## 10. Common Gotchas

| 이슈 | 해결 |
|------|------|
| `ProductId` enum vs `str` 혼용 | Agentic RAG는 `str`, OpenFrame RAG는 `ProductId` — 혼용 금지 |
| Web Doc ID ≠ Router ID | `openframe_mvs` → `mvs_openframe_7.1` 변환 필요 (`_LEGACY_TO_WEB_DOC_PID`) |
| 일본어 토큰화 이상 | `教えてください` → `教` + `えてください` 분리됨 → 히라가나 불용어 추가 |
| InMemoryStore 휘발 | 프로세스 재시작 시 소멸 → 프로덕션은 `PostgresStore` 필요 |
| DPO OOM | `max_length` 2048→512, `max_prompt` 512→128 (O(n²) 메모리 16배 절감) |
| CPT 데이터 포맷 | Plain Text (Q-A 구조 아님) — ChatML 사용하면 안됨 |
| vLLM Multi-LoRA | 어댑터 이름이 디렉토리명과 일치해야 함 |

---

## 11. 파일 인덱스

### Agent System

| 파일 | 역할 |
|------|------|
| `app/api/agents/orchestrator.py` | Agent 라우팅 & 실행 |
| `app/api/agents/executor.py` | 개별 Agent 실행, file_context 처리 |
| `app/api/agents/adapters/deep_agent_adapter.py` | LangGraph Deep Agent |
| `app/api/agents/adapters/integration.py` | Deep Agent 등록/활성화 |
| `app/api/agents/auto_agent/orchestrator.py` | Auto Agent 오케스트레이터 |
| `app/api/agents/auto_agent/verifier_agent.py` | 응답 검증 |
| `app/api/agents/auto_agent/answer_composer.py` | 답변 합성 |
| `app/api/agents/opencode/hallucination_detector.py` | 환각 감지 |

### Agentic RAG

| 파일 | 역할 |
|------|------|
| `app/api/routers/agentic_rag.py` | API 엔드포인트 |
| `app/api/services/agentic_rag_service.py` | 6-Phase 오케스트레이터 |
| `app/api/services/product_router_service.py` | 제품 라우팅 |
| `app/api/services/manual_registry_service.py` | 19개 제품 동적 탐색 |
| `app/api/services/dynamic_product_agent_service.py` | 제품별 에이전트 생성 |
| `app/api/services/structured_knowledge_store.py` | PDF 파싱 + 검색 |
| `app/api/services/web_doc_search_service.py` | Web Doc Fast Path |
| `app/api/services/product_context_memory.py` | 장기 메모리 |
| `app/api/models/agentic_rag.py` | Pydantic 모델 |

### Agent Teams

| 파일 | 역할 |
|------|------|
| `app/api/services/agent_teams/team_orchestrator.py` | 메인 통합 레이어 |
| `app/api/services/agent_teams/parallel_retrieval.py` | Pattern A: 병렬 검색 |
| `app/api/services/agent_teams/competitive_hypothesis.py` | Pattern B: 경쟁 가설 |
| `app/api/services/agent_teams/domain_specialist.py` | Pattern C: 도메인 전문가 |
| `app/api/services/agent_teams/multi_product_collab.py` | Pattern D: 멀티 제품 |
| `app/api/services/agent_teams/self_improvement.py` | Pattern E: 자기 개선 |

### Training Pipeline

| 파일 | 역할 |
|------|------|
| `scripts/training/run_full_pipeline.py` | 전체 파이프라인 오케스트레이터 |
| `scripts/training/run_cpt_training.py` | Phase 1: CPT |
| `scripts/training/train_multi_lora_v4.py` | Phase 2: Multi-LoRA SFT |
| `scripts/training/run_dpo_training.py` | Phase 3: DPO |
| `scripts/training/generate_dpo_data.py` | DPO preference 쌍 생성 |
| `scripts/training/qlora_trainer.py` | Generic QLoRA SFT Trainer |
| `scripts/training/run_learning_llm_training.py` | Learning LLM 학습 |
| `scripts/training/merge_adapter.py` | LoRA adapter 병합 |
| `scripts/training/evaluate_perplexity.py` | Perplexity 평가 |
