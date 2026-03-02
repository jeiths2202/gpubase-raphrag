# Design: Agentic RAG System

> **Feature**: Side 메뉴 "Analytics" → "Agentic RAG" 교체 + 제품별 Agent 기반 RAG 시스템
> **Plan**: `docs/01-plan/features/agentic-rag-system.plan.md`
> **Created**: 2026-02-07
> **Status**: Draft

---

## 1. 시스템 아키텍처

### 1.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend: AgenticRAGPage.tsx                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ 제품 선택 UI │  │ 되묻기 카드  │  │ 채팅 + 신뢰도 배지    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         └────────────────┼──────────────────────┘              │
│                          │ SSE Stream                           │
└──────────────────────────┼─────────────────────────────────────┘
                           │
                    POST /api/v1/agentic-rag/stream
                           │
┌──────────────────────────┼─────────────────────────────────────┐
│  Backend                 ▼                                      │
│  ┌─────────────────────────────────────────┐                   │
│  │  Router: agentic_rag.py                  │                   │
│  └────────────────────┬────────────────────┘                   │
│                       ▼                                         │
│  ┌─────────────────────────────────────────┐                   │
│  │  AgenticRAGService (오케스트레이터)        │                   │
│  │                                         │                    │
│  │  1. QueryRouter.classify()              │                    │
│  │     └→ 확정/되묻기/전체목록              │                    │
│  │  2. ProductAgent.search()               │                    │
│  │     └→ 구조화 검색 (LLM 없음)            │                    │
│  │  3. QueryTypeClassifier.classify()      │                    │
│  │     └→ 정형/비정형 판별                   │                    │
│  │  4a. TemplateResponseBuilder.build()    │  ← 정형 질문       │
│  │  4b. LLM + ResponseVerifier.verify()    │  ← 비정형 질문      │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ QueryRouter  │  │ ProductAgent │  │ ResponseVerifier     │  │
│  │ (다단계 확인) │  │ (9개 제품)   │  │ (cosine similarity)  │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 레이어 구조

```
Router Layer          → agentic_rag.py (얇은 레이어, 인증+직렬화)
  ↓
Orchestrator Layer    → AgenticRAGService (흐름 제어, SSE 생성)
  ↓
Classification Layer  → QueryRouter (제품 분류), QueryTypeClassifier (정형/비정형)
  ↓
Agent Layer           → ProductAgent 9개 (제품별 독립 검색)
  ↓
Knowledge Layer       → StructuredKnowledgeStore (요약본 파일 시스템)
  ↓
Response Layer        → TemplateResponseBuilder (정형) / LLM + ResponseVerifier (비정형)
```

---

## 2. Data Models (`models/agentic_rag.py`)

### 2.1 Enums

```python
# 기존 ProductId 재사용 (openframe_rag.py에서 import)
from .openframe_rag import ProductId, ConfidenceLevel

class QueryType(str, Enum):
    """질문 유형"""
    COMMAND = "command"           # 명령어 사용법
    ERROR_CODE = "error_code"    # 에러 코드 해석
    PARAMETER = "parameter"      # 파라미터/설정 설명
    CONFIG = "config"            # 설정 파일 방법
    FREEFORM = "freeform"        # 비정형 질문

class VerificationLevel(str, Enum):
    """신뢰도 검증 등급"""
    VERIFIED = "verified"         # 🟢 문서에서 직접 확인됨 (similarity >= 0.7)
    INFERRED = "inferred"         # 🟡 관련 문서 기반 추론 (0.4 <= similarity < 0.7)
    UNVERIFIED = "unverified"     # 🔴 문서에서 확인 불가 (similarity < 0.4)

class RouterDecision(str, Enum):
    """라우터 판정 결과"""
    CONFIRMED = "confirmed"              # 확정 라우팅 (score >= 0.8, gap >= 0.3)
    CLARIFICATION_NEEDED = "clarification_needed"  # 되묻기 필요
    NO_MATCH = "no_match"                # 매칭 없음 (전체 목록 표시)
```

### 2.2 Request Models

```python
class AgenticRAGRequest(BaseModel):
    """Agentic RAG 채팅 요청"""
    message: str = Field(..., min_length=1, max_length=8000)
    product: ProductId = Field(default=ProductId.AUTO)
    history: Optional[List[ChatMessage]] = None
    file_content: Optional[str] = None
    language: Optional[str] = Field(default="ja")

    # 되묻기 응답 시 사용자가 선택한 제품
    selected_product: Optional[ProductId] = Field(
        default=None,
        description="사용자가 되묻기에서 선택한 제품"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "tjesmgr BOOTの使い方を教えてください",
            "product": "auto",
            "language": "ja"
        }
    })
```

### 2.3 Response Models

```python
class ClarificationCandidate(BaseModel):
    """되묻기 후보 제품"""
    product: ProductId
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(description="매칭 이유")
    matched_keywords: List[str] = Field(default_factory=list)

class RouterResult(BaseModel):
    """라우터 분류 결과"""
    decision: RouterDecision
    product: Optional[ProductId] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    candidates: List[ClarificationCandidate] = Field(default_factory=list)
    all_scores: Dict[str, float] = Field(default_factory=dict)

class VerifiedSentence(BaseModel):
    """검증된 문장"""
    text: str
    level: VerificationLevel
    similarity: float = Field(ge=0.0, le=1.0)
    source_chunk: Optional[str] = None
    source_doc: Optional[str] = None

class AgenticRAGResponse(BaseModel):
    """Agentic RAG 채팅 응답"""
    success: bool
    response: str
    product: ProductId
    query_type: QueryType
    router_result: RouterResult
    verification: Optional[List[VerifiedSentence]] = None
    sources: ProductSources = Field(default_factory=ProductSources)
    confidence: ConfidenceLevel
    processing_time_ms: Optional[int] = None

class AgenticRAGHealth(BaseModel):
    """서비스 상태"""
    available: bool
    message: str
    agents: Dict[str, bool] = Field(default_factory=dict)
    knowledge_store_status: Dict[str, int] = Field(default_factory=dict)
```

### 2.4 SSE Event Models

```python
class SSEEvent(BaseModel):
    """SSE 이벤트 기본 모델"""
    type: str
    data: Dict[str, Any] = Field(default_factory=dict)

# SSE type별 data 구조:
# "classification"         → RouterResult
# "clarification_needed"   → {candidates: List[ClarificationCandidate], message: str}
# "search_progress"        → {product: str, step: str, progress: float}
# "template_response"      → {content: str, query_type: QueryType, sources: ProductSources}
# "llm_token"              → {token: str}
# "verification"           → {sentences: List[VerifiedSentence]}
# "sources"                → ProductSources
# "done"                   → {processing_time_ms: int, product: ProductId}
# "error"                  → {message: str, code: str}
```

---

## 3. API Router (`routers/agentic_rag.py`)

### 3.1 엔드포인트 상세

```python
router = APIRouter(prefix="/agentic-rag", tags=["Agentic RAG"])

@router.get("/health")
async def health_check(
    service: AgenticRAGService = Depends(get_agentic_rag_service),
) -> AgenticRAGHealth:
    """서비스 상태 확인 (인증 불필요)"""

@router.get("/products")
async def get_products(
    current_user: dict = Depends(get_current_user),
    service: AgenticRAGService = Depends(get_agentic_rag_service),
) -> dict:
    """지원 제품 목록 + Agent 상태 반환"""

@router.post("/classify")
async def classify_query(
    request: ClassifyRequest,
    current_user: dict = Depends(get_current_user),
    service: AgenticRAGService = Depends(get_agentic_rag_service),
) -> RouterResult:
    """쿼리 분류 (다단계 확인)"""

@router.post("/chat")
async def chat(
    request: AgenticRAGRequest,
    current_user: dict = Depends(get_current_user),
    service: AgenticRAGService = Depends(get_agentic_rag_service),
) -> AgenticRAGResponse:
    """동기식 Agent 채팅"""

@router.post("/stream")
async def stream_chat(
    request: AgenticRAGRequest,
    current_user: dict = Depends(get_current_user),
    service: AgenticRAGService = Depends(get_agentic_rag_service),
) -> StreamingResponse:
    """SSE 스트리밍 Agent 채팅"""
```

### 3.2 main.py 등록

```python
# app/api/main.py에 추가
from .routers import agentic_rag
app.include_router(agentic_rag.router, prefix=API_PREFIX)
```

---

## 4. QueryRouter 서비스 (`services/query_router_service.py`)

### 4.1 클래스 설계

```python
class QueryRouter:
    """
    다단계 확인 질문 라우터

    기존 ProductRouterService를 래핑하여 다단계 확인 로직을 추가합니다.

    판정 기준:
    - 확정 라우팅: top_score >= 0.8 AND (top_score - 2nd_score) >= 0.3
    - 되묻기: 0.5 <= top_score < 0.8 OR score_gap < 0.3
    - 매칭 없음: top_score < 0.5
    """

    CONFIRM_THRESHOLD = 0.8       # 자동 확정 최소 점수
    CLARIFY_THRESHOLD = 0.5       # 되묻기 최소 점수
    SCORE_GAP_THRESHOLD = 0.3     # 1위-2위 점수 차이 최소값

    def __init__(
        self,
        product_router: Optional[ProductRouterService] = None,
    ):
        self.product_router = product_router or get_product_router_service()

    def classify(self, query: str, language: str = "ja") -> RouterResult:
        """
        다단계 확인 분류

        Args:
            query: 사용자 쿼리
            language: UI 언어

        Returns:
            RouterResult with decision, product, candidates
        """
```

### 4.2 분류 로직 상세

```python
def classify(self, query: str, language: str = "ja") -> RouterResult:
    # 1단계: 기존 ProductRouterService로 점수 계산
    classification = self.product_router.classify(query)
    all_scores = classification.all_scores

    # 정렬된 제품 점수
    sorted_scores = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)

    if not sorted_scores or sorted_scores[0][1] == 0:
        return RouterResult(
            decision=RouterDecision.NO_MATCH,
            confidence=0.0,
            candidates=[],
            all_scores=all_scores,
        )

    top_product, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    score_gap = top_score - second_score

    # 2단계: 판정
    if top_score >= self.CONFIRM_THRESHOLD and score_gap >= self.SCORE_GAP_THRESHOLD:
        # 확정 라우팅
        return RouterResult(
            decision=RouterDecision.CONFIRMED,
            product=ProductId(top_product),
            confidence=top_score,
            candidates=[],
            all_scores=all_scores,
        )

    if top_score >= self.CLARIFY_THRESHOLD:
        # 되묻기 (상위 3개 후보 제시)
        candidates = [
            ClarificationCandidate(
                product=ProductId(prod),
                confidence=score,
                reason=self._get_match_reason(query, ProductId(prod)),
                matched_keywords=classification.matched_keywords
                    if prod == top_product else [],
            )
            for prod, score in sorted_scores[:3]
            if score >= 0.2
        ]
        return RouterResult(
            decision=RouterDecision.CLARIFICATION_NEEDED,
            product=ProductId(top_product),  # 기본 제안
            confidence=top_score,
            candidates=candidates,
            all_scores=all_scores,
        )

    # 매칭 없음
    return RouterResult(
        decision=RouterDecision.NO_MATCH,
        confidence=top_score,
        candidates=[],
        all_scores=all_scores,
    )
```

---

## 5. ProductAgent 설계 (`agents/agents/product_agents/`)

### 5.1 BaseProductAgent

```python
# base_product_agent.py

class BaseProductAgent:
    """
    제품별 Agent 베이스 클래스

    각 Agent는:
    - 자신의 ProductId를 갖는다
    - 구조화 데이터 소스 경로를 안다 (summaries/commands/, error-codes/ 등)
    - LLM 없이 키워드 기반 구조화 검색을 수행한다
    - 벡터/그래프 검색을 위임받아 실행한다
    """

    def __init__(
        self,
        product_id: ProductId,
        knowledge_domains: List[str],
        summary_paths: Dict[str, List[str]],  # domain → file paths
    ):
        self.product_id = product_id
        self.knowledge_domains = knowledge_domains
        self.summary_paths = summary_paths
        self._knowledge_store: Optional[StructuredKnowledgeStore] = None

    @property
    def knowledge_store(self) -> StructuredKnowledgeStore:
        if self._knowledge_store is None:
            self._knowledge_store = StructuredKnowledgeStore(
                product_id=self.product_id,
                summary_paths=self.summary_paths,
            )
        return self._knowledge_store

    async def search(
        self,
        query: str,
        query_type: Optional[QueryType] = None,
        vector_search_service=None,
        graph_search_service=None,
        top_k: int = 5,
    ) -> ProductSearchContext:
        """
        제품별 구조화 검색 실행

        Returns:
            ProductSearchContext with structured_results + vector_results + graph_results
        """
        results = ProductSearchContext(product=self.product_id)

        # 1. 구조화 검색 (LLM 없음, 파일 시스템 기반)
        results.structured_results = await self.knowledge_store.search(
            query=query,
            domains=self.knowledge_domains,
        )

        # 2. 벡터 검색 (선택적)
        if vector_search_service:
            results.vector_results = await self._vector_search(
                query, vector_search_service, top_k
            )

        # 3. 그래프 검색 (선택적)
        if graph_search_service:
            results.graph_results = await self._graph_search(
                query, graph_search_service, top_k
            )

        return results
```

### 5.2 제품별 Agent 인스턴스 구성

```python
# __init__.py

PRODUCT_AGENTS: Dict[ProductId, BaseProductAgent] = {
    ProductId.OPENFRAME_MVS: BaseProductAgent(
        product_id=ProductId.OPENFRAME_MVS,
        knowledge_domains=["commands", "error_codes", "configs", "glossary"],
        summary_paths={
            "commands": [
                "uploads/summaries/commands/OpenFrame_TJES_MVS.md",
                "uploads/summaries/commands/OpenFrame_Batch_MVS.md",
                "uploads/summaries/commands/OpenFrame_OSC_MVS.md",
                "uploads/summaries/commands/OpenFrame_OSI_MVS.md",
                "uploads/summaries/commands/OpenFrame_TACF_MVS.md",
                "uploads/summaries/commands/OpenFrame_HiDB_MVS.md",
                "uploads/summaries/commands/OpenFrame_Common_MVS.md",
                "uploads/summaries/commands/OpenFrame_Base_MVS.md",
            ],
            "error_codes": ["uploads/summaries/error-codes/BASE-*.md"],
            "configs": ["uploads/summaries/configs/OpenFrame_*.md"],
            "glossary": ["uploads/summaries/glossary/*.md"],
        },
    ),
    ProductId.OPENFRAME_BASE: BaseProductAgent(
        product_id=ProductId.OPENFRAME_BASE,
        knowledge_domains=["commands", "error_codes", "glossary"],
        summary_paths={
            "commands": [
                "uploads/summaries/commands/OpenFrame_Base_MVS.md",
                "uploads/summaries/commands/OpenFrame_Base_MSP.md",
                "uploads/summaries/commands/OpenFrame_Base_XSP.md",
            ],
            "error_codes": ["uploads/summaries/error-codes/BASE-*.md"],
            "glossary": ["uploads/summaries/glossary/*.md"],
        },
    ),
    ProductId.MSP_OPENFRAME: BaseProductAgent(
        product_id=ProductId.MSP_OPENFRAME,
        knowledge_domains=["commands", "error_codes"],
        summary_paths={
            "commands": [
                "uploads/summaries/commands/OpenFrame_MSP.md",
                "uploads/summaries/commands/OpenFrame_Batch_MSP.md",
                "uploads/summaries/commands/OpenFrame_AIM_MSP.md",
                "uploads/summaries/commands/OpenFrame_TACF_MSP.md",
                "uploads/summaries/commands/OpenFrame_Base_MSP.md",
            ],
            "error_codes": ["uploads/summaries/error-codes/BASE-*.md"],
        },
    ),
    ProductId.VOS3_OPENFRAME: BaseProductAgent(
        product_id=ProductId.VOS3_OPENFRAME,
        knowledge_domains=["commands", "error_codes"],
        summary_paths={
            "commands": [
                "uploads/summaries/commands/OpenFrame_VOS3.md",
                "uploads/summaries/commands/OpenFrame_Batch_VOS3.md",
                "uploads/summaries/commands/OpenFrame_TJES_VOS3.md",
            ],
            "error_codes": ["uploads/summaries/error-codes/BASE-*.md"],
        },
    ),
    ProductId.TIBERO7: BaseProductAgent(
        product_id=ProductId.TIBERO7,
        knowledge_domains=["commands", "error_codes"],
        summary_paths={
            "commands": ["uploads/summaries/commands/Tibero.md"],
            "error_codes": ["uploads/summaries/error-codes/Tibero-*.md"],
        },
    ),
    ProductId.TMAX: BaseProductAgent(
        product_id=ProductId.TMAX,
        knowledge_domains=["commands", "configs"],
        summary_paths={
            "commands": ["uploads/summaries/commands/Tmax.md"],
            "configs": ["uploads/summaries/configs/Tmax*.md"],
        },
    ),
    ProductId.OFASM: BaseProductAgent(
        product_id=ProductId.OFASM,
        knowledge_domains=["commands"],
        summary_paths={
            "commands": ["uploads/summaries/commands/OpenFrame.md"],  # OFASM 관련
        },
    ),
    ProductId.OFCOBOL: BaseProductAgent(
        product_id=ProductId.OFCOBOL,
        knowledge_domains=["commands"],
        summary_paths={
            "commands": ["uploads/summaries/commands/OpenFrame.md"],  # OFCOBOL 관련
        },
    ),
    ProductId.XSP_OPENFRAME: BaseProductAgent(
        product_id=ProductId.XSP_OPENFRAME,
        knowledge_domains=["commands"],
        summary_paths={
            "commands": [
                "uploads/summaries/commands/OpenFrame_XSP.md",
                "uploads/summaries/commands/OpenFrame_Batch_XSP.md",
                "uploads/summaries/commands/OpenFrame_AIM_XSP.md",
                "uploads/summaries/commands/OpenFrame_TACF_XSP.md",
                "uploads/summaries/commands/OpenFrame_Base_XSP.md",
            ],
        },
    ),
}

def get_product_agent(product_id: ProductId) -> Optional[BaseProductAgent]:
    """제품 Agent 획득"""
    return PRODUCT_AGENTS.get(product_id)
```

---

## 6. StructuredKnowledgeStore (`services/structured_knowledge_store.py`)

### 6.1 설계

```python
class StructuredKnowledgeStore:
    """
    구조화 지식 저장소

    요약본(summaries/) 파일 시스템에서 구조화 검색을 수행합니다.
    LLM 없이 키워드 매칭으로 정확한 정보를 반환합니다.

    캐싱 전략:
    - 파일 내용은 시작 시 메모리에 로드 (총 ~50MB 이하)
    - 검색은 in-memory로 수행 (< 10ms)
    """

    def __init__(
        self,
        product_id: ProductId,
        summary_paths: Dict[str, List[str]],
        base_dir: str = "uploads/summaries",
    ):
        self.product_id = product_id
        self.summary_paths = summary_paths
        self.base_dir = Path(base_dir)
        self._cache: Dict[str, List[KnowledgeEntry]] = {}
        self._loaded = False

    async def load(self) -> None:
        """요약본 파일을 파싱하여 메모리에 로드"""

    async def search(
        self,
        query: str,
        domains: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> List[KnowledgeEntry]:
        """
        구조화 검색

        검색 전략:
        1. 명령어 매칭: query에서 명령어 이름 추출 → 정확 매칭
        2. 에러 코드 매칭: -\d{4,5} 패턴 → 에러 DB 검색
        3. 키워드 매칭: BM25 기반 관련성 스코어링
        """


@dataclass
class KnowledgeEntry:
    """구조화 지식 항목"""
    entry_type: str        # "command", "error_code", "config", "glossary"
    name: str              # "tjesmgr BOOT", "-5212", "LRECL"
    content: str           # 전체 내용 (마크다운)
    syntax: Optional[str]  # 명령어 구문
    description: str       # 설명
    parameters: Optional[Dict[str, str]]  # 파라미터 목록
    examples: Optional[List[str]]         # 사용 예제
    source_file: str       # 출처 파일
    source_page: Optional[int]  # 출처 페이지
    product: str           # 제품 ID
```

### 6.2 요약본 파싱 규칙

```python
# 요약본 마크다운 파싱 패턴

# commands/*.md 파싱
COMMAND_PATTERN = re.compile(
    r'###?\s+(?P<name>\w+(?:\s+\w+)?)\n'   # ## tjesmgr BOOT
    r'.*?(?:\*\*구문\*\*|Syntax):\s*`(?P<syntax>[^`]+)`'  # 구문
    r'.*?(?:\*\*설명\*\*|Description):\s*(?P<desc>.+?)(?=\n#|\Z)',
    re.DOTALL
)

# error-codes/*.md 파싱
ERROR_CODE_PATTERN = re.compile(
    r'###?\s*(?P<code>-?\d{4,5})\s*[:\-]\s*(?P<name>\w+)\n'
    r'.*?(?:\*\*원인\*\*|Cause):\s*(?P<cause>.+?)\n'
    r'.*?(?:\*\*해결\*\*|Solution):\s*(?P<solution>.+?)(?=\n#|\Z)',
    re.DOTALL
)

# configs/*.md 파싱
CONFIG_PATTERN = re.compile(
    r'###?\s+(?P<param>\w+(?:\.\w+)*)\n'
    r'.*?(?:\*\*기본값\*\*|Default):\s*(?P<default>.+?)\n'
    r'.*?(?:\*\*설명\*\*|Description):\s*(?P<desc>.+?)(?=\n#|\Z)',
    re.DOTALL
)
```

---

## 7. QueryTypeClassifier (질문 유형 판별)

### 7.1 설계 (AgenticRAGService 내부 메서드)

```python
class QueryTypeClassifier:
    """
    질문 유형 판별기

    정형/비정형을 구분하여 응답 전략을 결정합니다.
    LLM 없이 정규식 패턴 매칭으로 판별합니다.
    """

    # 정형 질문 패턴
    STRUCTURED_PATTERNS: Dict[QueryType, List[re.Pattern]] = {
        QueryType.COMMAND: [
            re.compile(r'(\w+mgr|idcams|iebgener|dfsort|ofasm|ofcobol)\s+\w*', re.I),
            re.compile(r'(使い方|사용법|usage|how to use)\s', re.I),
            re.compile(r'(コマンド|명령어|command)\s', re.I),
        ],
        QueryType.ERROR_CODE: [
            re.compile(r'-\d{4,5}'),
            re.compile(r'ABEND\s+S\d{3}', re.I),
            re.compile(r'(エラー|에러|error)\s*(コード|코드|code)?', re.I),
        ],
        QueryType.PARAMETER: [
            re.compile(r'(パラメータ|파라미터|parameter|LRECL|BLKSIZE|RECFM)', re.I),
            re.compile(r'(DD\s+|DSN=|DISP=)', re.I),
        ],
        QueryType.CONFIG: [
            re.compile(r'(\.conf|設定|설정|config)', re.I),
            re.compile(r'(tjes\.conf|osc\.conf|tacf\.conf|ds\.conf)', re.I),
        ],
    }

    def classify(self, query: str, search_results: List[KnowledgeEntry]) -> QueryType:
        """
        질문 유형 판별

        판별 우선순위:
        1. 쿼리 패턴 매칭 → 정형 유형 결정
        2. 검색 결과에 구조화 항목이 있으면 → 정형
        3. 그 외 → FREEFORM (비정형)
        """
        # 1. 패턴 매칭
        for query_type, patterns in self.STRUCTURED_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(query):
                    return query_type

        # 2. 검색 결과 기반 판별
        if search_results:
            entry_types = {r.entry_type for r in search_results}
            if "command" in entry_types:
                return QueryType.COMMAND
            if "error_code" in entry_types:
                return QueryType.ERROR_CODE
            if "config" in entry_types:
                return QueryType.CONFIG

        # 3. 비정형
        return QueryType.FREEFORM
```

---

## 8. TemplateResponseBuilder (`services/template_response_builder.py`)

### 8.1 템플릿 정의

```python
class TemplateResponseBuilder:
    """
    정형 질문 템플릿 응답 생성기

    구조화 검색 결과를 마크다운 템플릿으로 변환합니다.
    LLM 개입 없음 → 환각 0%.
    """

    TEMPLATES: Dict[QueryType, str] = {
        QueryType.COMMAND: """## {name}

**구문**: `{syntax}`

**説明**: {description}

{parameters_section}

{examples_section}

📖 **出典**: {source_file}{page_info}
""",
        QueryType.ERROR_CODE: """## エラーコード {code}

**名称**: `{name}`

**原因**: {cause}

**解決方法**: {solution}

📖 **出典**: {source_file}{page_info}
""",
        QueryType.PARAMETER: """## {name}

**説明**: {description}

**デフォルト値**: {default_value}

**使用例**: {examples}

📖 **出典**: {source_file}{page_info}
""",
        QueryType.CONFIG: """## {name}

**説明**: {description}

**設定ファイル**: `{config_file}`

**パラメータ**:
{config_params}

📖 **出典**: {source_file}{page_info}
""",
    }

    def build(
        self,
        query_type: QueryType,
        entries: List[KnowledgeEntry],
        language: str = "ja",
    ) -> str:
        """
        템플릿 기반 응답 생성

        Args:
            query_type: 질문 유형
            entries: 검색된 지식 항목
            language: 출력 언어

        Returns:
            마크다운 포맷 응답 문자열
        """
```

---

## 9. ResponseVerifier (`services/response_verifier_service.py`)

### 9.1 설계

```python
class ResponseVerifier:
    """
    LLM 응답 사후 검증 레이어

    LLM이 생성한 응답의 각 문장을 소스 문서와 비교하여 신뢰도를 판정합니다.

    검증 방법:
    1. 응답을 문장 단위로 분리
    2. 각 문장을 소스 청크와 cosine similarity 비교
    3. 유사도 기반 신뢰도 등급 부여
    """

    VERIFIED_THRESHOLD = 0.7     # 🟢 확인됨
    INFERRED_THRESHOLD = 0.4     # 🟡 추정됨
    # < 0.4                       # 🔴 미확인

    def __init__(
        self,
        embedding_service: Optional[TextEmbeddingService] = None,
    ):
        self.embedding_service = embedding_service

    async def verify(
        self,
        response_text: str,
        source_chunks: List[str],
    ) -> List[VerifiedSentence]:
        """
        응답 검증

        Args:
            response_text: LLM이 생성한 응답 전체 텍스트
            source_chunks: 검색에 사용된 소스 청크 목록

        Returns:
            문장별 검증 결과 리스트
        """
        sentences = self._split_sentences(response_text)
        results = []

        for sentence in sentences:
            if len(sentence.strip()) < 5:
                continue

            # 각 문장과 소스 청크 간 최대 유사도 계산
            max_similarity = 0.0
            best_chunk = None
            best_doc = None

            if self.embedding_service:
                sentence_embedding = await self.embedding_service.embed_text(sentence)
                for chunk in source_chunks:
                    chunk_embedding = await self.embedding_service.embed_text(chunk)
                    similarity = self._cosine_similarity(
                        sentence_embedding, chunk_embedding
                    )
                    if similarity > max_similarity:
                        max_similarity = similarity
                        best_chunk = chunk[:200]
            else:
                # 임베딩 서비스 없을 때: 문자열 기반 유사도 (폴백)
                max_similarity = self._text_similarity(sentence, source_chunks)

            # 등급 판정
            if max_similarity >= self.VERIFIED_THRESHOLD:
                level = VerificationLevel.VERIFIED
            elif max_similarity >= self.INFERRED_THRESHOLD:
                level = VerificationLevel.INFERRED
            else:
                level = VerificationLevel.UNVERIFIED

            results.append(VerifiedSentence(
                text=sentence,
                level=level,
                similarity=round(max_similarity, 3),
                source_chunk=best_chunk,
            ))

        return results

    def filter_unverified(
        self,
        sentences: List[VerifiedSentence],
        remove_unverified: bool = True,
    ) -> Tuple[str, List[VerifiedSentence]]:
        """
        미확인 문장 필터링

        Args:
            sentences: 검증 결과
            remove_unverified: True면 🔴 문장 제거, False면 경고 표시

        Returns:
            (필터링된 응답 텍스트, 검증 결과)
        """
```

---

## 10. AgenticRAGService 오케스트레이터 (`services/agentic_rag_service.py`)

### 10.1 메인 흐름

```python
class AgenticRAGService:
    """
    Agentic RAG 오케스트레이터

    전체 파이프라인을 조율합니다:
    1. QueryRouter → 제품 분류
    2. ProductAgent → 구조화 검색
    3. QueryTypeClassifier → 정형/비정형 판별
    4. TemplateResponseBuilder / LLM + ResponseVerifier → 응답 생성
    """

    def __init__(
        self,
        query_router: Optional[QueryRouter] = None,
        template_builder: Optional[TemplateResponseBuilder] = None,
        response_verifier: Optional[ResponseVerifier] = None,
        learning_llm_service: Optional[LearningLLMService] = None,
        trtllm_adapter: Optional[TRTLLMAdapter] = None,
        vector_search_service=None,
        graph_search_service=None,
    ):
        self.query_router = query_router or QueryRouter()
        self.query_type_classifier = QueryTypeClassifier()
        self.template_builder = template_builder or TemplateResponseBuilder()
        self.response_verifier = response_verifier or ResponseVerifier()
        self.learning_llm_service = learning_llm_service
        self.trtllm_adapter = trtllm_adapter
        self.vector_search_service = vector_search_service
        self.graph_search_service = graph_search_service

    async def stream_chat(
        self,
        request: AgenticRAGRequest,
    ) -> AsyncGenerator[str, None]:
        """
        SSE 스트리밍 채팅 메인 흐름

        Yields:
            SSE 이벤트 문자열 (data: {...}\n\n)
        """
        start_time = time.time()

        # ─── Step 1: 제품 분류 ───
        if request.selected_product:
            # 되묻기 응답: 사용자가 제품 선택
            product = request.selected_product
            router_result = RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=product,
                confidence=1.0,
            )
        elif request.product == ProductId.AUTO:
            router_result = self.query_router.classify(
                request.message, request.language or "ja"
            )
        else:
            product = request.product
            router_result = RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=product,
                confidence=1.0,
            )

        yield self._sse_event("classification", router_result.model_dump())

        # 되묻기 필요 시 → 여기서 중단
        if router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            yield self._sse_event("clarification_needed", {
                "candidates": [c.model_dump() for c in router_result.candidates],
                "message": self._clarification_message(
                    router_result.candidates, request.language
                ),
            })
            yield self._sse_event("done", {"needs_clarification": True})
            return

        if router_result.decision == RouterDecision.NO_MATCH:
            yield self._sse_event("clarification_needed", {
                "candidates": [],
                "message": self._no_match_message(request.language),
            })
            yield self._sse_event("done", {"needs_clarification": True})
            return

        product = router_result.product

        # ─── Step 2: 제품 Agent 검색 ───
        agent = get_product_agent(product)
        yield self._sse_event("search_progress", {
            "product": product.value, "step": "searching", "progress": 0.3
        })

        search_context = await agent.search(
            query=request.message,
            vector_search_service=self.vector_search_service,
            graph_search_service=self.graph_search_service,
        )

        yield self._sse_event("search_progress", {
            "product": product.value, "step": "analyzing", "progress": 0.6
        })

        # ─── Step 3: 질문 유형 판별 ───
        query_type = self.query_type_classifier.classify(
            request.message, search_context.structured_results
        )

        # ─── Step 4: 응답 생성 ───
        if query_type != QueryType.FREEFORM and search_context.structured_results:
            # 정형 질문 → 템플릿 응답 (LLM 없음)
            response_text = self.template_builder.build(
                query_type=query_type,
                entries=search_context.structured_results,
                language=request.language or "ja",
            )
            yield self._sse_event("template_response", {
                "content": response_text,
                "query_type": query_type.value,
            })

        else:
            # 비정형 질문 → LLM 생성 + 검증
            context = search_context.to_context_string()

            async for token in self._generate_with_llm(
                request.message, context, product, request.language
            ):
                yield self._sse_event("llm_token", {"token": token})

            # 사후 검증
            full_response = self._collected_response
            source_chunks = [r.content for r in search_context.all_results()]

            verification = await self.response_verifier.verify(
                full_response, source_chunks
            )

            # 미확인 문장 필터링
            filtered_response, verification = self.response_verifier.filter_unverified(
                verification
            )

            yield self._sse_event("verification", {
                "sentences": [v.model_dump() for v in verification]
            })

        # ─── Step 5: 소스 + 완료 ───
        yield self._sse_event("sources", search_context.to_sources().model_dump())
        yield self._sse_event("done", {
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "product": product.value,
            "query_type": query_type.value,
        })

    def _sse_event(self, event_type: str, data: dict) -> str:
        """SSE 이벤트 포맷팅"""
        return f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"
```

---

## 11. Frontend Design (`AgenticRAGPage.tsx`)

### 11.1 컴포넌트 구조

```
AgenticRAGPage
├── ProductSelector           # 제품 선택 카드 그리드
│   └── ProductCard           # 개별 제품 카드 (아이콘+이름+상태)
├── ChatArea                  # 채팅 영역
│   ├── MessageList           # 메시지 목록
│   │   ├── UserMessage       # 사용자 메시지
│   │   ├── ClarificationCard # 되묻기 카드 (제품 선택 버튼)
│   │   └── AssistantMessage  # AI 응답
│   │       ├── VerificationBadge   # 🟢🟡🔴 신뢰도 배지
│   │       └── SourcePanel         # 출처 문서 패널
│   └── InputArea             # 입력 영역
│       ├── TextInput         # 텍스트 입력
│       ├── FileAttach        # 파일 첨부
│       └── SendButton        # 전송 버튼
└── SettingsPanel             # (선택적) 상세 설정
```

### 11.2 SSE 처리 로직

```typescript
// useAgenticRAGStream.ts (커스텀 훅)

const useAgenticRAGStream = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentProduct, setCurrentProduct] = useState<string>('auto');

  const sendMessage = async (text: string, selectedProduct?: string) => {
    const response = await fetch('/api/v1/agentic-rag/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        message: text,
        product: selectedProduct || currentProduct,
        selected_product: selectedProduct,  // 되묻기 응답 시
        language: currentLanguage,
      }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const events = chunk.split('\n\n').filter(Boolean);

      for (const event of events) {
        const data = JSON.parse(event.replace('data: ', ''));

        switch (data.type) {
          case 'classification':
            // 제품 분류 결과 표시
            setCurrentProduct(data.product);
            break;

          case 'clarification_needed':
            // 되묻기 카드 표시
            addClarificationMessage(data.candidates, data.message);
            return; // 스트리밍 중단, 사용자 선택 대기

          case 'template_response':
            // 정형 응답 전체 표시 (스트리밍 없음)
            addAssistantMessage(data.content, data.query_type);
            break;

          case 'llm_token':
            // 비정형 응답 토큰 스트리밍
            appendToLastMessage(data.token);
            break;

          case 'verification':
            // 신뢰도 배지 추가
            updateVerification(data.sentences);
            break;

          case 'sources':
            // 출처 패널 업데이트
            updateSources(data);
            break;

          case 'done':
            setIsStreaming(false);
            break;
        }
      }
    }
  };
};
```

### 11.3 되묻기 UI

```typescript
// ClarificationCard 컴포넌트

interface ClarificationCardProps {
  candidates: Array<{
    product: string;
    confidence: number;
    reason: string;
  }>;
  message: string;
  onSelect: (product: string) => void;
}

// 카드 형태로 후보 제품을 표시, 클릭 시 해당 제품으로 재쿼리
```

### 11.4 신뢰도 배지 UI

```typescript
// VerificationBadge 컴포넌트

const BADGE_CONFIG = {
  verified:   { icon: '🟢', label: '確認済み', color: '#22c55e' },
  inferred:   { icon: '🟡', label: '推定',     color: '#eab308' },
  unverified: { icon: '🔴', label: '未確認',   color: '#ef4444' },
};

// 각 문장 옆에 작은 배지로 표시
// 호버 시 출처 청크 표시
```

---

## 12. Sidebar 및 Route 변경

### 12.1 Sidebar.tsx 변경

```typescript
// 변경 전 (line 103-109)
{
    id: 'analytics',
    path: '/analytics',
    icon: <BarChart3 size={20} />,
    labelKey: 'common.nav.analytics',
    requiredRole: 'admin',
},

// 변경 후
{
    id: 'agenticRag',
    path: '/agentic-rag',
    icon: <Workflow size={20} />,           // lucide-react Workflow 아이콘
    labelKey: 'common.nav.agenticRag',
    // requiredRole 제거 → 모든 사용자 접근 가능
},
```

### 12.2 App.tsx 변경

```typescript
// 변경 전 (line 116)
<Route path="/analytics" element={<PlaceholderPage title="Analytics" />} />

// 변경 후
<Route path="/agentic-rag" element={<AgenticRAGPage />} />
```

### 12.3 i18n 변경

```json
// en/common.json
"nav": {
  "agenticRag": "Agentic RAG"
}

// ko/common.json
"nav": {
  "agenticRag": "에이전트 RAG"
}

// ja/common.json
"nav": {
  "agenticRag": "エージェントRAG"
}
```

---

## 13. DI 및 초기화 (`main.py`, `core/deps.py`)

### 13.1 서비스 초기화

```python
# main.py lifespan 내부

async def initialize_agentic_rag_service(
    learning_llm_service,
    trtllm_adapter,
    vector_search_service,
    graph_search_service,
) -> AgenticRAGService:
    """Agentic RAG 서비스 초기화"""
    service = AgenticRAGService(
        learning_llm_service=learning_llm_service,
        trtllm_adapter=trtllm_adapter,
        vector_search_service=vector_search_service,
        graph_search_service=graph_search_service,
    )
    await service.initialize()
    return service
```

### 13.2 DI 등록

```python
# core/deps.py에 추가

_agentic_rag_service: Optional[AgenticRAGService] = None

def get_agentic_rag_service() -> AgenticRAGService:
    global _agentic_rag_service
    if _agentic_rag_service is None:
        raise HTTPException(503, "Agentic RAG service not initialized")
    return _agentic_rag_service
```

---

## 14. 구현 순서 (Phase별 상세)

### Phase 1: Frontend 메뉴 교체 + 기본 페이지
```
수정: Sidebar.tsx (analytics → agenticRag)
수정: App.tsx (route 교체)
생성: AgenticRAGPage.tsx (기본 채팅 UI)
생성: agentic-rag.api.ts (API 클라이언트)
수정: en/common.json, ko/common.json, ja/common.json
```

### Phase 2: Backend 모델 + 라우터
```
생성: models/agentic_rag.py (Enum + Request/Response)
생성: routers/agentic_rag.py (5개 엔드포인트)
수정: main.py (라우터 등록)
수정: core/deps.py (DI 추가)
```

### Phase 3: 다단계 질문 라우터
```
생성: services/query_router_service.py (QueryRouter 클래스)
테스트: 분류 정확도 검증
```

### Phase 4: 제품별 Agent + 구조화 검색
```
생성: agents/agents/product_agents/__init__.py
생성: agents/agents/product_agents/base_product_agent.py
생성: services/structured_knowledge_store.py
설정: 9개 제품별 Agent 인스턴스 등록
```

### Phase 5: 응답 생성 + 검증
```
생성: services/template_response_builder.py
생성: services/response_verifier_service.py
통합: QueryTypeClassifier (AgenticRAGService 내부)
```

### Phase 6: Frontend 완성
```
구현: SSE 스트리밍 훅 (useAgenticRAGStream.ts)
구현: ClarificationCard 컴포넌트
구현: VerificationBadge 컴포넌트
구현: SourcePanel 컴포넌트
```

### Phase 7: 테스트
```
E2E: 기존 45개 Hallucination 테스트 호환
단위: QueryRouter 분류 정확도
단위: TemplateResponseBuilder 출력 검증
통합: SSE 스트리밍 전체 흐름
```

---

## 15. 파일 생성/수정 매트릭스

| 파일 | 작업 | Phase | LOC (예상) |
|------|------|-------|-----------|
| `models/agentic_rag.py` | 생성 | 2 | ~200 |
| `routers/agentic_rag.py` | 생성 | 2 | ~120 |
| `services/agentic_rag_service.py` | 생성 | 2,5 | ~350 |
| `services/query_router_service.py` | 생성 | 3 | ~150 |
| `services/structured_knowledge_store.py` | 생성 | 4 | ~250 |
| `services/template_response_builder.py` | 생성 | 5 | ~180 |
| `services/response_verifier_service.py` | 생성 | 5 | ~150 |
| `agents/agents/product_agents/__init__.py` | 생성 | 4 | ~120 |
| `agents/agents/product_agents/base_product_agent.py` | 생성 | 4 | ~150 |
| `main.py` | 수정 | 2 | +20 |
| `core/deps.py` | 수정 | 2 | +15 |
| `AgenticRAGPage.tsx` | 생성 | 1,6 | ~600 |
| `agentic-rag.api.ts` | 생성 | 1 | ~50 |
| `Sidebar.tsx` | 수정 | 1 | ~5 |
| `App.tsx` | 수정 | 1 | ~5 |
| `locales/*/common.json` (x3) | 수정 | 1 | +5 each |
| **합계** | | | **~2,380** |
