# Design: IMS Semantic Search & Chat Service

> Feature: `ims-semantic-search`
> Plan: `docs/01-plan/features/ims-semantic-search.plan.md`
> Created: 2026-03-07
> Status: Design Phase

---

## 1. Component Architecture

```
                        +-----------------------+
                        |   CLI (ofims/)        |
                        |   python -m ofims     |
                        +-----------+-----------+
                                    |
                                    | HTTP (requests)
                                    v
+-------------------------------------------------------------------+
|  FastAPI Server (localhost:9000)                                   |
|                                                                   |
|  +-------------------+    +----------------------------------+    |
|  | Router            |    | Router                           |    |
|  | ims_chat.py       |    | (existing endpoints preserved)   |    |
|  | NEW endpoints:    |    +----------------------------------+    |
|  |  POST /search     |                                            |
|  |  POST /chat/sem.  |                                            |
|  |  GET  /issues/... |                                            |
|  |  GET  /related/.. |                                            |
|  |  POST /summarize  |                                            |
|  |  POST /knowledge  |                                            |
|  +--------+----------+                                            |
|           |                                                       |
|  +--------v---------------------------------------------------+   |
|  | IMSSemanticSearchService (NEW)                             |   |
|  |  - semantic_search(query, limit) -> List[SearchResult]     |   |
|  |  - get_issue_content(ims_id) -> IssueContent               |   |
|  |  - get_related_issues(ims_id) -> List[RelatedIssue]        |   |
|  |  - summarize_issue(ims_id) -> str                          |   |
|  |  - chat_with_search(query, conv_id) -> SSE stream          |   |
|  |  - create_knowledge(ims_id, title) -> KnowledgeArticle     |   |
|  +--------+------+-------+------+----------------------------+   |
|           |      |       |      |                                 |
|    +------v-+ +--v---+ +-v---+ +v-----------+                    |
|    |BGE-M3  | |Issue | |LLM  | |Knowledge   |                    |
|    |IR Svc  | |Loader| |Port  | |Article Svc |                    |
|    |(exist) | |(NEW) | |(ex.) | |(existing)  |                    |
|    +---+----+ +--+---+ +--+--+ +------------+                    |
|        |         |         |                                      |
+-------------------------------------------------------------------+
         |         |         |
    +----v----+ +--v------+ +v-----------+
    | BGE-M3  | | Text    | | Qwen 32B   |
    | Server  | | Files   | | vLLM       |
    | :12801  | | uploads/| | :12810     |
    +---------+ | ims_*   | +------------+
                +---------+
```

---

## 2. File Structure (New & Modified Files)

### 2.1 New Files

```
ofims/                                     # CLI 패키지 (Phase 1)
├── __init__.py
├── __main__.py                            # python -m ofims entry point
├── cli.py                                 # argparse CLI commands
├── client.py                              # API client (requests + SSE)
├── config.py                              # CLI config (API URL, auth)
└── display.py                             # Rich terminal output

app/api/
├── services/
│   └── ims_semantic_search_service.py     # Core service (NEW)
└── models/
    └── ims_semantic.py                    # Pydantic models (NEW)
```

### 2.2 Modified Files

```
app/api/routers/ims_chat.py               # 6 new endpoints added
app/api/core/config.py                     # IMS_ISSUES_DIR, IMS_ISSUES_REMOTE_DIR settings
app/api/main.py                            # (no change needed - ims_chat router already registered)
```

---

## 3. Data Models (`app/api/models/ims_semantic.py`)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


# ============================================================================
# Issue Content (parsed from text file)
# ============================================================================

class IssueMetadata(BaseModel):
    """IMS 이슈 메타데이터 (텍스트 파일 헤더에서 파싱)"""
    ims_id: str = Field(..., description="IMS 이슈 번호", example="341013")
    product: str = Field("", description="제품명", example="OpenFrame PLI")
    version: str = Field("", description="버전", example="3, FixSet : FS07")
    module: str = Field("", description="모듈", example="General")
    category: str = Field("", description="카테고리", example="Enhancement Request")
    subject: str = Field("", description="제목")
    customer: str = Field("", description="고객사")
    status: str = Field("", description="상태", example="Closed_P")
    date: str = Field("", description="등록일", example="2025-04-08")


class ActionLogEntry(BaseModel):
    """조치 이력 항목"""
    index: int = Field(..., description="순번 (1부터)")
    content: str = Field(..., description="조치 내용")


class IssueContent(BaseModel):
    """완전한 IMS 이슈 내용 (텍스트 파일 파싱 결과)"""
    metadata: IssueMetadata
    description: str = Field("", description="상세 내용")
    action_log: List[ActionLogEntry] = Field(default_factory=list, description="조치 이력")
    raw_text: str = Field("", description="원본 텍스트 전문")
    # 이슈 내 참조 추출 결과
    referenced_ims_ids: List[str] = Field(default_factory=list, description="참조된 IMS 이슈 번호")
    referenced_urls: List[str] = Field(default_factory=list, description="참조된 URL")
    has_attachment_references: bool = Field(False, description="첨부파일 참조 여부")


# ============================================================================
# Search
# ============================================================================

class IMSSearchRequest(BaseModel):
    """시맨틱 검색 요청"""
    query: str = Field(..., min_length=2, description="자연어 검색 쿼리")
    limit: int = Field(10, ge=1, le=50, description="최대 결과 수")
    product_filter: Optional[str] = Field(None, description="제품 필터 (optional)")


class IMSSearchResult(BaseModel):
    """검색 결과 단건"""
    ims_id: str = Field(..., description="IMS 이슈 번호")
    score: float = Field(..., description="유사도 점수 (0.0~1.0)")
    subject: str = Field("", description="이슈 제목")
    product: str = Field("", description="제품명")
    status: str = Field("", description="상태")
    date: str = Field("", description="등록일")
    snippet: str = Field("", description="매칭 컨텐츠 스니펫 (200자)")


class IMSSearchResponse(BaseModel):
    """검색 응답"""
    query: str
    results: List[IMSSearchResult]
    total: int
    search_time_ms: float


# ============================================================================
# Related Issues
# ============================================================================

class RelatedIssue(BaseModel):
    """관련 이슈"""
    ims_id: str
    relation_type: str = Field(..., description="관계 유형: ims_reference, url_reference, action_reference")
    subject: str = Field("")
    product: str = Field("")
    status: str = Field("")
    context: str = Field("", description="참조 컨텍스트 (어디서 참조되었는지)")


class RelatedIssuesResponse(BaseModel):
    """관련 이슈 응답"""
    ims_id: str
    related_issues: List[RelatedIssue]
    total: int


# ============================================================================
# Semantic Chat (검색 + 대화 통합)
# ============================================================================

class IMSSemanticChatRequest(BaseModel):
    """시맨틱 검색 기반 채팅 요청 (issue_ids 불필요 - 자동 검색)"""
    query: str = Field(..., min_length=2, description="자연어 질문")
    conversation_id: Optional[str] = Field(None, description="기존 대화 ID")
    search_limit: int = Field(5, ge=1, le=20, description="검색할 이슈 수")
    include_related: bool = Field(True, description="관련 이슈 자동 포함")
    language: str = Field("auto", description="응답 언어: auto, ko, ja, en")


# ============================================================================
# Summary
# ============================================================================

class IMSSummaryRequest(BaseModel):
    """이슈 요약 요청"""
    ims_id: str = Field(..., description="이슈 번호")
    language: str = Field("auto", description="요약 언어")
    include_action_log: bool = Field(True, description="조치 이력 포함 여부")


class IMSSummaryResponse(BaseModel):
    """이슈 요약 응답"""
    ims_id: str
    subject: str
    summary: str = Field(..., description="LLM 생성 요약")
    key_points: List[str] = Field(default_factory=list, description="핵심 포인트")
    resolution: Optional[str] = Field(None, description="해결 방법 (있는 경우)")
    related_ims_ids: List[str] = Field(default_factory=list)


# ============================================================================
# Knowledge Creation
# ============================================================================

class IMSKnowledgeCreateRequest(BaseModel):
    """이슈 기반 지식 생성 요청"""
    ims_ids: List[str] = Field(..., min_length=1, description="소스 이슈 번호 목록")
    title: str = Field(..., min_length=5, description="지식 문서 제목")
    language: str = Field("auto", description="생성 언어")


class IMSKnowledgeCreateResponse(BaseModel):
    """지식 생성 응답"""
    title: str
    content: str = Field(..., description="생성된 지식 문서 내용 (Markdown)")
    source_issues: List[str]
    created_at: datetime
```

---

## 4. Service Design (`app/api/services/ims_semantic_search_service.py`)

### 4.1 Class Design

```python
class IMSSemanticSearchService:
    """
    IMS 시맨틱 검색 서비스 (Singleton)

    BGE-M3 임베딩 기반 자연어 검색 + 이슈 로딩 + LLM 채팅을 통합.
    일반 매뉴얼 RAG와 완전 분리된 IMS 전용 파이프라인.
    """

    _instance: Optional["IMSSemanticSearchService"] = None

    def __init__(self):
        self._ir_service: BgeM3IRService  # BGE-M3 검색
        self._issues_dir: Path            # 로컬 이슈 파일 디렉토리
        self._issues_remote_dir: str      # 서버측 원본 경로
        self._issue_cache: Dict[str, IssueContent]  # 파싱 캐시
        self._conversations: Dict[str, list]  # 대화 히스토리
```

### 4.2 Core Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `semantic_search` | `async (query: str, limit: int, product_filter: str?) -> IMSSearchResponse` | BGE-M3 벡터 검색 → IMS 이슈 목록 |
| `get_issue_content` | `(ims_id: str) -> IssueContent` | 텍스트 파일 파싱 (캐시) |
| `get_related_issues` | `(ims_id: str, depth: int=1) -> RelatedIssuesResponse` | IMS# 참조 추출 + 관련 이슈 로드 |
| `summarize_issue` | `async (ims_id: str, language: str) -> IMSSummaryResponse` | LLM 기반 이슈 요약 |
| `chat_with_search` | `async (request: IMSSemanticChatRequest) -> AsyncGenerator` | 검색 → 컨텍스트 구성 → LLM 스트리밍 |
| `create_knowledge` | `async (request: IMSKnowledgeCreateRequest) -> IMSKnowledgeCreateResponse` | 이슈 기반 지식 문서 생성 |

### 4.3 Internal Methods

| Method | Purpose |
|--------|---------|
| `_parse_issue_file(path: Path) -> IssueContent` | 텍스트 파일 → IssueContent 파싱 |
| `_extract_references(text: str) -> Tuple[List[str], List[str], bool]` | IMS#, URL, 첨부파일 참조 추출 |
| `_search_to_ims_ids(search_results: List[Dict]) -> List[str]` | Neo4j doc_name → ims_id 변환 |
| `_build_chat_context(issues: List[IssueContent]) -> str` | 이슈 내용 → LLM 컨텍스트 문자열 |
| `_call_llm_stream(system: str, messages: list) -> AsyncGenerator[str]` | vLLM 스트리밍 호출 |

### 4.4 Semantic Search Flow (Detail)

```
semantic_search("OSC EIBAID 값이 비어있는 문제", limit=10)
    |
    1. query → bge_m3_ir_service.encode_dense([query])
    |    → [1024-dim float vector]
    |
    2. Neo4j vector search (IMS 전용 필터)
    |    CALL db.index.vector.queryNodes('chunk_embedding', K, embedding)
    |    YIELD node, score
    |    MATCH (d:Document)-[:HAS_CHUNK|CONTAINS]->(node)
    |    WHERE toLower(d.filename) CONTAINS 'ims_issue'   ← IMS 전용 필터
    |       OR toLower(d.filename) =~ '\\d{5,6}\\.txt'    ← 이슈 번호 파일명
    |    RETURN node.content, d.filename, score
    |    ORDER BY score DESC LIMIT $limit
    |
    3. doc_name → ims_id 변환
    |    "ims_issues/341013.txt" → "341013"
    |    중복 ims_id 제거 (같은 이슈의 여러 chunk 가능)
    |    chunk별 최고 score를 이슈 score로 사용
    |
    4. ims_id별 메타데이터 로드
    |    uploads/ims_issues/341013.txt → IssueMetadata 파싱 (헤더만)
    |
    5. IMSSearchResponse 반환
         [{ims_id: "341013", score: 0.87, subject: "...", snippet: "..."}, ...]
```

### 4.5 Issue File Parser

```python
def _parse_issue_file(self, path: Path) -> IssueContent:
    """
    IMS 이슈 텍스트 파일 파싱.

    파일 포맷:
        === IMS Issue {ims_id} ===
        Product: {value}
        Version: {value}
        Module: {value}
        Category: {value}
        Subject: {value}
        Customer: {value}
        Status: {value}
        Date: {value}

        ## 상세 내용
        {description text}

        ## 조치 이력
        {action1}
        ---
        {action2}
        ---
    """
    # 1. UTF-8로 읽기 (fallback: cp949, euc-kr)
    # 2. 정규식으로 헤더 파싱
    #    re.match(r'^=== IMS Issue (\d+) ===$', first_line)
    #    re.match(r'^(Product|Version|Module|...): (.+)$', line)
    # 3. "## 상세 내용" ~ "## 조치 이력" 구간 → description
    # 4. "## 조치 이력" 이후 "---" 구분자로 split → action_log entries
    # 5. _extract_references(raw_text) → IMS#, URL, 첨부 참조
```

### 4.6 Reference Extraction Patterns

```python
import re

# IMS 이슈 번호 참조
_IMS_REF_PATTERN = re.compile(r'IMS#(\d{5,6})')

# Action 번호 참조
_ACTION_REF_PATTERN = re.compile(r'Action\s+No\.?\s*(\d{7})')

# URL 참조
_URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')

# 첨부파일 참조 (한국어/일본어/영어)
_ATTACHMENT_PATTERN = re.compile(
    r'첨부.*파일|첨부\s*참조|添付.*ファイル|attachment|添付参照',
    re.IGNORECASE
)
```

### 4.7 Chat Context Building

```python
def _build_chat_context(self, issues: List[IssueContent], max_tokens: int = 24000) -> str:
    """
    이슈 내용을 LLM 컨텍스트로 변환.

    전략:
    - 최대 5개 이슈 full content
    - 5개 초과 시 메타데이터 + description만 포함
    - 총 ~24K tokens 제한 (32K 컨텍스트 중 8K 여유)
    - 각 이슈당 ~4K chars 상한
    """
    context_parts = []
    chars_budget = max_tokens * 2  # ~2 chars per token (한국어/일본어)

    for i, issue in enumerate(issues):
        if i < 5:
            # Full content (메타 + 상세 + 조치이력)
            part = self._format_full_issue(issue, max_chars=4000)
        else:
            # Summary only (메타 + 상세 첫 500자)
            part = self._format_summary_issue(issue, max_chars=800)

        if len("\n".join(context_parts)) + len(part) > chars_budget:
            break
        context_parts.append(part)

    return "\n\n".join(context_parts)
```

---

## 5. API Endpoint Specifications

### 5.1 `POST /api/v1/ims-chat/search` - Semantic Search

**Request:**
```json
{
    "query": "OSC EIBAID 값이 비어있는 문제",
    "limit": 10,
    "product_filter": null
}
```

**Response (200):**
```json
{
    "query": "OSC EIBAID 값이 비어있는 문제",
    "results": [
        {
            "ims_id": "100012",
            "score": 0.8743,
            "subject": "[일본 아이치코퍼레이션] 온라인업무화면에서 엔터키(DFHENTER)처리가 이상동작",
            "product": "OpenFrame OSC",
            "status": "Closed",
            "date": "2015-09-01",
            "snippet": "EIBAID 값이 들어 있지 않은 것입니다..."
        }
    ],
    "total": 10,
    "search_time_ms": 1250.5
}
```

### 5.2 `POST /api/v1/ims-chat/chat/semantic` - Semantic Chat (SSE)

**Request:**
```json
{
    "query": "OSC에서 START TRANSID로 실행된 프로그램의 EIBAID가 비어있는 문제 해결방법",
    "conversation_id": null,
    "search_limit": 5,
    "include_related": true,
    "language": "auto"
}
```

**SSE Events:**
```
event: search_start
data: {"query": "...", "limit": 5}

event: search_results
data: {"results": [...], "total": 5, "search_time_ms": 1200}

event: context_loaded
data: {"issues_loaded": 5, "related_loaded": 3, "total_context_chars": 18000}

event: token
data: {"content": "OSC에서 "}

event: token
data: {"content": "EXEC CICS START TRANSID "}

... (streaming tokens)

event: sources
data: {"sources": [{"ims_id": "100012", "subject": "...", "score": 0.87}]}

event: done
data: {"conversation_id": "uuid", "total_tokens": 1500}
```

### 5.3 `GET /api/v1/ims-chat/issues/{ims_id}` - Issue Detail

**Response (200):**
```json
{
    "metadata": {
        "ims_id": "341013",
        "product": "OpenFrame PLI",
        "version": "3, FixSet : FS07",
        "module": "General",
        "category": "Enhancement Request",
        "subject": "[일본 스즈키] PLI 소스 내 EXEC SQL 문 안에 @ 마크가 있을 때...",
        "customer": "일본티맥스",
        "status": "Closed_P",
        "date": "2025-04-08"
    },
    "description": "...",
    "action_log": [
        {"index": 1, "content": "안녕하세요. 이영길 수석님..."},
        {"index": 2, "content": "@김기홍 매니저님..."}
    ],
    "raw_text": "...",
    "referenced_ims_ids": ["344158", "341031", "344004"],
    "referenced_urls": ["https://dbpms.tibero.com:7000/#/build/296981"],
    "has_attachment_references": true
}
```

### 5.4 `GET /api/v1/ims-chat/issues/{ims_id}/related` - Related Issues

**Response (200):**
```json
{
    "ims_id": "341013",
    "related_issues": [
        {
            "ims_id": "344158",
            "relation_type": "ims_reference",
            "subject": "[일본 스즈키] PLI 핫패치 배포",
            "product": "OpenFrame PLI",
            "status": "Closed_P",
            "context": "패치 IMS#344158 에서 핫패치로 배포 드립니다"
        },
        {
            "ims_id": "341031",
            "relation_type": "ims_reference",
            "subject": "Tibero ESQL 전처리 @ 마크 지원",
            "product": "Tibero",
            "status": "Closed",
            "context": "IMS#341031 의 패치가 반영된 티베로 바이너리를 사용하셔야 합니다"
        }
    ],
    "total": 3
}
```

### 5.5 `POST /api/v1/ims-chat/issues/summarize` - Issue Summary

**Request:**
```json
{
    "ims_id": "341013",
    "language": "ko",
    "include_action_log": true
}
```

**Response (200):**
```json
{
    "ims_id": "341013",
    "subject": "[일본 스즈키] PLI 소스 내 EXEC SQL 문...",
    "summary": "PLI 소스코드에서 EXEC SQL 문 내 호스트 변수명에 @ 마크가 포함된 경우 컴파일 시 syntax error가 발생하는 이슈. Tibero ESQL 전처리기에서 @ 기호를 올바르게 처리하지 못하는 것이 원인.",
    "key_points": [
        "OFPLI 컴파일러에서 @ 마크 포함 EXEC SQL 구문 처리 실패",
        "Tibero ESQL 전처리기 업데이트 필요 (IMS#341031)",
        "OFPLI 패치와 Tibero 패치 모두 적용 필요",
        "정식 배포용 빌드는 별도 진행 필요"
    ],
    "resolution": "OFPLI 패치(Revision 689)와 Tibero FS02PS_170921o 패치를 함께 적용. 새로운 전처리 함수가 없을 경우 기존 함수를 fallback 호출하므로 OFPLI 먼저 패치 가능.",
    "related_ims_ids": ["344158", "341031", "344004"]
}
```

### 5.6 `POST /api/v1/ims-chat/knowledge/create` - Knowledge Creation

**Request:**
```json
{
    "ims_ids": ["341013", "344158", "341031"],
    "title": "PLI EXEC SQL 내 @ 마크 컴파일 오류 해결 가이드",
    "language": "ko"
}
```

**Response (200):**
```json
{
    "title": "PLI EXEC SQL 내 @ 마크 컴파일 오류 해결 가이드",
    "content": "# PLI EXEC SQL 내 @ 마크 컴파일 오류 해결 가이드\n\n## 증상\n...\n## 원인\n...\n## 해결 방법\n...\n## 참고 이슈\n- IMS#341013, IMS#344158, IMS#341031",
    "source_issues": ["341013", "344158", "341031"],
    "created_at": "2026-03-07T09:30:00Z"
}
```

---

## 6. CLI Design (`ofims/`)

### 6.1 Entry Point (`__main__.py`)

```python
"""python -m ofims [command] [args]"""
from .cli import main
main()
```

### 6.2 CLI Commands (`cli.py`)

```python
import argparse

def main():
    parser = argparse.ArgumentParser(prog="ofims", description="IMS Semantic Search CLI")
    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Semantic search for IMS issues")
    p_search.add_argument("query", help="Natural language query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--product", default=None)

    # detail
    p_detail = sub.add_parser("detail", help="Get full issue content")
    p_detail.add_argument("ims_id", help="IMS issue number")

    # chat
    p_chat = sub.add_parser("chat", help="Chat with search results")
    p_chat.add_argument("query", help="Natural language question")
    p_chat.add_argument("--limit", type=int, default=5)
    p_chat.add_argument("--no-related", action="store_true")

    # summarize
    p_sum = sub.add_parser("summarize", help="Summarize an issue")
    p_sum.add_argument("ims_id", help="IMS issue number")
    p_sum.add_argument("--lang", default="auto")

    # related
    p_rel = sub.add_parser("related", help="Find related issues")
    p_rel.add_argument("ims_id", help="IMS issue number")

    # create-knowledge
    p_know = sub.add_parser("create-knowledge", help="Create knowledge from issues")
    p_know.add_argument("ims_ids", nargs="+", help="IMS issue numbers")
    p_know.add_argument("--title", required=True)
    p_know.add_argument("--lang", default="auto")

    args = parser.parse_args()
    # dispatch to client functions...
```

### 6.3 API Client (`client.py`)

```python
class IMSClient:
    """IMS Semantic Search API Client"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def login(self, username: str, password: str) -> str:
        """POST /api/v1/auth/login → access_token"""

    def search(self, query: str, limit: int = 10, product: str = None) -> dict:
        """POST /api/v1/ims-chat/search"""

    def get_issue(self, ims_id: str) -> dict:
        """GET /api/v1/ims-chat/issues/{ims_id}"""

    def get_related(self, ims_id: str) -> dict:
        """GET /api/v1/ims-chat/issues/{ims_id}/related"""

    def summarize(self, ims_id: str, language: str = "auto") -> dict:
        """POST /api/v1/ims-chat/issues/summarize"""

    def chat_stream(self, query: str, limit: int = 5, include_related: bool = True):
        """POST /api/v1/ims-chat/chat/semantic → SSE stream iterator"""

    def create_knowledge(self, ims_ids: list, title: str, lang: str = "auto") -> dict:
        """POST /api/v1/ims-chat/knowledge/create"""
```

### 6.4 Terminal Display (`display.py`)

```python
# Rich 라이브러리 사용 (없으면 plain text fallback)
# - 검색 결과: 테이블 포맷 (IMS ID | Score | Subject | Product | Status)
# - 이슈 상세: Panel with syntax highlighting
# - 채팅: 스트리밍 토큰 실시간 출력 (SSE event → print)
# - 요약: Markdown 렌더링
# - 관련 이슈: Tree 구조
```

---

## 7. Neo4j IMS Issue Document 필터 전략

### 7.1 IMS 이슈 전용 필터

IMS 이슈 임베딩 Document의 filename 패턴 확인이 필요하지만, 가능한 패턴:

```cypher
-- Option A: filename에 'ims_issue' 또는 이슈번호 패턴 포함
WHERE toLower(d.filename) CONTAINS 'ims_issue'
   OR d.filename =~ '\\d{5,6}\\.txt'

-- Option B: 별도 label 사용 (IMS Document)
MATCH (d:Document:IMSIssue)-[:HAS_CHUNK]->(node)

-- Option C: property 기반
WHERE d.doc_type = 'ims_issue'
```

**결정**: 실제 Neo4j 데이터 확인 후 최적 필터 결정. 우선 Option A로 구현하고, 필요시 전용 인덱스 추가.

### 7.2 Fallback: BGE-M3 Direct Search

Neo4j에 IMS 이슈가 별도 인덱싱되지 않은 경우:

```python
# Direct approach: 텍스트 파일 목록에서 직접 검색
async def _fallback_search(self, query: str, limit: int) -> List[IMSSearchResult]:
    """
    BGE-M3 encode_dense() + 로컬 이슈 파일 임베딩 비교
    - 이슈 파일 목록 스캔 (21K files, 캐시됨)
    - 이슈별 subject + description 텍스트 → BGE-M3 encode
    - cosine similarity 정렬
    """
```

---

## 8. LLM Integration

### 8.1 LLM 호출 방식

기존 `LLMPort` 인터페이스 활용 (vLLM Qwen 32B):

```python
from ..ports.llm_port import LLMPort, LLMMessage, LLMRole, LLMConfig

# 또는 직접 httpx로 vLLM OpenAI-compatible API 호출
async def _call_llm_stream(self, system_prompt: str, user_msg: str):
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{self._llm_url}/chat/completions",
            json={
                "model": self._llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                "stream": True,
                "temperature": 0.3,
                "max_tokens": 2048
            }
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
```

### 8.2 System Prompts

**Semantic Chat:**
```
You are an AI assistant that analyzes TmaxSoft IMS issues.
Your knowledge is STRICTLY LIMITED to the following IMS issues found by semantic search.

RULES:
1. Only answer from the provided issue data. Never invent information.
2. Always cite IMS issue numbers (e.g., IMS#341013).
3. When multiple issues are related, explain the relationships.
4. If the answer is not in the provided issues, say so clearly.
5. Respond in {language}.

Found Issues:
{context}
```

**Summary:**
```
Summarize the following IMS issue concisely.
Include: problem description, root cause (if known), resolution (if resolved).
Output format:
- summary: 2-3 sentence overview
- key_points: bullet list of important facts
- resolution: resolution method (if the issue is resolved/closed)
Respond in {language}.

Issue:
{issue_content}
```

**Knowledge Creation:**
```
Create a knowledge document based on the following IMS issues.
The document should be a practical guide that other engineers can reference.
Include: symptoms, root cause, resolution steps, related references.
Format as Markdown.
Respond in {language}.

Source Issues:
{issues_content}
```

---

## 9. Configuration Additions (`app/api/core/config.py`)

```python
# IMS Semantic Search settings
IMS_ISSUES_DIR: str = "uploads/ims_issues"
IMS_ISSUES_REMOTE_DIR: str = "/raid/users/ofuser/work/of7/ims_issues_20260302"
IMS_SEARCH_DEFAULT_LIMIT: int = 10
IMS_SEARCH_MAX_LIMIT: int = 50
IMS_CHAT_MAX_CONTEXT_ISSUES: int = 10
IMS_CHAT_MAX_CONTEXT_CHARS: int = 48000  # ~24K tokens
IMS_ISSUE_CACHE_SIZE: int = 500  # LRU 캐시 사이즈
```

---

## 10. Error Handling

| Error Case | HTTP Status | Response |
|------------|-------------|----------|
| BGE-M3 서버 불가 | 503 | `{"detail": "BGE-M3 embedding service unavailable"}` |
| 이슈 파일 없음 | 404 | `{"detail": "IMS issue {ims_id} not found"}` |
| Neo4j 연결 실패 | 503 | `{"detail": "Search service temporarily unavailable"}` |
| LLM 타임아웃 | 504 | `{"detail": "LLM response timeout"}` |
| 검색 결과 없음 | 200 | `{"results": [], "total": 0}` (정상 응답, 빈 결과) |
| 잘못된 ims_id 형식 | 400 | `{"detail": "Invalid IMS ID format"}` |

---

## 11. Implementation Order

```
Step 1: Models (ims_semantic.py)
  └── Pydantic 모델 정의
       |
Step 2: Issue Parser (ims_semantic_search_service.py - parser part)
  └── _parse_issue_file(), _extract_references()
       |
Step 3: Semantic Search (ims_semantic_search_service.py - search part)
  └── semantic_search() using bge_m3_ir_service
       |
Step 4: Router Endpoints (ims_chat.py - new endpoints)
  └── POST /search, GET /issues/{id}, GET /issues/{id}/related
       |
Step 5: Config (config.py)
  └── IMS_ISSUES_DIR 등 설정 추가
       |
Step 6: CLI (ofims/ package)
  └── search, detail, related commands
       |
Step 7: Chat Integration (service + router)
  └── chat_with_search(), POST /chat/semantic
       |
Step 8: Summary & Knowledge (service + router)
  └── summarize_issue(), create_knowledge()
       |
Step 9: CLI Chat & Summary (ofims/)
  └── chat, summarize, create-knowledge commands
```

---

## 12. Testing Strategy

### Unit Tests
```
tests/unit/
├── test_ims_issue_parser.py      # 파일 파싱 (다양한 포맷, 인코딩)
├── test_ims_reference_extract.py # IMS#, URL, 첨부 참조 추출
├── test_ims_search_service.py    # 검색 로직 (mock BGE-M3)
└── test_ims_semantic_models.py   # Pydantic 모델 validation
```

### Integration Tests
```bash
# CLI 검색 테스트
python -m ofims search "EIBAID 값이 비어있는 문제" --limit 5

# CLI 이슈 상세
python -m ofims detail 100012

# CLI 채팅
python -m ofims chat "tjesmgr BOOT 에러 원인"

# API 직접 테스트
curl -s -X POST http://localhost:9000/api/v1/ims-chat/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "OSC EIBAID", "limit": 5}'
```

---

## 13. Dependencies

### Python (requirements-api.txt에 이미 포함)
- `httpx` - BGE-M3 API 호출 (existing)
- `neo4j` - Neo4j driver (existing)
- `pydantic` - 데이터 모델 (existing)

### CLI 추가 (optional)
- `rich` - 터미널 출력 포맷팅 (optional, fallback to plain text)

---

## Next Step

> `/pdca do ims-semantic-search` 로 구현 시작
