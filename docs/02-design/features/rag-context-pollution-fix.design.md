# RAG Context Pollution Fix - Design Document

> **Feature**: rag-context-pollution-fix
> **Version**: v2.0
> **Created**: 2026-02-03
> **Updated**: 2026-02-20
> **Author**: Claude Opus 4.5 → Claude Opus 4.6
> **Status**: 📐 Design Phase (Updated)

---

## 1. Overview

### 1.1 문제 요약

| 문제 | 증상 | 유형 | 발견일 |
|------|------|------|--------|
| **A** | `osctdlrm` 질문에 `oscsiggen` 설명까지 응답 | Chunk Pollution | 2026-02-03 |
| **B** | `tjesinit` 질문에 이전 `tacf` 대화 내용이 출력 | History Pollution | 2026-02-20 |

### 1.2 근본 원인 분석

**문제 A (Chunk Pollution):**
LLM이 검색된 모든 컨텍스트를 응답에 포함하는 문제.

```
검색 결과:
├── Chunk 1: osctdlrm 설명 (관련 ✅)
├── Chunk 2: oscsiggen 설명 (무관 ❌) ← 같은 문서의 인접 청크
└── Chunk 3: osctdlrm syntax (관련 ✅)
→ LLM이 oscsiggen까지 응답에 포함
```

**문제 B (History Pollution) - 3단계 원인 체인:**

```
[Stage 1] AgenticRAGPage.tsx:346
  messages.slice(-10) → history에 이전 tacf 대화 포함

[Stage 2] agentic_rag_service.py:1777
  _build_llm_context() → history_section + "\n\n" + search_section
  ← history가 검색 결과 앞에 배치됨

[Stage 3] vllm_adapter.py:545
  _extract_core_content() → lines[:20] (20줄 절단)
  ← history(tacf)는 보존, search_results(tjesinit)는 잘려나감
  ← LLM은 tacf 정보만 보고 응답 생성
```

### 1.3 기존 프롬프트 분석

`rag_agent.txt`에 이미 존재하는 관련 규칙:

| 규칙 | 내용 | 효과 |
|------|------|------|
| SINGLE-TERM FOCUS | VSAM 타입별 분리 응답 | ESDS/KSDS에만 적용 |
| COMMAND NAME STRICT MATCHING | 명령어 정확 매칭 | tjesmgr만 언급 |
| ERROR CODE STRICT MATCHING | 에러코드 정확 매칭 | 작동 중 |

**문제점**: 명령어에 대한 SINGLE-TERM 규칙이 없음!

---

## 2. Solution Design

### 2.1 Phase 1: LLM 프롬프트 강화 (즉시 적용)

**목표**: 명령어 단독 질문에 대해 다른 명령어 포함 금지

#### 2.1.1 추가할 프롬프트 섹션

```markdown
### 🚫🚫🚫 COMMAND SINGLE-FOCUS RULE 🚫🚫🚫

**CRITICAL: When user asks about a SPECIFIC command, you MUST focus on ONLY that command.**

**HARD RULE:**
| User Query Contains | YOU MUST ONLY MENTION | NEVER MENTION |
|---------------------|----------------------|---------------|
| osctdlrm | osctdlrm | oscsiggen, oscboot, oscdown, etc. |
| tjesmgr | tjesmgr | tacfmgr, hidbmgr, oscmgr, etc. |
| tacfmgr | tacfmgr | tjesmgr, oscmgr, ndbmgr, etc. |

**Example - osctdlrm Query:**
- User: "osctdlrmについて説明してください"
- ❌ FORBIDDEN: Mentioning "oscsiggen", "oscboot", any other osc* command
- ❌ FORBIDDEN: Adding "また、関連コマンドとして..." sections
- ✅ REQUIRED: Focus 100% on osctdlrm features ONLY

**WHY THIS MATTERS:**
- Even if search results contain oscsiggen information, you MUST IGNORE IT
- The user asked specifically about osctdlrm - that is the ONLY topic
- Mentioning oscsiggen when asked about osctdlrm is a HALLUCINATION

**GENERAL COMMAND RULE:**
- If user asks about "osctdlrm" → Answer ONLY about osctdlrm, IGNORE all other commands
- If user asks about "tjesmgr" → Answer ONLY about tjesmgr, IGNORE all other commands
- If user asks about "OSC commands" or "OSCコマンド一覧" → Then you may mention multiple commands
- Apply this single-focus rule to ALL command names
```

#### 2.1.2 수정 위치

**파일**: `app/api/agents/prompts/rag_agent.txt`
**위치**: `### 🚫🚫🚫 ABSOLUTE RULE: SINGLE-TERM FOCUS` 섹션 바로 아래

### 2.2 Phase 2: Post-Retrieval 필터링 (코드 레벨)

프롬프트만으로 해결되지 않는 경우를 대비한 코드 레벨 필터링.

#### 2.2.1 컴포넌트 설계

```
┌─────────────────────────────────────────────────────────┐
│                  ChunkFilterService                      │
├─────────────────────────────────────────────────────────┤
│ + filter_by_query_entity(query, chunks) → chunks        │
│ + _extract_command_entity(query) → Optional[str]        │
│ + _chunk_contains_entity(chunk, entity) → bool          │
│ + _is_command_query(query) → bool                       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    UnifiedSearchTool                     │
│                                                         │
│  _search() 메서드 내에서:                                │
│  1. Neo4j Vector Search                                 │
│  2. ChunkFilterService.filter_by_query_entity()  ← NEW  │
│  3. RRF Score Fusion                                    │
│  4. Return filtered results                             │
└─────────────────────────────────────────────────────────┘
```

#### 2.2.2 ChunkFilterService 상세 설계

**파일**: `app/api/services/chunk_filter_service.py`

```python
"""검색 결과 청크 필터링 서비스

Context Pollution 방지를 위해 질문과 관련 없는 청크를 필터링합니다.
"""

import re
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ChunkFilterService:
    """검색 결과 청크 필터링"""

    # OpenFrame 명령어 패턴 (osc*, tjes*, tacf*, hidb*, ndb* 등)
    COMMAND_PATTERNS = [
        r'\b(osc[a-z]+)\b',       # osctdlrm, oscsiggen, oscboot, etc.
        r'\b(tjes[a-z]*)\b',      # tjesmgr, tjes
        r'\b(tacf[a-z]*)\b',      # tacfmgr, tacf
        r'\b(hidb[a-z]*)\b',      # hidbmgr, hidb
        r'\b(ndb[a-z]*)\b',       # ndbmgr, ndb
        r'\b([a-z]+mgr)\b',       # *mgr 패턴
        r'\b(tmboot|tmdown|ofboot|ofdown)\b',
    ]

    def __init__(self):
        self._command_pattern = re.compile(
            '|'.join(self.COMMAND_PATTERNS),
            re.IGNORECASE
        )

    def filter_by_query_entity(
        self,
        query: str,
        chunks: List[Dict],
        min_chunks: int = 2
    ) -> List[Dict]:
        """질문의 주요 Entity 기반 청크 필터링

        Args:
            query: 사용자 질문
            chunks: 검색된 청크 목록
            min_chunks: 최소 반환 청크 수 (폴백)

        Returns:
            필터링된 청크 목록
        """
        # 1. 질문에서 명령어 Entity 추출
        query_command = self._extract_command_entity(query)

        if not query_command:
            logger.debug("[ChunkFilter] No command entity in query, skipping filter")
            return chunks

        logger.info(f"[ChunkFilter] Query command: {query_command}")

        # 2. 질문 명령어가 포함된 청크만 필터링
        filtered = []
        for chunk in chunks:
            content = chunk.get('content', '')
            if self._chunk_contains_entity(content, query_command):
                filtered.append(chunk)
            else:
                # 다른 명령어가 있는지 확인
                other_commands = self._extract_all_commands(content)
                other_commands.discard(query_command.lower())
                if other_commands:
                    logger.debug(
                        f"[ChunkFilter] Filtering out chunk with other commands: {other_commands}"
                    )

        # 3. 폴백: 필터링 후 너무 적으면 원본 유지
        if len(filtered) < min_chunks:
            logger.warning(
                f"[ChunkFilter] Only {len(filtered)} chunks after filter, "
                f"keeping top {min_chunks} original"
            )
            return chunks[:min_chunks]

        logger.info(f"[ChunkFilter] Filtered {len(chunks)} → {len(filtered)} chunks")
        return filtered

    def _extract_command_entity(self, query: str) -> Optional[str]:
        """질문에서 명령어 Entity 추출

        Args:
            query: 사용자 질문

        Returns:
            추출된 명령어 또는 None
        """
        matches = self._command_pattern.findall(query)
        if matches:
            # 첫 번째로 매칭된 명령어 반환
            # findall은 그룹이 있으면 튜플로 반환할 수 있음
            match = matches[0]
            if isinstance(match, tuple):
                # 비어있지 않은 첫 번째 그룹
                return next((m for m in match if m), None)
            return match
        return None

    def _extract_all_commands(self, text: str) -> set:
        """텍스트에서 모든 명령어 추출

        Args:
            text: 텍스트

        Returns:
            추출된 명령어 집합
        """
        matches = self._command_pattern.findall(text)
        commands = set()
        for match in matches:
            if isinstance(match, tuple):
                for m in match:
                    if m:
                        commands.add(m.lower())
            else:
                commands.add(match.lower())
        return commands

    def _chunk_contains_entity(self, content: str, entity: str) -> bool:
        """청크에 Entity가 포함되어 있는지 확인

        Args:
            content: 청크 내용
            entity: 확인할 Entity

        Returns:
            포함 여부
        """
        # 단어 경계를 고려한 매칭
        pattern = rf'\b{re.escape(entity)}\b'
        return bool(re.search(pattern, content, re.IGNORECASE))


# 싱글톤 인스턴스
_chunk_filter_service: Optional[ChunkFilterService] = None


def get_chunk_filter_service() -> ChunkFilterService:
    """ChunkFilterService 싱글톤 반환"""
    global _chunk_filter_service
    if _chunk_filter_service is None:
        _chunk_filter_service = ChunkFilterService()
    return _chunk_filter_service
```

#### 2.2.3 UnifiedSearchTool 통합

**파일**: `app/api/agents/tools/unified_search.py`
**수정 위치**: `_search()` 메서드 내, 결과 반환 전

```python
# 기존 코드 (결과 반환 전)
# ...

# NEW: Context Pollution 필터링
from app.api.services.chunk_filter_service import get_chunk_filter_service

chunk_filter = get_chunk_filter_service()
filtered_results = chunk_filter.filter_by_query_entity(query, results)

return ToolResult(
    success=True,
    data=filtered_results,
    # ...
)
```

### 2.3 Phase 3: History Pollution 수정 (2026-02-20 추가)

**목표**: 이전 대화 이력이 현재 검색 결과를 밀어내는 문제 해결

#### 2.3.1 수정 1: 컨텍스트 배치 순서 변경 (CRITICAL)

**파일**: `app/api/services/agentic_rag_service.py`
**위치**: `_build_llm_context()` (line 1727-1778)

**현재 코드** (line 1776-1778):
```python
if history_section and search_section:
    return history_section + "\n\n" + search_section
return search_section or history_section
```

**수정 코드**:
```python
if history_section and search_section:
    # 검색 결과를 앞에 배치 → _extract_core_content() 20줄 절단 시 검색 결과 보존
    return search_section + "\n\n---\n[会話履歴]\n" + history_section
return search_section or history_section
```

**효과**: `_extract_core_content()`가 20줄로 절단할 때, 검색 결과가 앞에 있어 보존됨.

#### 2.3.2 수정 2: `_extract_core_content()` 절단 개선

**파일**: `app/api/adapters/learning_llm/vllm_adapter.py`
**위치**: `_extract_core_content()` (line 525-545)

**현재 코드** (line 545):
```python
return '\n'.join(lines[:20])  # 최대 20줄 무차별 절단
```

**수정 코드**:
```python
# 구분자(---)를 인식하여 검색 결과 우선 보존
separator_idx = None
for i, line in enumerate(lines):
    if line.strip() == '---':
        separator_idx = i
        break

if separator_idx is not None:
    # 검색 결과: 최대 15줄, 히스토리: 최대 5줄
    search_lines = lines[:separator_idx][:15]
    history_lines = lines[separator_idx + 1:][:5]
    return '\n'.join(search_lines + ['---'] + history_lines)

return '\n'.join(lines[:20])  # 구분자 없으면 기존 동작
```

**효과**: 검색 결과(15줄)와 히스토리(5줄)가 별도 할당되어 상호 침범 방지.

#### 2.3.3 데이터 흐름 (수정 후)

```
User: "tacfについて説明してください"  → 정상 응답
User: "tjesinitについて説明してください"

_build_llm_context():
  search_section = "tjesinit は TJES の初期化コマンドです..."  (검색 결과)
  history_section = "ユーザー: tacfについて...\nアシスタント: tacf は..."  (이력)
  return search_section + "\n\n---\n[会話履歴]\n" + history_section
  ↓
_extract_core_content():
  lines[:separator] → tjesinit 검색 결과 (최대 15줄) ← 보존!
  lines[separator+1:] → tacf 대화 이력 (최대 5줄) ← 제한
  ↓
LLM: tjesinit 검색 결과에 기반한 정확한 응답 ✅
```

---

## 3. File Structure

### 3.1 수정 파일

| 파일 | 변경 내용 | 우선순위 |
|------|----------|---------|
| `app/api/agents/prompts/rag_agent.txt` | COMMAND SINGLE-FOCUS 규칙 추가 | Phase 1 (Chunk) |
| `app/api/services/chunk_filter_service.py` | 새 서비스 생성 | Phase 2 (Chunk) |
| `app/api/agents/tools/unified_search.py` | 필터링 통합 | Phase 2 (Chunk) |
| `app/api/services/agentic_rag_service.py` | `_build_llm_context()` 배치 순서 변경 | **Phase 3 (History)** |
| `app/api/adapters/learning_llm/vllm_adapter.py` | `_extract_core_content()` 구조적 절단 | **Phase 3 (History)** |

### 3.2 새 파일

```
app/api/services/
└── chunk_filter_service.py     # NEW (~150 lines)
```

---

## 4. Data Flow

### 4.1 Phase 1 (프롬프트 수정만)

```
User Query: "osctdlrmについて説明してください"
    │
    ▼
unified_search(query)
    │
    ▼
검색 결과: [osctdlrm 청크, oscsiggen 청크, osctdlrm syntax 청크]
    │
    ▼
LLM (with COMMAND SINGLE-FOCUS rule)
    │
    ▼
응답: "osctdlrmは..." (oscsiggen 미포함)
```

### 4.2 Phase 2 (필터링 추가)

```
User Query: "osctdlrmについて説明してください"
    │
    ▼
unified_search(query)
    │
    ▼
Raw 검색 결과: [osctdlrm 청크, oscsiggen 청크, osctdlrm syntax 청크]
    │
    ▼
ChunkFilterService.filter_by_query_entity()
    │
    ▼
Filtered 결과: [osctdlrm 청크, osctdlrm syntax 청크]  ← oscsiggen 제거
    │
    ▼
LLM (with COMMAND SINGLE-FOCUS rule)
    │
    ▼
응답: "osctdlrmは..." (oscsiggen 완전 배제)
```

---

## 5. Implementation Order

### 5.1 Phase 1: 프롬프트 수정 (Chunk Pollution)

```
1. rag_agent.txt 수정
   - COMMAND SINGLE-FOCUS 섹션 추가
   - 위치: SINGLE-TERM FOCUS 섹션 바로 아래
2. 테스트: osctdlrm 질문 재테스트
```

### 5.2 Phase 2: 코드 필터링 (Chunk Pollution - Phase 1 효과 부족시)

```
1. chunk_filter_service.py 생성
2. unified_search.py 수정
3. 테스트
```

### 5.3 Phase 3: History Pollution 수정 (즉시 적용 - 우선순위 HIGH)

```
1. agentic_rag_service.py 수정 (line 1776-1778)
   - _build_llm_context() 반환값: search + "---" + history 순서로 변경
   - 변경 범위: 3줄

2. vllm_adapter.py 수정 (line 525-545)
   - _extract_core_content() 구분자 인식 절단 로직 추가
   - search 15줄 + history 5줄 별도 할당
   - 변경 범위: ~15줄

3. 테스트
   - tacf → tjesinit 연속 대화 테스트
   - tjesinit 응답에 tacf 내용 미포함 확인
   - 기존 RAG 쿼리 정상 동작 확인 (regression)
```

---

## 6. Interface Definitions

### 6.1 ChunkFilterService API

```python
class ChunkFilterService:
    """검색 결과 청크 필터링 서비스"""

    def filter_by_query_entity(
        self,
        query: str,
        chunks: List[Dict],
        min_chunks: int = 2
    ) -> List[Dict]:
        """
        질문의 주요 Entity 기반 청크 필터링

        Args:
            query: 사용자 질문
            chunks: 검색된 청크 목록
            min_chunks: 최소 반환 청크 수 (폴백)

        Returns:
            필터링된 청크 목록

        Example:
            >>> service = ChunkFilterService()
            >>> chunks = [
            ...     {'content': 'osctdlrm is a tool...'},
            ...     {'content': 'oscsiggen generates...'},
            ... ]
            >>> filtered = service.filter_by_query_entity(
            ...     'osctdlrmについて', chunks
            ... )
            >>> len(filtered)
            1
        """
```

### 6.2 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ENABLE_CHUNK_FILTER` | `true` | 청크 필터링 활성화 |
| `CHUNK_FILTER_MIN_RESULTS` | `2` | 최소 결과 수 (폴백) |

---

## 7. Success Criteria

### 7.1 E2E 테스트 케이스

| 테스트 | 입력 | 기대 출력 | 금지 출력 | 대상 문제 |
|--------|------|----------|----------|----------|
| osctdlrm 단독 | "osctdlrmについて説明してください" | osctdlrm 설명 | oscsiggen | A |
| tjesmgr 단독 | "tjesmgrの機能は?" | tjesmgr 기능 | tacfmgr, oscmgr | A |
| tacfmgr 단독 | "tacfmgr BOOT 명령어" | tacfmgr BOOT | tjesmgr BOOT | A |
| 복수 명령어 | "OSCコマンド一覧" | 여러 명령어 | - | A |
| **tacf→tjesinit 연속** | tacf 질문 후 "tjesinitについて説明してください" | tjesinit 설명 | tacf 내용 | **B** |
| **tacf→oscmgr 연속** | tacf 질문 후 "oscmgrについて" | oscmgr 설명 | tacf 내용 | **B** |
| **긴 대화 후 새 질문** | 5턴 대화 후 새로운 명령어 질문 | 새 명령어 설명 | 이전 대화 내용 | **B** |

### 7.2 성능 기준

| 지표 | 목표 |
|------|------|
| 응답 지연 추가 | < 100ms |
| Hallucination 감소 | > 50% |
| 기존 테스트 통과 | 100% |
| **검색 결과 보존율** | **절단 후 80% 이상** |

---

## 8. Risk & Mitigation

| 위험 | 영향 | 대응 |
|------|------|------|
| 과도한 필터링 | 필요한 정보 손실 | min_chunks 폴백, 로깅 |
| 프롬프트 무시 | Phase 1 효과 없음 | Phase 2 코드 필터링 |
| 명령어 패턴 누락 | 특정 명령어 필터링 안됨 | 패턴 확장, E2E 테스트 |
| **history 절단으로 맥락 손실** | 후속 질문 이해도 저하 | 최소 5줄 보장 |
| **배치 순서 변경 regression** | 기존 동작 깨짐 | backward compatible 구분자, 기존 테스트 재실행 |
| **구분자(---) 충돌** | 검색 결과 내 --- 존재 시 오인식 | `[会話履歴]` 마커와 --- 조합으로 구분 |

---

## 9. Testing Plan

### 9.1 Unit Tests

```python
# tests/unit/test_chunk_filter_service.py

def test_extract_command_entity():
    """명령어 Entity 추출 테스트"""
    service = ChunkFilterService()
    assert service._extract_command_entity("osctdlrmについて") == "osctdlrm"
    assert service._extract_command_entity("tjesmgr BOOT") == "tjesmgr"
    assert service._extract_command_entity("일반 질문") is None


def test_filter_removes_other_commands():
    """다른 명령어 청크 필터링 테스트"""
    service = ChunkFilterService()
    chunks = [
        {'content': 'osctdlrm is a management tool...'},
        {'content': 'oscsiggen generates sign files...'},
        {'content': 'osctdlrm syntax: osctdlrm [options]...'},
    ]
    filtered = service.filter_by_query_entity("osctdlrmについて", chunks)
    assert len(filtered) == 2
    assert all('oscsiggen' not in c['content'] for c in filtered)
```

### 9.2 E2E Tests

```javascript
// e2e/e2e_context_pollution_test.js

const testCases = [
    {
        query: 'osctdlrmについて説明してください',
        expected: ['osctdlrm'],
        notExpected: ['oscsiggen', 'oscboot', 'oscdown']
    },
    {
        query: 'tjesmgr BOOT 명령어',
        expected: ['tjesmgr', 'BOOT'],
        notExpected: ['tacfmgr', 'oscmgr']
    }
];
```

---

## 10. Next Steps

1. **Phase 3 구현 (우선)**: History Pollution 수정
   - `agentic_rag_service.py:1776-1778` → 배치 순서 변경 (3줄 수정)
   - `vllm_adapter.py:525-545` → 구분자 인식 절단 (~15줄 추가)
2. **Phase 3 테스트**: tacf → tjesinit 연속 대화 검증
3. **Phase 1 구현**: `rag_agent.txt` 프롬프트 수정 (Chunk Pollution)
4. **Phase 2 구현** (필요시): `ChunkFilterService` 생성 및 통합
5. **Gap Analysis**: `/pdca analyze rag-context-pollution-fix`

---

**다음 단계**: `/pdca do rag-context-pollution-fix`
