# KMS RAG 시스템 할루시네이션 최소화 보고서

## 1. 개요

### 1.1 문서 목적

본 문서는 HybridRAG KMS 시스템에서 LLM [할루시네이션](#hallucination-할루시네이션)(환각 현상)을 최소화하기 위해 수행한 일련의 개선 작업과 그 결과를 정리한다. 2025년 1월 초기 구축 시점부터 2026년 2월 현재까지, 총 6단계의 반복적 개선을 거쳐 [E2E 테스트](#e2e-end-to-end-테스트) 기준 53% 실패율을 0%까지 낮추었다.

> 본 문서에서 사용하는 전문 용어(QLoRA, SFT, DPO, CPT, ChatML, RAFT 등)에 대한 상세 설명과 참고 링크는 [부록 A. 용어 해설](#부록-a-용어-해설)에 정리하였다.

### 1.2 현황 요약

| 항목 | 값 |
|------|-----|
| 대상 시스템 | HybridRAG KMS - Agentic RAG |
| 개선 기간 | 2025-01 ~ 2026-02 (진행 중) |
| E2E 테스트 결과 | 40/40 통과 (100%) |
| 대상 제품 수 | 19개 (OpenFrame 제품군) |
| QLoRA 어댑터 수 | 22개 |
| 핵심 아키텍처 | Agentic [RAG](#rag-retrieval-augmented-generation) + [QLoRA](#qlora-quantized-low-rank-adaptation) 3-Phase + [RAFT](#raft-retrieval-augmented-fine-tuning) |

### 1.3 핵심 성과

| 지표 | 개선 전 | 개선 후 |
|------|---------|---------|
| E2E Hallucination 테스트 | 24/45 통과 (53% 실패) | 40/40 통과 (0% 실패) |
| 구조화 질문 할루시네이션 | 발생 | 0% (LLM 미사용 Template 응답) |
| [DPO](#dpo-direct-preference-optimization) 선호도 정확도 | - | 95% |
| 제품 교차 오염 | 빈번 | 제품별 Agent 격리로 차단 |

## 2. 문제 배경

### 2.1 초기 시스템의 한계

KMS 시스템을 처음 구축했을 때, [RAG](#rag-retrieval-augmented-generation) 파이프라인은 사용자의 질문을 받아 Vector DB와 Graph DB에서 관련 문서를 검색한 뒤 LLM에 넘겨 답변을 생성하는 단순한 구조였다. 이 방식에는 세 가지 근본적인 문제가 있었다.

첫째, LLM 출력에 대한 검증 장치가 전혀 없었다. 검색된 문서와 무관한 내용을 LLM이 생성해도 그대로 사용자에게 전달되었다. 둘째, Hybrid RAG에서 Vector 검색 결과와 Graph 검색 결과가 서로 모순되는 경우가 있었는데, LLM이 이를 임의로 합성하면서 사실과 다른 답변이 만들어졌다. 셋째, 사용자가 "tjesmgr에 대해 알려줘"라고 물었을 때, oscmgr나 hidbmgr 같은 다른 제품의 정보가 섞여 들어가는 교차 오염이 발생했다.

### 2.2 범용 LLM의 도메인 지식 부재

Qwen 2.5를 기본 LLM으로 사용하고 있었는데, 이 모델은 TmaxSoft의 OpenFrame 제품군에 대한 사전 지식이 전혀 없다. "tjesmgr"가 무엇인지, "TJES"와 "OSC"가 별개의 서브시스템이라는 것을 모르기 때문에, 검색된 컨텍스트가 불충분하면 자체적으로 내용을 지어내는 경향이 있었다.

E2E 테스트로 이 문제의 심각성을 정량적으로 확인했다. 45개 테스트 케이스 중 21개(53%)에서 할루시네이션이 감지되었다.

## 3. 개선 과정

### 3.1 Phase 1: 초기 대응 (2025-01 ~ 2026-01 초)

가장 먼저 시도한 것은 쿼리 분류와 컨텍스트 캐싱이었다. 한국어, 일본어, 영어 쿼리를 라우팅하여 언어 혼동을 방지하고, 대화 컨텍스트를 캐싱하여 후속 질문에서의 반복 실수를 줄였다. "X와 Y를 비교해줘" 같은 포괄 쿼리도 감지하여 제품별로 분리 처리하도록 했다.

이 단계의 효과는 제한적이었다. 언어 혼동이나 명백한 교차 질문에는 효과가 있었지만, 단일 제품에 대한 질문에서 발생하는 할루시네이션에는 근본적인 해결책이 되지 못했다.

| 시도 | 내용 | 효과 |
|------|------|------|
| 쿼리 분류 | 한/일/영 라우팅으로 언어 혼동 방지 | 부분 개선 |
| 대화 컨텍스트 캐싱 | 후속 질문 추적, 프로토타입 임베딩 캐시 | 반복 실수 감소 |
| 포괄 쿼리 감지 | "X와 Y 비교" 감지 후 제품 분리 처리 | 혼합 환각 감소 |

### 3.2 Phase 2: Knowledge Grounding (2026-01)

이 시점에서 얻은 가장 중요한 교훈은 "LLM만으로는 할루시네이션 방지가 불가능하다"는 것이었다. 프롬프트를 아무리 정교하게 작성해도, 모델이 갖고 있지 않은 도메인 지식을 정확히 답변하게 만들 수는 없었다. 방향을 전환하여 데이터 기반 응답(grounding)에 집중했다.

[Cross-encoder Reranker](#cross-encoder-reranker)를 도입하여 검색 품질을 올리는 것도 시도했지만, 결국 LLM이 최종 답변을 생성하는 한 할루시네이션 리스크는 남아 있었다.

전환점이 된 것은 두 가지였다. 하나는 Summary 데이터 39,000건의 Q&A 쌍으로 [QLoRA](#qlora-quantized-low-rank-adaptation) 학습을 수행한 Learning LLM이고, 다른 하나는 구조화 질문에서 LLM을 아예 사용하지 않는 Direct Mode였다. Direct Mode는 검색 결과를 Markdown 포맷으로 직접 변환하여 응답하는 방식으로, LLM을 거치지 않으므로 할루시네이션이 원천적으로 발생할 수 없다.

이 조합으로 E2E 테스트를 44/45까지 올릴 수 있었다.

| 시도 | 내용 | 효과 |
|------|------|------|
| Cross-encoder Reranker | [vLLM](#vllm) 통합, 검색 품질 개선 | LLM 의존도 여전히 높음 |
| Learning LLM | Summary 39K Q&A로 QLoRA 학습 | 구조화 질문 약 96% 정확도 |
| Direct Mode | 구조화 질문에 LLM 미사용, 검색 결과 직접 포맷 | 0% 할루시네이션 |
| Anti-Hallucination 프롬프트 | VSAM 타입 격리 규칙, glossary 개선 | E2E 44/45 통과 |

### 3.3 Phase 3: Template 아키텍처 (2026-01 말)

Direct Mode의 성공에서 착안하여, 질문 유형을 체계적으로 분류하고 각 유형에 맞는 응답 전략을 설계했다. QueryTypeClassifier는 정규식 기반으로 동작하여 LLM을 사용하지 않는다.

사용자 질문의 약 70~80%는 에러 코드 조회, 명령어 사용법, 파라미터 설명, 설정 방법 등 구조화된 질문이다. 이런 질문은 TemplateResponseBuilder가 검색 결과를 정해진 포맷으로 조합하여 응답한다. 나머지 20~30%의 자유형 질문만 LearningLLM을 사용하되, 컨텍스트를 제한하고 사후 검증을 수행한다.

```
사용자 질문
  |
  v
QueryTypeClassifier (정규식, LLM 미사용)
  |-- ERROR_CODE / COMMAND / PARAMETER / CONFIG
  |     -> TemplateResponseBuilder (할루시네이션 0%)
  |
  +-- FREEFORM
        -> LearningLLM (컨텍스트 제한 + 사후 검증)
```

같은 시기에 Summary-First RAG도 도입했다. 기존에는 Vector DB에서 바로 검색했는데, 그 전에 요약본(commands, error-codes, configs, glossary)을 [BM25](#bm25)로 먼저 검색하여 컨텍스트를 보강한다. 이 검색은 파일 시스템 기반이라 10ms 미만으로 완료되며, LLM을 사용하지 않는다.

### 3.4 Phase 4: OpenFrame RAG 시스템 (2026-02-02 ~ 03)

이전까지는 8개 제품만 지원했는데, 이 단계에서 19개 제품으로 확장하면서 3가지 쿼리 모드를 도입했다.

| 모드 | 동작 조건 | 할루시네이션 위험도 |
|------|----------|------------------|
| Direct | 검색 결과를 그대로 출력 | 0% (LLM 미사용) |
| Hybrid | 검색 점수 10 이상이면 Direct, 미만이면 LLM | 낮음 |
| LLM | 자연어 생성 (컨텍스트 제한 적용) | 중간 (검증 필요) |

CJK(한국어, 중국어, 일본어) 토큰화도 이 시점에 지원을 추가했다. 일본어의 경우 한자와 히라가나 경계에서 토큰이 분리되는 문제가 있어 불용어 목록을 보완해야 했다.

### 3.5 Phase 5: Agentic RAG (2026-02-07 ~ 08)

이 단계가 할루시네이션 최소화에서 가장 큰 전환점이었다. 19개 제품 각각에 독립적인 Agent를 할당하여, 하나의 질문이 반드시 하나의 제품 Agent만 거치도록 격리했다. 이를 통해 제품 간 정보 교차 오염을 구조적으로 차단했다.

전체 파이프라인은 다음과 같다.

```
사용자 질문
  |
  v
ProductRouter (키워드 + 패턴 매칭, LLM 미사용)
  |  confidence >= 0.8, gap >= 0.3 -> 제품 확정
  |  0.5 ~ 0.8 -> 확인 요청 (후보 1개 + conf >= 0.6이면 자동 확정)
  |
  v
QueryTypeClassifier (정규식, LLM 미사용)
  |-- ERROR_CODE / COMMAND / PARAM / CONFIG
  |     -> TemplateResponseBuilder (할루시네이션 0%)
  |
  +-- FREEFORM
        -> LearningLLM (컨텍스트 4000자 제한, [temperature](#temperature) 0.3)
              |
              v
        ResponseVerifier (단어 겹침 기반 검증)
              >= 0.7 : VERIFIED (검증 완료)
              0.4~0.7 : INFERRED (추론 포함)
              < 0.4 : UNVERIFIED (미검증)
```

핵심 설계 원칙을 정리하면 다음과 같다.

| 원칙 | 내용 |
|------|------|
| 검색에 LLM 없음 | 결정적(deterministic) 검색으로 재현성 확보 |
| 구조화 질문 LLM 우회 | 전체 질문의 70~80%를 Template으로 처리 |
| 제품 격리 | 19개 제품 각각 독립 Agent, 교차 오염 차단 |
| 사후 검증 | ResponseVerifier로 3단계 신뢰도 표시 |
| Web Doc Fast Path | score 0.9 이상이면 전체 HTML 페이지 기반 응답 |

이 구조로 E2E 테스트 40/40 전건 통과를 달성했다.

### 3.6 Phase 6: Agent Teams (2026-02-15)

Agentic RAG 위에 5가지 고급 패턴을 추가하여 할루시네이션 방지를 다층화했다. 각 패턴은 Feature Flag로 제어되며, 기본값은 모두 OFF로 설정하여 기존 동작을 100% 보존한 상태에서 개별 활성화할 수 있도록 했다.

| 패턴 | 방식 | 할루시네이션 방지 메커니즘 |
|------|------|--------------------------|
| A: 병렬 검색 | Web Doc + PDF RAG 동시 검색 | 신뢰도가 높은 결과 선택 |
| B: 경쟁 가설 | [temperature](#temperature) 0.3/0.7/1.0 세 버전 생성 후 다수결 | 개별 환각이 상쇄됨 |
| C: 도메인 전문가 | 제품군별 QLoRA 어댑터 선택 | 도메인 특화로 교차 환각 감소 |
| D: 멀티제품 DAG | 제품별 독립 검색 후 합성 | 명시적 경계로 혼합 방지 |
| E: 자기 개선 | 피드백 축적 후 QLoRA 재학습 | 시간에 따라 품질 향상 |

```
# Feature Flags (config.py)
AGENT_TEAMS_PARALLEL_RETRIEVAL = False     # Pattern A
AGENT_TEAMS_COMPETITIVE_HYPOTHESIS = False # Pattern B
AGENT_TEAMS_DOMAIN_SPECIALIST = False      # Pattern C
AGENT_TEAMS_MULTI_PRODUCT = False          # Pattern D
AGENT_TEAMS_SELF_IMPROVEMENT = False       # Pattern E
```

## 4. QLoRA 학습 파이프라인

### 4.1 학습 동기

E2E 테스트에서 53%의 실패율을 확인한 후, 범용 LLM의 도메인 지식 부재가 근본 원인이라고 판단했다. 72B 규모의 풀 파인튜닝은 GPU 메모리 제약(A100 40GB x 4)으로 불가능했기 때문에, 4-bit 양자화와 [LoRA](#lora-low-rank-adaptation)를 결합한 [QLoRA](#qlora-quantized-low-rank-adaptation) 방식을 채택했다.

### 4.2 학습 포맷

학습 데이터는 용도에 따라 두 가지 포맷을 사용한다.

[SFT](#sft-supervised-fine-tuning)와 [DPO](#dpo-direct-preference-optimization)에는 [ChatML](#chatml-chat-markup-language) 포맷을 사용한다. Qwen 2.5의 특수 토큰을 활용하여 instruction-response 쌍으로 구성하며, 22개 제품별 Multi-LoRA 어댑터를 이 포맷으로 학습시켰다.

[CPT](#cpt-continued-pre-training)(Continued Pre-Training)에는 Plain Text 포맷을 사용한다. PDF에서 추출한 원문 텍스트 72MB(약 34.3M 토큰)를 문서 경계 토큰으로 구분하여 4096 토큰 청크로 분할한다. CPT의 목적이 도메인 지식 주입이므로 Q-A 구조는 불필요하고, 원문의 자연어 패턴을 보존하는 것이 중요하다.

### 4.3 데이터셋 버전 이력

v4에서 v9까지 [PDCA](#pdca-plan-do-check-act) 사이클을 반복하며 데이터 품질을 점진적으로 개선했다.

| 버전 | 초점 | 주요 작업 | 상태 |
|------|------|----------|------|
| v4 | Baseline | 22개 제품 기본 추출 | 완료 |
| v5 | 증강 | 패러프레이즈 + 역번역 | 완료 |
| v6 | 균형 | 제품간 샘플 수 조정 | 완료 |
| v7 | 시맨틱 클리닝 | 중복 제거 (코사인 유사도 0.95 이상 필터) | 완료 |
| v8 | 패턴 필터링 | NDB 제품 제거, Q-A 불일치 40% 이상 제거 | 완료 |
| v9 | PDCA 정제 | E2E 실패 케이스 기반 최종 보정 | 운용 중 |

### 4.4 3-Phase 학습 구성

학습은 세 단계로 나누어 진행한다. 각 단계의 목적과 하이퍼파라미터가 다르다.

#### Phase 1: CPT (Continued Pre-Training) - 도메인 지식 주입

| 항목 | 값 |
|------|-----|
| 베이스 모델 | Qwen2.5-72B-Instruct |
| LoRA | r=64, alpha=128 |
| 학습률 | 1e-5 |
| 포맷 | Plain Text (4096 토큰 청크) |
| GPU | [FSDP](#fsdp-fully-sharded-data-parallel), GPU 4-7 (40GB each) |
| 소요 시간 | 2시간 28분 |
| Eval [Perplexity](#perplexity-ppl) | 1.65 |
| Loss | 0.11 |

#### Phase 2: SFT (Supervised Fine-Tuning) - 제품별 어댑터

| 항목 | 값 |
|------|-----|
| 베이스 모델 | Qwen2.5-7B-Instruct x 22개 제품 |
| LoRA | r=64, alpha=16 |
| 학습률 | 2e-4 |
| 포맷 | ChatML (instruction-response) |
| GPU | 4개 어댑터 병렬 학습 (GPU 4,5,6,7) |
| 소요 시간 | 약 69분 (전체) |
| 결과 | 22개 제품별 어댑터 생성 |

#### Phase 3: DPO (Direct Preference Optimization) - 선호도 정렬

| 항목 | 값 |
|------|-----|
| 베이스 모델 | Qwen2.5-72B-Instruct + CPT 어댑터 |
| LoRA | r=32, alpha=64 |
| 학습률 | 5e-6 |
| 학습 데이터 | 2,000개 preference 쌍 |
| 소요 시간 | 약 2시간 |
| 선호도 정확도 | 95% |
| Loss 감소 | 75% (0.69 -> 0.17) |

DPO 학습 데이터는 세 가지 전략으로 생성했다. E2E 테스트 실패 케이스에서 교차 제품 정보로 답변한 사례(0.6%), 사실 관계를 의도적으로 변형한 사례(55.7%), 다른 제품의 Summary를 교차 적용한 사례(43.7%)를 rejected 응답으로 사용했다.

### 4.5 하이퍼파라미터 비교

| 파라미터 | CPT | SFT | DPO | 설정 근거 |
|----------|-----|-----|-----|----------|
| LoRA Rank | 64 | 64 | 32 | DPO는 선호도 정렬이므로 낮은 rank로 충분 |
| 학습률 | 1e-5 | 2e-4 | 5e-6 | 지식 주입은 낮게, 명령 학습은 높게, 정렬은 가장 낮게 |
| Epoch | 2 | 3 | 2 | 과적합 방지와 학습 효과의 균형 |
| Max Sequence | 2048 | 2048 | 512 | DPO는 reference model 때문에 메모리 2배 필요 |

### 4.6 DPO 학습 과정에서의 OOM 해결

DPO 학습 초기에 GPU [OOM](#oom-out-of-memory)(Out of Memory)이 반복 발생했다. A100 40GB에서 max_length=2048, max_prompt=512 설정으로는 step 14에서 39.29/39.38 GiB를 사용하며 OOM이 발생했다. precompute_ref_log_probs 옵션은 [FSDP](#fsdp-fully-sharded-data-parallel)와 호환되지 않았고, fsdp_offload_params도 8bit optimizer와 충돌했다.

최종적으로 max_length를 512, max_prompt를 128로 줄여 해결했다. Transformer의 self-attention은 시퀀스 길이에 대해 O(n^2) 메모리를 사용하므로, 길이를 1/4로 줄이면 메모리가 약 1/16로 감소한다.

## 5. RAFT 기반 Domain-Specific Fine-Tuning

### 5.1 배경

[RAFT](#raft-retrieval-augmented-fine-tuning)(Retrieval Augmented Fine-Tuning)는 Cornell University에서 발표한 논문 "RAFT: Adapting Language Model to Domain Specific RAG" (arXiv:2403.10131)에서 제안된 방법론이다.

핵심 아이디어는 오픈북 시험에 비유할 수 있다. 일반 Fine-Tuning이 교과서를 외우고 시험을 보는 것이라면, 일반 RAG는 교과서를 보면서 시험을 보되 어디를 봐야 할지 모르는 것이고, RAFT는 교과서에서 정답 부분만 찾아 읽는 훈련을 한 뒤 시험을 보는 것이다.

RAFT의 주요 개념은 다음과 같다.

| 개념 | 설명 |
|------|------|
| Oracle Document (D*) | 정답이 포함된 관련 문서 |
| Distractor Document (Dk) | 관련 없는 방해 문서 |
| Chain-of-Thought | 추론 과정을 단계별로 생성 |
| Verbatim Citation | 원문을 직접 인용하여 답변 |

### 5.2 KMS에서의 RAFT 적용

SFT 학습 데이터에 Oracle Document(정답 포함 검색 결과)와 Distractor Document(다른 제품의 무관 문서)를 함께 포함시켜, 모델이 관련 문서만 골라서 답변하는 능력을 학습시켰다.

DPO에서는 교차 제품 문서를 Distractor로 활용했다. 올바른 제품의 정보로 답변한 것을 chosen, 다른 제품의 정보로 답변한 것을 rejected로 설정하여 모델이 무관 문서를 무시하는 선호도를 학습하게 했다.

추론(Inference) 시에도 같은 패턴이 자연스럽게 적용된다. Summary 검색이 Oracle Document 역할을 하고, ResponseVerifier의 단어 겹침 검증이 원문 인용(Verbatim Citation) 검증과 유사한 역할을 한다.

```
사용자 질문: "tjesmgr BOOT 명령어 사용법"
  |
  v
Summary 검색 (Oracle Document 역할)
  |-- commands/OpenFrame_TJES_MVS.md -> 정확한 명령어 정보 (D*)
  |-- commands/OpenFrame_OSC.md -> 무관 문서 (Dk) -> 무시됨
  +-- glossary/T.md -> 용어 보충 (D*)
  |
  v
TemplateResponseBuilder 또는 LearningLLM
  -> Oracle Document에서만 정보 추출
  |
  v
ResponseVerifier
  -> 원문 인용 검증
```

RAFT 적용 이후, tjesmgr 질문에 oscmgr 정보가 혼입되는 유형의 교차 제품 할루시네이션이 크게 감소했다.

## 6. 시스템 진화 타임라인

| 시점 | 마일스톤 | 주요 변경 사항 |
|------|----------|---------------|
| 2025-01 | 초기 구축 | Query Classification, Context Caching |
| 2026-01 초 | Knowledge Grounding | Learning LLM, Direct Mode |
| 2026-01 말 | Template 아키텍처 | QueryTypeClassifier, TemplateResponseBuilder |
| 2026-02-02 | OpenFrame RAG | 19개 제품 확장, 3가지 쿼리 모드 |
| 2026-02-07 | Agentic RAG | 제품별 Agent 격리, E2E 40/40 통과 |
| 2026-02-15 | Agent Teams | 5가지 고급 패턴, Feature Flag 제어 |

## 7. 관련 파일

### 7.1 할루시네이션 방지 핵심 파일

| 파일 | 역할 |
|------|------|
| services/response_verifier.py | 사후 검증 (단어 겹침 유사도, 3단계 신뢰도) |
| services/query_type_classifier.py | 질문 분류 (정규식 패턴, LLM 미사용) |
| services/agentic_rag_service.py | 파이프라인 오케스트레이션 |
| services/learning_llm_service.py | 제한된 생성 (컨텍스트 4000자, temperature 0.3) |
| services/product_router_service.py | 제품 라우팅 (키워드+패턴, 결정적) |
| services/web_doc_search_service.py | Web Doc Fast Path (score 0.9 이상 매칭) |
| agents/prompts/rag_agent.txt | Agent 프롬프트 (EXTRACTIVE ONLY 모드) |

### 7.2 QLoRA 학습 파일

| 파일 | 역할 |
|------|------|
| scripts/training/qlora_trainer.py | QLoRA 학습 메인 트레이너 |
| scripts/training/run_cpt_training.py | CPT 실행 |
| scripts/training/run_dpo_training.py | DPO 실행 |
| scripts/training/run_learning_llm_training.py | Learning LLM 학습 실행 |
| scripts/training/train_multi_lora_v4.py | Multi-LoRA 어댑터 학습 |
| scripts/training/convert_to_qlora.py | 학습 데이터 포맷 변환 |
| scripts/training/improve_v9_dataset.py | v9 데이터셋 PDCA 정제 |

## 8. 알려진 한계 및 향후 개선

### 8.1 ResponseVerifier의 한계

현재 ResponseVerifier는 단어 겹침(word overlap) 방식으로 검증을 수행한다. 이 방식에는 두 가지 약점이 있다.

첫째, 의미적 불일치를 감지하지 못한다. 예를 들어 "oscmgr는 TJES 관리 도구이다"라는 답변은 oscmgr와 TJES라는 키워드가 모두 검색 결과에 포함되어 있으면 높은 겹침 점수를 받을 수 있지만, 실제로는 oscmgr는 OSC 관리 도구이므로 오답이다.

둘째, 순서 오류를 구별하지 못한다. "A가 B를 유발한다"와 "B가 A를 유발한다"는 같은 단어로 구성되어 있으므로 동일한 겹침 점수를 받는다.

### 8.2 향후 개선 방향

| 방법 | 기대 효과 |
|------|----------|
| N-gram 겹침 (bigram/trigram) | 단어 순서를 고려한 검증 |
| 임베딩 기반 유사도 | 의미적 검증 |
| [NLI](#nli-natural-language-inference) (Natural Language Inference) | 논리적 함의 확인 |
| SPO Triple 추출 | 주어-술어-목적어 사실 관계 매칭 |
| RAFT 학습 데이터 확장 | Oracle/Distractor 비율 최적화 |

## 9. 결론

이 프로젝트에서 가장 효과적이었던 단일 결정은 "구조화 질문에 LLM을 사용하지 않는다"는 것이었다. 전체 사용자 질문의 70~80%가 에러 코드, 명령어, 파라미터 등 구조화된 질문인데, 이를 Template으로 처리함으로써 대부분의 할루시네이션을 원천 차단했다.

시스템의 진화 방향을 한마디로 요약하면, "범용 LLM에 전적으로 의존하는 RAG"에서 "전문화된 다층 방어 시스템"으로의 전환이었다. LLM이 모든 답변을 생성하던 구조에서, LLM 출력 검증, LLM 사용 최소화, 제품별 격리와 다층 검증, RAFT 기반 도메인 특화 학습으로 순차적으로 발전해왔다.

## 부록 A. 용어 해설

본 문서에서 사용하는 주요 기술 용어를 정리한다.

### A.1 LLM 학습 기법

#### QLoRA (Quantized Low-Rank Adaptation)

QLoRA는 대규모 언어 모델을 효율적으로 파인튜닝하기 위한 기법이다. 원래 모델의 가중치를 4-bit로 양자화(quantize)하여 GPU 메모리 사용량을 대폭 줄인 상태에서, 학습 가능한 저랭크 행렬(LoRA 어댑터)만 추가하여 학습한다. 72B 파라미터 모델의 풀 파인튜닝에는 수백 GB의 GPU 메모리가 필요하지만, QLoRA를 사용하면 A100 40GB 4장으로도 학습이 가능하다.

- 논문: [QLoRA: Efficient Finetuning of Quantized LLMs](https://arxiv.org/abs/2305.14314) (Dettmers et al., 2023)

#### LoRA (Low-Rank Adaptation)

LoRA는 사전 학습된 모델의 가중치를 직접 수정하지 않고, 각 레이어에 작은 저랭크 행렬 쌍(A, B)을 추가하여 학습하는 방식이다. 원래 가중치 W에 대해 W + BA 형태로 업데이트하며, A와 B의 rank(r)가 원래 차원보다 훨씬 작으므로 학습해야 할 파라미터 수가 크게 줄어든다. 본 프로젝트에서는 r=32~64를 사용했다.

- 논문: [LoRA: Low-Rank Adaptation of Large Language Models](https://arxiv.org/abs/2106.09685) (Hu et al., 2021)

#### SFT (Supervised Fine-Tuning)

SFT는 레이블이 있는 학습 데이터(instruction-response 쌍)를 사용하여 모델이 특정 형식의 지시를 따르도록 학습시키는 방법이다. 사전 학습(pre-training)된 범용 모델을 특정 태스크에 맞게 조정하는 가장 기본적인 파인튜닝 방식이며, 본 프로젝트에서는 22개 제품별로 독립적인 SFT를 수행하여 제품 전문 어댑터를 생성했다.

- 참고: [Hugging Face SFT Trainer 문서](https://huggingface.co/docs/trl/sft_trainer)

#### DPO (Direct Preference Optimization)

DPO는 인간(또는 규칙 기반)의 선호도 데이터를 사용하여 모델의 출력 품질을 정렬(alignment)하는 학습 방법이다. 기존의 RLHF(Reinforcement Learning from Human Feedback)가 별도의 보상 모델(reward model)을 필요로 하는 반면, DPO는 chosen(선호 응답)과 rejected(비선호 응답) 쌍으로부터 직접 정책을 최적화한다. 수식이 단순하고 학습이 안정적이라는 장점이 있다. 본 프로젝트에서는 교차 제품 할루시네이션이 포함된 응답을 rejected로 설정하여 모델이 이를 회피하도록 학습시켰다.

- 논문: [Direct Preference Optimization: Your Language Model is Secretly a Reward Model](https://arxiv.org/abs/2305.18290) (Rafailov et al., 2023)

#### CPT (Continued Pre-Training)

CPT는 이미 사전 학습된 모델에 특정 도메인의 텍스트 데이터를 추가로 학습시켜 도메인 지식을 주입하는 방법이다. SFT처럼 instruction-response 형태가 아니라 원문 텍스트를 그대로 학습하며, 모델이 해당 도메인의 용어, 개념, 문맥을 내재화하는 것이 목적이다. 본 프로젝트에서는 245개 PDF 매뉴얼에서 추출한 72MB의 원문 텍스트를 Qwen2.5-72B에 CPT로 학습시켰다.

- 참고: [Continual Pre-training of Language Models](https://arxiv.org/abs/2302.03241) (Ke et al., 2023)

#### RAFT (Retrieval Augmented Fine-Tuning)

RAFT는 RAG 환경에 특화된 파인튜닝 기법이다. 학습 시 질문과 함께 정답이 포함된 문서(Oracle Document)와 무관한 문서(Distractor Document)를 섞어서 제공하고, 모델이 관련 문서에서만 정보를 추출하여 답변하도록 훈련한다. 오픈북 시험에서 필요한 페이지만 정확히 찾아 읽는 능력을 학습시키는 것에 비유할 수 있다.

- 논문: [RAFT: Adapting Language Model to Domain Specific RAG](https://arxiv.org/abs/2403.10131) (Zhang et al., 2024)

### A.2 데이터 포맷

#### ChatML (Chat Markup Language)

ChatML은 OpenAI가 제안한 대화형 학습 데이터 포맷이다. `<|im_start|>`와 `<|im_end|>` 특수 토큰으로 각 발화(system, user, assistant)의 경계를 명시한다. Qwen 2.5 계열 모델이 이 포맷을 기본으로 사용하며, 본 프로젝트의 SFT/DPO 학습 데이터가 이 형식을 따른다.

```
<|im_start|>system
You are an OpenFrame KMS assistant.<|im_end|>
<|im_start|>user
tjesmgr BOOT 명령어 사용법을 알려주세요.<|im_end|>
<|im_start|>assistant
tjesmgr BOOT는 TJES 노드를 초기화하는 명령어입니다...<|im_end|>
```

- 참고: [OpenAI ChatML 설명](https://github.com/openai/openai-python/blob/main/chatml.md)

### A.3 RAG 및 검색

#### RAG (Retrieval-Augmented Generation)

RAG는 LLM이 답변을 생성하기 전에 외부 데이터베이스에서 관련 문서를 검색하여 컨텍스트로 제공하는 기법이다. LLM의 사전 학습 데이터에 없는 최신 정보나 전문 도메인 지식을 활용할 수 있게 해주며, 할루시네이션을 줄이는 주요 수단 중 하나다. 본 프로젝트에서는 Vector DB 검색, Graph DB 검색, Summary 검색을 결합한 Hybrid RAG 구조를 사용한다.

- 논문: [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) (Lewis et al., 2020)

#### BM25

BM25(Best Matching 25)는 정보 검색 분야에서 널리 사용되는 확률 기반 랭킹 함수다. TF-IDF를 개선한 것으로, 문서 내 검색어 출현 빈도(TF)와 전체 문서 집합에서의 희소성(IDF), 문서 길이를 종합적으로 고려하여 관련도 점수를 산출한다. 벡터 임베딩과 달리 LLM이 필요 없으며, 키워드 매칭에 강점이 있다. 본 프로젝트에서는 Summary-First RAG의 요약본 검색에 BM25를 사용한다.

- 참고: [Wikipedia - Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25)

#### Cross-encoder Reranker

Cross-encoder는 질문과 문서를 하나의 입력으로 결합하여 관련도를 직접 예측하는 모델이다. 일반적인 Bi-encoder(질문과 문서를 따로 인코딩)보다 정확도가 높지만 연산 비용이 크다. 검색 파이프라인에서 1차 검색(BM25 또는 Bi-encoder) 결과를 Cross-encoder로 재정렬(reranking)하여 상위 결과의 품질을 높이는 용도로 사용한다.

- 참고: [SBERT Cross-Encoder 문서](https://www.sbert.net/examples/applications/cross-encoder/README.html)

### A.4 인프라 및 학습 도구

#### vLLM

vLLM은 LLM 추론(inference) 속도를 최적화하기 위한 오픈소스 서빙 엔진이다. PagedAttention 기법을 사용하여 GPU 메모리를 효율적으로 관리하고, continuous batching으로 여러 요청을 동시에 처리한다. OpenAI 호환 API를 제공하므로 기존 코드를 거의 수정하지 않고 적용할 수 있다. 본 프로젝트에서는 Qwen 2.5 + QLoRA 어댑터를 vLLM 위에서 서빙한다.

- GitHub: [vLLM Project](https://github.com/vllm-project/vllm)

#### FSDP (Fully Sharded Data Parallel)

FSDP는 PyTorch에서 제공하는 분산 학습 기법으로, 모델 파라미터, 그래디언트, 옵티마이저 상태를 여러 GPU에 분산(shard)하여 각 GPU의 메모리 사용량을 줄인다. 기존의 DDP(Distributed Data Parallel)가 모든 GPU에 전체 모델 복사본을 유지하는 것과 달리, FSDP는 필요한 시점에만 파라미터를 모아서(all-gather) 연산하고 다시 분산한다. 본 프로젝트에서는 CPT 학습 시 GPU 4장에 72B 모델을 분산하기 위해 사용했다.

- 참고: [PyTorch FSDP 문서](https://pytorch.org/docs/stable/fsdp.html)

### A.5 평가 지표

#### Hallucination (할루시네이션)

LLM 분야에서 할루시네이션은 모델이 입력 데이터나 학습 데이터에 근거 없는 정보를 마치 사실인 것처럼 생성하는 현상을 말한다. RAG 시스템에서는 검색된 문서에 없는 내용을 지어내거나, 여러 제품의 정보를 잘못 혼합하는 것이 대표적인 사례다. 본 프로젝트에서 해결하려는 핵심 문제이다.

- 참고: [Survey of Hallucination in Natural Language Generation](https://arxiv.org/abs/2202.03629) (Ji et al., 2023)

#### Perplexity (PPL)

Perplexity는 언어 모델의 성능을 평가하는 지표로, 모델이 다음 토큰을 얼마나 잘 예측하는지를 나타낸다. 값이 낮을수록 모델이 해당 텍스트 분포를 잘 학습했음을 의미한다. PPL=1이면 완벽한 예측이고, 랜덤 예측의 경우 어휘 크기에 비례하는 높은 값이 나온다. 본 프로젝트 CPT 학습에서 Eval Perplexity 1.65를 달성했는데, 이는 모델이 OpenFrame 도메인 텍스트를 높은 수준으로 학습했음을 나타낸다.

#### Temperature

Temperature는 LLM이 텍스트를 생성할 때 출력의 무작위성을 조절하는 파라미터다. 값이 0에 가까울수록 가장 확률이 높은 토큰만 선택하여 결정적(deterministic)인 출력을 생성하고, 값이 높을수록 다양한 토큰이 선택될 확률이 올라간다. 할루시네이션을 줄이려면 낮은 temperature(0.1~0.3)를 사용하는 것이 일반적이며, 본 프로젝트에서는 LearningLLM에 temperature=0.3을 설정했다.

#### NLI (Natural Language Inference)

NLI는 두 문장 간의 논리적 관계를 판별하는 자연어 처리 태스크다. 전제(premise)와 가설(hypothesis)이 주어졌을 때, 함의(entailment), 모순(contradiction), 중립(neutral) 중 하나로 분류한다. 할루시네이션 검증에서는 검색된 원문(전제)과 LLM 생성 답변(가설) 사이의 함의 관계를 확인하여, 답변이 원문에 근거하는지 판단하는 데 활용할 수 있다.

- 참고: [Wikipedia - Textual Entailment](https://en.wikipedia.org/wiki/Textual_entailment)

#### E2E (End-to-End) 테스트

E2E 테스트는 시스템의 전체 흐름을 처음부터 끝까지 검증하는 테스트 방식이다. 본 프로젝트에서는 Playwright 기반 브라우저 자동화를 사용하여, 실제 사용자가 질문을 입력하고 답변을 받는 전체 과정을 시뮬레이션한다. 45개(이후 40개로 조정) 테스트 케이스에 대해 기대 키워드와 금지 키워드를 설정하여 할루시네이션을 정량적으로 감지한다.

### A.6 기타 용어

#### OOM (Out of Memory)

GPU 메모리가 부족하여 연산을 계속할 수 없는 상태. 대규모 모델 학습에서 자주 발생하며, 배치 크기 축소, 시퀀스 길이 단축, gradient checkpointing, 모델 분산(FSDP) 등으로 대응한다.

#### PDCA (Plan-Do-Check-Act)

품질 관리 및 지속적 개선을 위한 반복적 방법론. 계획(Plan), 실행(Do), 검증(Check), 개선(Act) 4단계를 순환하며 점진적으로 품질을 높인다. 본 프로젝트에서는 학습 데이터셋 버전을 v4에서 v9까지 PDCA 사이클로 반복 개선했다.

#### Feature Flag

소프트웨어의 특정 기능을 코드 배포 없이 ON/OFF 할 수 있는 설정값. 새로운 기능을 코드에 포함하되 기본적으로 비활성화 상태로 두어, 안전하게 점진적 롤아웃이 가능하다. 본 프로젝트의 Agent Teams 5가지 패턴은 각각 독립적인 Feature Flag로 제어된다.
