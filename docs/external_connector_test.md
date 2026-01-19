# KMS 외부 커넥터 테스트 문서

## 개요
이 문서는 HybridRAG KMS의 외부 커넥터 영속성 기능을 테스트하기 위한 샘플 문서입니다.

## 주요 기능

### 1. 외부 리소스 연결
- **GitHub**: 저장소의 마크다운 문서 연동
- **Notion**: 페이지 및 데이터베이스 연동
- **Google Drive**: 문서 및 스프레드시트 연동
- **Confluence**: 위키 페이지 연동
- **OneNote**: 노트북 및 섹션 연동

### 2. 영속성 보장
외부 커넥터로 연결된 문서는 다음 저장소에 영구 저장됩니다:
- **PostgreSQL**: 연결 정보, 문서 메타데이터, 청크 정보
- **Neo4j**: 벡터 임베딩 (ExternalChunk 노드)

### 3. 격리 아키텍처
- 내부 문서 (Admin 업로드): `Chunk` 노드, `chunk_embedding` 인덱스
- 외부 문서 (사용자 연결): `ExternalChunk` 노드, `external_chunk_embedding` 인덱스

## 테스트 시나리오

1. GitHub OAuth 연결
2. 저장소 동기화 (문서 목록 가져오기)
3. 문서 처리 (청킹 + 임베딩)
4. RAG 검색 테스트
5. 서버 재시작 후 데이터 유지 확인

## 기술 스택
| 구성요소 | 기술 |
|---------|------|
| Backend | FastAPI (Python 3.10+) |
| Database | PostgreSQL + Neo4j |
| LLM | Nemotron Nano 9B |
| Embeddings | NV-EmbedQA-Mistral 7B |

## 결론
외부 커넥터 영속성 통합이 완료되어 서비스 재시작 시에도 사용자의 외부 연결 데이터가 유지됩니다.
