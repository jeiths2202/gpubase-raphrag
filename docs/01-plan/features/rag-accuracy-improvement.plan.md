# PDCA Plan: RAG Accuracy Improvement

> **Feature**: rag-accuracy-improvement
> **Created**: 2026-01-31
> **Status**: Plan Phase
> **Level**: Dynamic

---

## 1. Background & Problem Statement

### 1.1 Current Issues (E2E Test Results)

| 문제 유형 | 빈도 | 심각도 | 예시 |
|----------|------|--------|------|
| **Hallucination** | 3% | 🔴 Critical | osc.conf 질문 → tjes.conf 응답 |
| **Semantic Mismatch** | ~10% | 🟠 High | "構造" 질문 → "命令어" 결과 |
| **No Results (DB 부재)** | ~13% | 🟡 Medium | iebgener, ABEND S0C7 |
| **검색-응답 불일치** | ~5% | 🟠 High | 검색 결과 있지만 "정보 없음" |

### 1.2 Root Causes

1. **검색 정확도 문제**: Vector 유사도만으로 의미적 일치 판단
2. **Relevance Verification 부재**: 검색 결과가 질문에 실제로 답하는지 검증 없음
3. **Strict Matching 부재**: 특정 키워드(config 파일명 등) 정확 매칭 미흡
4. **Fallback 메시지 불명확**: 부분 일치 시 UX 혼란

---

## 2. Industry Standard Solutions (2024-2025 Research)

### 2.1 RAGAS Evaluation Framework

> Reference: [RAGAS Documentation](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)

| Metric | 설명 | 적용 방안 |
|--------|------|----------|
| **Faithfulness** | 응답이 검색 결과에 근거하는지 | Post-generation 검증 |
| **Answer Relevancy** | 응답이 질문에 적절한지 | Cosine similarity 검증 |
| **Context Precision** | 검색된 컨텍스트의 정밀도 | Retrieval 품질 측정 |
| **Context Recall** | 필요한 정보가 모두 검색되었는지 | Coverage 측정 |

### 2.2 Self-Reflective RAG (Agentic RAG)

> Reference: [LangChain Self-Reflective RAG](https://blog.langchain.com/agentic-rag-with-langgraph/)

```
Query → Retriever → [ISREL] Relevance Check
                         ↓
                    Relevant? ─No→ Query Rewrite → Retry
                         ↓Yes
                    Generator → [ISSUP] Support Check
                         ↓
                    Supported? ─No→ Retry Generation
                         ↓Yes
                    Final Answer
```

**핵심 토큰**:
- `ISREL`: 문서가 질문에 관련 있는지 (relevant/irrelevant)
- `ISSUP`: 생성된 답변이 문서에 근거하는지 (fully/partially/no support)

### 2.3 Corrective RAG (CRAG)

> Reference: [Corrective RAG with LangChain](https://www.chitika.com/corrective-rag-langchain-langgraph/)

- 부적절한 문서 자동 필터링
- 쿼리 실시간 개선
- 응답의 컨텍스트 정확성 보장

### 2.4 Guardrails & Hallucination Detection

> Reference: [AWS Hallucination Detection](https://aws.amazon.com/blogs/machine-learning/detect-hallucinations-for-rag-based-systems/)

| 방법 | 정확도 | 적용 |
|------|--------|------|
| LLM Prompt-based Detection | 75%+ | 복잡한 할루시네이션 |
| Token Similarity Detection | High | 명백한 불일치 |
| Semantic Similarity Check | Medium | 의미적 관련성 |
| HHEM-2.1-Open (T5 classifier) | High | 오픈소스 대안 |

### 2.5 Multi-Stage Evidence Aggregation

> Reference: [MEGA-RAG](https://pmc.ncbi.nlm.nih.gov/articles/PMC12540348/)

```
Query → Dense Retrieval → Cross-Encoder Re-ranking → Weighted Entailment Scoring → Final Results
```

---

## 3. Proposed Solution Architecture

### 3.1 Overall Flow (개선 후)

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Accuracy Pipeline v2                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Query                                                      │
│      ↓                                                          │
│  ┌──────────────────┐                                           │
│  │ Query Analyzer   │ ← Intent Detection, Keyword Extraction    │
│  └────────┬─────────┘                                           │
│           ↓                                                      │
│  ┌──────────────────┐                                           │
│  │ Hybrid Retrieval │ ← Vector + Keyword + Metadata Filter      │
│  └────────┬─────────┘                                           │
│           ↓                                                      │
│  ┌──────────────────┐                                           │
│  │ Relevance Grader │ ← [NEW] ISREL 기반 문서 관련성 평가        │
│  └────────┬─────────┘                                           │
│           ↓                                                      │
│      Relevant? ──No──→ Query Rewrite → Retry (max 2)            │
│           ↓Yes                                                   │
│  ┌──────────────────┐                                           │
│  │ Answer Generator │ ← Context-grounded Generation             │
│  └────────┬─────────┘                                           │
│           ↓                                                      │
│  ┌──────────────────┐                                           │
│  │ Faithfulness     │ ← [NEW] ISSUP 기반 근거 검증              │
│  │ Checker          │                                           │
│  └────────┬─────────┘                                           │
│           ↓                                                      │
│      Supported? ──No──→ Partial Match Response                  │
│           ↓Yes                                                   │
│  ┌──────────────────┐                                           │
│  │ Final Response   │ ← With source citations                   │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 신규 컴포넌트

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| **RelevanceGrader** | `services/relevance_grader_service.py` | 검색 결과 관련성 평가 |
| **FaithfulnessChecker** | `services/faithfulness_checker_service.py` | 응답 근거 검증 |
| **QueryRewriter** | `services/query_rewriter_service.py` | 쿼리 개선 |
| **PartialMatchHandler** | `services/partial_match_handler.py` | 부분 일치 UX 처리 |

### 3.3 프롬프트 개선

| 항목 | 현재 | 개선 |
|------|------|------|
| Config 파일 매칭 | 유사 파일 대체 허용 | Strict exact match 강제 |
| 구조 vs 명령어 | 구분 없음 | Intent-aware 응답 |
| No Results 메시지 | 단순 "정보 없음" | Partial match 안내 + 대안 제시 |

---

## 4. Implementation Phases

### Phase 1: Relevance Grader (Week 1)
- [ ] `RelevanceGraderService` 구현
- [ ] ISREL 스타일 관련성 평가 로직
- [ ] unified_search 결과 후처리 통합

### Phase 2: Faithfulness Checker (Week 2)
- [ ] `FaithfulnessCheckerService` 구현
- [ ] ISSUP 스타일 근거 검증
- [ ] Answer Builder 통합

### Phase 3: Query Enhancement (Week 3)
- [ ] `QueryRewriterService` 구현
- [ ] 실패 시 쿼리 재작성 로직
- [ ] 최대 2회 재시도 제한

### Phase 4: UX Improvement (Week 4)
- [ ] `PartialMatchHandler` 구현
- [ ] 프롬프트 강화 (Strict matching rules)
- [ ] 부분 일치 응답 템플릿

### Phase 5: Evaluation & Monitoring
- [ ] RAGAS 메트릭 통합
- [ ] E2E 테스트 확장
- [ ] 모니터링 대시보드

---

## 5. Success Criteria

| Metric | Current | Target | 측정 방법 |
|--------|---------|--------|----------|
| Hallucination Rate | 3% | <0.5% | E2E Test |
| Semantic Mismatch | ~10% | <3% | E2E Test |
| Answer Relevancy (RAGAS) | N/A | >0.85 | RAGAS Eval |
| Faithfulness (RAGAS) | N/A | >0.90 | RAGAS Eval |
| E2E Pass Rate | 97% | >99% | E2E Test |

---

## 6. Technical Specifications

### 6.1 Relevance Grader Prompt

```markdown
You are a relevance grader. Evaluate if the retrieved document answers the user's question.

Question: {question}
Document: {document}

Evaluate:
1. Does the document contain information about the EXACT topic asked?
2. Does the document address the SPECIFIC aspect (structure/usage/error) asked?

Output: "relevant" or "irrelevant" with brief reason.
```

### 6.2 Faithfulness Checker Prompt

```markdown
You are a faithfulness checker. Verify if the generated answer is supported by the context.

Context: {retrieved_context}
Answer: {generated_answer}

For each claim in the answer:
- Is it DIRECTLY stated in the context? → "supported"
- Is it INFERRED from the context? → "partially_supported"
- Is it NOT in the context? → "not_supported"

Output overall: "fully_supported", "partially_supported", or "not_supported"
```

### 6.3 Strict Matching Rule (Config Files)

```python
EXACT_MATCH_PATTERNS = [
    r'\w+\.conf$',     # Config files: osc.conf, tjes.conf
    r'ABEND S\d+',     # ABEND codes: ABEND S0C7
    r'-\d{4,5}$',      # Error codes: -5212
]

def requires_exact_match(query: str) -> bool:
    return any(re.search(p, query) for p in EXACT_MATCH_PATTERNS)
```

---

## 7. Dependencies & References

### 7.1 External Libraries
- `ragas` - Evaluation metrics
- `sentence-transformers` - Semantic similarity (already installed)

### 7.2 Research References

- [RAGAS Metrics Documentation](https://docs.ragas.io/en/stable/concepts/metrics/)
- [Self-Reflective RAG with LangGraph](https://blog.langchain.com/agentic-rag-with-langgraph/)
- [AWS Hallucination Detection](https://aws.amazon.com/blogs/machine-learning/detect-hallucinations-for-rag-based-systems/)
- [Corrective RAG Implementation](https://www.chitika.com/corrective-rag-langchain-langgraph/)
- [MEGA-RAG Multi-Evidence Aggregation](https://pmc.ncbi.nlm.nih.gov/articles/PMC12540348/)
- [Confident AI RAG Evaluation](https://www.confident-ai.com/blog/rag-evaluation-metrics-answer-relevancy-faithfulness-and-more)

### 7.3 Related Files

| 파일 | 수정 내용 |
|------|----------|
| `app/api/agents/prompts/rag_agent.txt` | Strict matching rules 추가 |
| `app/api/agents/tools/unified_search.py` | RelevanceGrader 통합 |
| `app/api/services/answer_builder_service.py` | FaithfulnessChecker 통합 |
| `e2e/e2e_sentence_test.js` | RAGAS 메트릭 테스트 추가 |

---

## 8. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM 호출 증가로 Latency 증가 | 🟠 Medium | 캐싱, 병렬 처리 |
| Grader/Checker 과도한 필터링 | 🟠 Medium | Threshold 조정, A/B 테스트 |
| 신규 컴포넌트 복잡도 | 🟡 Low | 단계적 롤아웃 |

---

## 9. Timeline

```
Week 1: Phase 1 (Relevance Grader)
Week 2: Phase 2 (Faithfulness Checker)
Week 3: Phase 3 (Query Enhancement)
Week 4: Phase 4 (UX) + Phase 5 (Evaluation)
```

---

**Next Step**: `/pdca design rag-accuracy-improvement`

---

> **Created by**: Claude Code + bkit PDCA
> **Last Updated**: 2026-01-31
