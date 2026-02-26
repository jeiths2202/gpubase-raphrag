# Feature Plan: Token Overflow Prevention (Proactive Context Management)

## Problem Statement

현재 `local_coder.py`(core.py)는 Qwen3 32B (8192 context) 환경에서 토큰 오버플로우 에러가 발생한다.

**실제 에러:**
```
Error code: 400 - 'max_tokens' or 'max_completion_tokens' is too large: 4096.
This model's maximum context length is 8192 tokens and your request has 4888 input tokens
(4096 > 8192 - 4888)
```

**근본 원인:** 현재 구현은 **반응적(reactive)** 방식 - 에러 발생 후 retry/compress 처리.
토큰 추정(`chars/2.5`)이 부정확하여 사전 방지가 실패하고 vLLM 400 에러에 도달한다.

## Current State Analysis

### 기존 4-Layer Defense (core.py)
| Layer | 위치 | 방식 | 문제점 |
|-------|------|------|--------|
| L1: `calculate_max_tokens()` | 전송 전 | 추정 기반 max_tokens 조정 | chars/2.5 추정 부정확 |
| L2: `compress_history()` | L1에서 호출 | LLM으로 요약 생성 | 요약 자체가 토큰 소모 |
| L3: `_ensure_context_fits()` | L2 후 호출 | 메시지 truncation | 정보 손실 큼 |
| L4: `_create_stream()` | 에러 발생 시 | vLLM 에러 파싱 → retry | 에러가 이미 발생한 후 |

### 핵심 문제
1. **토큰 추정 부정확**: `chars/2.5`는 영어 기준. 한국어/JSON/코드 혼합 시 2-3배 차이 발생
2. **Tool 정의 토큰 과소평가**: 13개 tools JSON → ~1500-2000 토큰 (실제), 추정은 더 낮음
3. **요약 실패 시 정보 손실**: compress_history가 8K context 내에서 요약 API 호출 → 자체 실패 가능
4. **에러 기반 retry는 UX 나쁨**: 사용자에게 에러 메시지 노출 후 재시도

## Proposed Solution: Proactive Token Budget System

### 아키텍처: 3-Phase Token Budget

```
┌─────────────────────────────────────────────────────┐
│ Phase 1: Budget Calculation (매 요청 전)              │
│   input_tokens = system + tools + messages           │
│   output_budget = context_limit - input_tokens - buf │
│   if output_budget < MIN_OUTPUT → Phase 2로          │
└─────────────────────────────┬───────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────┐
│ Phase 2: Progressive Summarization                   │
│   Step 1: 오래된 메시지 → 로컬 요약 (LLM 미사용)     │
│   Step 2: Tool 결과 truncation (긴 결과 줄이기)      │
│   Step 3: 재계산 → 여전히 부족 시 Step 4             │
│   Step 4: LLM 기반 요약 (별도 짧은 context 사용)     │
└─────────────────────────────┬───────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────┐
│ Phase 3: Validated Send                              │
│   max_tokens = min(requested, output_budget)         │
│   if max_tokens < MIN → 사용자에게 /clear 권고       │
│   else → API 전송 (에러 없이 성공)                    │
└─────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Token Estimation 개선

**현재:**
```python
def estimate_tokens(text):
    return int(len(text) / 2.5) + 1
```

**개선:** vLLM 첫 응답에서 실제 usage를 받아 보정 계수 학습
```python
# vLLM response에서 prompt_tokens를 받아 보정
# estimated vs actual ratio → 이후 추정에 적용
# 초기값은 보수적(chars/2.0)으로 설정하여 과소추정 방지
```

### 2. Progressive Summarization (LLM 미사용 단계 추가)

**현재:** 바로 LLM 요약 호출 → 자체 토큰 소모
**개선:** 3단계 로컬 처리 후 LLM 요약

| Step | 방식 | 토큰 절약 | LLM 사용 |
|------|------|----------|---------|
| 1 | Tool 결과 → 첫 3줄만 보존 | ~60% | No |
| 2 | 오래된 메시지 → role + 첫 문장만 | ~40% | No |
| 3 | System prompt → 핵심만 (OpenFrame 모드) | ~30% | No |
| 4 | 남은 내용 → LLM 요약 (300 token 제한) | ~50% | Yes |

### 3. Tool 정의 경량화

13개 tools의 JSON schema가 ~1500 토큰 차지.
- OpenFrame 전용 모드: 기본 tools 최소화 (read_file, bash만)
- Tool description 압축 (긴 설명 제거)
- 동적 tool 로딩: 필요한 tools만 포함

### 4. 에러 기반 보정 루프 개선

```
┌─ 전송 시도 ─┐
│  성공 → 완료  │
│  400 에러 →  │
│    실제 input_tokens 파싱           │
│    correction_factor 업데이트       │
│    Phase 2 재실행                   │
│    재시도 (최대 2회)                │
└──────────────┘
```

## Files to Modify

| File | Changes |
|------|---------|
| `openframe_code/core.py` | Token estimation, summarization, budget system |

### Specific Sections in core.py:
- **Section 1.5** (line 130-158): `estimate_tokens`, `estimate_messages_tokens` 개선
- **Section 7** (line 1037+): `LocalCoder` class
  - `calculate_max_tokens()` (line 1096): Budget 시스템으로 교체
  - `compress_history()` (line 1120): Progressive summarization으로 교체
  - `_ensure_context_fits()` (line 1191): 로컬 요약 단계 추가
  - `_create_stream()` (line 1285): 보정 계수 학습 추가
  - `stream_response()` (line 1345): usage 정보 수집 추가

## Implementation Order

1. `estimate_tokens()` 보수적 변경 (chars/2.0) + tool 토큰 고정값
2. `progressive_compress()` 구현 (로컬 3단계 + LLM 1단계)
3. `calculate_max_tokens()` → proactive budget 시스템으로 교체
4. `_create_stream()` 보정 계수 학습 추가
5. Tool 정의 경량화 (description 압축)

## Success Criteria

- 8192 context에서 대화 5턴 이상 에러 없이 유지
- vLLM 400 에러 발생률: 현재 ~30% → 목표 <5%
- 요약 후 핵심 컨텍스트 보존율 >80%
- 사용자에게 에러 메시지 대신 자동 요약 알림만 노출

## Risk & Constraints

- **8K context는 매우 작음**: 13개 tools (~1500 tokens) + system prompt (~500 tokens) = 2000 tokens 고정 소비
  → 실질 사용 가능: ~6200 tokens (입력+출력)
- **LLM 요약의 재귀적 토큰 소비**: 요약을 위한 API 호출도 토큰 제한에 걸릴 수 있음
  → 해결: 로컬 요약 우선, LLM은 마지막 수단
- **Tool 경량화 시 LLM 성능 저하 가능**: description이 짧으면 tool 사용 정확도 하락
  → 해결: 핵심 키워드는 유지, 예시만 제거
