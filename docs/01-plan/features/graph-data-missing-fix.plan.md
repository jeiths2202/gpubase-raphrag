# Plan: graph_data 이벤트 누락 버그 수정

## 문제 설명
Agentic RAG에서 "tjesmgr에 대해서 설명해주세요." 쿼리 실행 시 `knowledgeGraph.relatedGraph`가 표시되지 않는 문제.

## 근본 원인
`graph_data` SSE 이벤트가 **LLM freeform 응답 경로에서만** yield됨.
`stream_chat()` 메서드 내 5개 조기 반환(early return) 경로에서 `graph_data`를 누락:

| 응답 경로 | 위치 | graph_data |
|---|---|---|
| Template response (구조화) | line 1166 return | **누락** |
| vLLM direct search | line 1038 return | **누락** |
| Web Doc fast path | line 1107 return | **누락** |
| Special/Code/Planner Agent | line 1000-1014 return | **누락** |
| LLM freeform | line 1232 | 정상 |

"tjesmgr에 대해서 설명해주세요."는 COMMAND 유형으로 분류되어 template response 또는 vLLM direct search 경로를 타므로 graph_data가 생성되지 않음.

## 수정 방안

### 1. 헬퍼 메서드 추출
`_get_graph_data_event()` 비동기 메서드를 생성하여 graph_data 이벤트 생성 로직을 캡슐화.

### 2. 4개 경로에 graph_data 추가
- Template response path (done 이전)
- vLLM direct search path (done 이전)
- Web Doc fast path (done 이전)
- 기존 LLM freeform path → 헬퍼 메서드 호출로 교체

### 수정 파일
- `app/api/services/agentic_rag_service.py` (1개 파일)

### 영향 범위
- graph_data는 optional (실패 시 무시) → 기존 동작에 영향 없음
- 프론트엔드 변경 불필요 (이미 graph_data 이벤트 처리 구현됨)

## 구현 우선순위
1. `_get_graph_data_event()` 헬퍼 메서드 추가
2. Template response 경로에 graph_data 삽입 (가장 빈번)
3. vLLM direct search 경로에 삽입
4. Web Doc fast path에 삽입
5. 기존 LLM freeform 경로를 헬퍼 호출로 리팩토링
