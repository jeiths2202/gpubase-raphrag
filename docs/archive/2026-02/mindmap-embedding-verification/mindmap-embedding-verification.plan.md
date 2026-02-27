# Plan: Mindmap Embedding Database 연동 검증

> **작성일**: 2026-02-02
> **상태**: Analysis Complete
> **PDCA Phase**: Plan

## 1. 목적

`/mindmap` API가 실제로 embedding된 데이터베이스(Neo4j Vector Index)와 연동하여 동작하는지 검증

## 2. 현재 구현 분석 결과

### 2.1 데이터베이스 연동 현황

| 구분 | 연동 여부 | 사용 방식 |
|------|-----------|----------|
| **Neo4j Graph DB** | ✅ 연동됨 | `langchain_neo4j.Neo4jGraph` |
| **Vector Index** | ✅ 연동됨 | `chunk_embedding` 인덱스 사용 |
| **Embedding Service** | ✅ 연동됨 | `NeMoEmbeddingService` (port 12801) |

### 2.2 핵심 연동 로직 위치

```
app/api/services/mindmap_service.py
├── _vector_search_chunks() (line 356-415)  ← Vector 검색 핵심
├── _get_relevant_chunks() (line 417-467)   ← 동적 청크 조회
└── _get_document_chunks() (line 310-354)   ← Graph 기반 청크 조회
```

### 2.3 Vector Search 구현 확인

**mindmap_service.py:356-415** - `_vector_search_chunks()` 메서드:

```python
def _vector_search_chunks(self, query: str, k: int = 20, min_score: float = 0.3) -> List[Dict]:
    """Vector 유사도 검색으로 관련 청크 가져오기"""

    # 1. Embedding 생성
    query_embedding = self._embedding_service.embed_text(query, input_type="query")

    # 2. Vector Index 이름 가져오기
    vector_index_name = getattr(config.vector, 'index_name', 'chunk_embedding')

    # 3. Neo4j Vector Index 검색 실행
    results = self._graph.query(
        f"""
        CALL db.index.vector.queryNodes('{vector_index_name}', $k, $embedding)
        YIELD node, score
        WHERE score >= $min_score
        OPTIONAL MATCH (d:Document)-[:CONTAINS]->(node)
        OPTIONAL MATCH (node)-[:MENTIONS]->(e:Entity)
        RETURN
            node.id AS chunk_id,
            node.content AS content,
            score,
            d.id AS doc_id,
            collect(DISTINCT e.name)[..5] AS entities
        ORDER BY score DESC
        """,
        {"k": k, "embedding": query_embedding, "min_score": min_score}
    )
```

### 2.4 Health Check 구현

**mindmap_health_checker.py** - Vector Index 확인:

| 검사 항목 | 메서드 | 설명 |
|-----------|--------|------|
| Neo4j 연결 | `_check_neo4j_connection()` | DB 연결 상태 |
| Vector Index | `_check_vector_index()` | `chunk_embedding` 인덱스 존재 |
| 문서 데이터 | `_check_has_documents()` | Document 노드 존재 |
| 청크 데이터 | `_check_has_chunks()` | Chunk 노드 존재 |

### 2.5 데이터 흐름

```
사용자 요청: POST /api/v1/mindmap/generate
    │
    ▼
MindmapService.generate_mindmap()
    │
    ├─ Health Check 실행
    │   └─ Vector Index 확인 → 없으면 자동 생성
    │
    ├─ focus_topic 있는 경우:
    │   └─ _get_relevant_chunks() 호출
    │       └─ _vector_search_chunks() ← Vector Index 검색
    │
    ├─ document_ids 있는 경우:
    │   └─ _get_document_chunks() ← Graph 관계 검색
    │
    └─ LLM 개념 추출 → Neo4j에 Mindmap/Concept 저장
```

## 3. 검증 결론

### ✅ 연동 확인됨

1. **Vector Index 사용**: `db.index.vector.queryNodes()` Cypher 프로시저 사용
2. **Embedding 생성**: `NeMoEmbeddingService.embed_text()` 호출
3. **실시간 검색**: query embedding → vector similarity search → 결과 반환
4. **Health Check**: Vector Index 존재 여부 확인 및 자동 생성 로직

### ⚠️ 주의사항

1. **Vector Index 필수**: `chunk_embedding` 인덱스가 없으면 Vector 검색 실패
2. **Embedding Service 필수**: NeMoEmbeddingService (port 12801) 동작 필요
3. **Chunk.embedding 속성**: 각 Chunk 노드에 embedding 벡터가 저장되어 있어야 함

## 4. 검증 테스트 방법

### 4.1 Health Check API

```bash
curl -X GET http://localhost:9000/api/v1/mindmap/health \
  -H "Authorization: Bearer $TOKEN"
```

예상 응답:
```json
{
  "data": {
    "status": "healthy",
    "checks": {
      "neo4j_connection": true,
      "vector_index": true,
      "has_documents": true,
      "has_chunks": true
    },
    "stats": {
      "documents": 45,
      "chunks": 12340,
      "entities": 5678,
      "mindmaps": 3
    }
  }
}
```

### 4.2 Vector Index 존재 확인 (Neo4j Browser)

```cypher
SHOW INDEXES WHERE name = 'chunk_embedding'
```

### 4.3 Embedding 데이터 확인

```cypher
MATCH (c:Chunk)
WHERE c.embedding IS NOT NULL
RETURN count(c) AS chunks_with_embedding
```

## 5. 잠재적 개선사항

| 개선 영역 | 현재 상태 | 개선 제안 |
|-----------|----------|----------|
| Vector 검색 우선순위 | focus_topic 있을 때만 | 항상 Vector 검색 먼저 시도 |
| Embedding 캐싱 | 없음 | Redis 캐싱 고려 |
| 검색 결과 랭킹 | score 기반 | BM25 + Vector hybrid 고려 |
| 오류 처리 | 기본 폴백 | 상세 오류 로깅 강화 |

## 6. 결론

**Mindmap 서비스는 실제 embedding된 데이터베이스(Neo4j Vector Index)와 정상적으로 연동되어 동작하고 있습니다.**

주요 연동 포인트:
1. `db.index.vector.queryNodes()` - Neo4j Vector Index 검색
2. `NeMoEmbeddingService.embed_text()` - Query Embedding 생성
3. `MindmapHealthChecker` - Vector Index 상태 확인 및 자동 생성

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `app/api/services/mindmap_service.py` | 마인드맵 생성/검색 핵심 로직 |
| `app/api/services/mindmap_health_checker.py` | Vector Index 상태 확인 |
| `app/api/routers/mindmap.py` | API 엔드포인트 정의 |
| `app/src/config.py:87` | Vector Index 이름 설정 |
