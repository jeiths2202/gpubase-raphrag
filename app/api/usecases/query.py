"""
Query Use Cases
Business logic for RAG query execution.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import logging

from .base import UseCase, UseCaseResult, UseCaseContext
from ..ports import LLMPort, EmbeddingPort, VectorStorePort, GraphStorePort
from ..ports.llm_port import LLMMessage, LLMRole, LLMConfig
from ..repositories import DocumentRepository, HistoryRepository

logger = logging.getLogger(__name__)


# ==================== Input/Output DTOs ====================

@dataclass
class QueryInput:
    """Input for RAG query execution"""
    question: str
    strategy: str = "hybrid"  # vector, keyword, hybrid, graph
    language: str = "ko"
    top_k: int = 5

    # Session context
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    use_session_docs: bool = True

    # Options
    include_sources: bool = True
    stream: bool = False


@dataclass
class ClassifyInput:
    """Input for query classification"""
    question: str


@dataclass
class SourceInfo:
    """Source information for a query result"""
    doc_id: str
    doc_name: str
    chunk_id: str
    content: str
    score: float
    source_type: str = "document"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "chunk_id": self.chunk_id,
            "content": self.content,
            "score": self.score,
            "source_type": self.source_type
        }


@dataclass
class QueryOutput:
    """Output of query execution"""
    answer: str
    strategy: str
    language: str
    confidence: float
    sources: List[SourceInfo] = field(default_factory=list)
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "strategy": self.strategy,
            "language": self.language,
            "confidence": self.confidence,
            "sources": [s.to_dict() for s in self.sources],
            "tokens_used": self.tokens_used
        }


@dataclass
class ClassifyOutput:
    """Output of query classification"""
    question: str
    strategy: str
    confidence: float
    language: str
    is_code_query: bool = False
    is_comprehensive: bool = False
    probabilities: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "language": self.language,
            "is_code_query": self.is_code_query,
            "is_comprehensive": self.is_comprehensive,
            "probabilities": self.probabilities
        }


# ==================== Use Cases ====================

class ExecuteQueryUseCase(UseCase[QueryInput, QueryOutput]):
    """
    Execute RAG query and generate answer.

    This use case:
    1. Classifies the query to determine optimal strategy
    2. Retrieves relevant documents using vector/graph search
    3. Generates answer using LLM with retrieved context
    4. Records query history

    All dependencies are injected for testability.
    """

    def __init__(
        self,
        llm: LLMPort,
        embedding: EmbeddingPort,
        vector_store: VectorStorePort,
        graph_store: GraphStorePort,
        document_repository: DocumentRepository,
        history_repository: HistoryRepository
    ):
        self.llm = llm
        self.embedding = embedding
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.document_repo = document_repository
        self.history_repo = history_repository

    async def execute(
        self,
        input: QueryInput,
        context: UseCaseContext
    ) -> UseCaseResult[QueryOutput]:
        """Execute RAG query"""
        start_time = time.time()

        try:
            # 1. Retrieve relevant documents
            sources = await self._retrieve_documents(
                input.question,
                input.strategy,
                input.top_k
            )

            # 2. Build context from sources
            context_text = self._build_context(sources)

            # 3. Generate answer using LLM
            answer, tokens_used = await self._generate_answer(
                input.question,
                context_text,
                input.language
            )

            # 4. Calculate confidence
            confidence = self._calculate_confidence(sources)

            # 5. Build output
            source_infos = [
                SourceInfo(
                    doc_id=s.get("doc_id", ""),
                    doc_name=s.get("doc_name", ""),
                    chunk_id=s.get("chunk_id", ""),
                    content=s.get("content", ""),
                    score=s.get("score", 0.0),
                    source_type=s.get("source_type", "document")
                )
                for s in sources
            ]

            output = QueryOutput(
                answer=answer,
                strategy=input.strategy,
                language=input.language,
                confidence=confidence,
                sources=source_infos if input.include_sources else [],
                tokens_used=tokens_used
            )

            # 6. Record history (async, non-blocking)
            # await self._record_history(input, output, context)

            execution_time = int((time.time() - start_time) * 1000)
            result = UseCaseResult.success(output, execution_time)
            self._log_execution(input, context, result)

            return result

        except Exception as e:
            logger.exception(f"Query execution failed: {e}")
            return UseCaseResult.failure(str(e), "QUERY_FAILED")

    async def _retrieve_documents(
        self,
        question: str,
        strategy: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents based on strategy"""

        # Generate embedding for question
        embedding_result = await self.embedding.embed_query(question)

        # Vector search
        search_results = await self.vector_store.search(
            collection="documents",
            query_vector=embedding_result.embedding,
            top_k=top_k,
            include_metadata=True
        )

        # Convert to source format
        sources = []
        for result in search_results:
            sources.append({
                "doc_id": result.document_id or result.id,
                "doc_name": result.metadata.get("doc_name", ""),
                "chunk_id": result.id,
                "content": result.content,
                "score": result.score,
                "source_type": "document"
            })

        # If hybrid strategy, also query graph
        if strategy in ("hybrid", "graph"):
            graph_results = await self._query_graph(question)
            sources.extend(graph_results)

        return sources

    async def _query_graph(self, question: str) -> List[Dict[str, Any]]:
        """Query knowledge graph for relevant entities"""
        try:
            # Simple entity-based search
            nodes = await self.graph_store.find_nodes(
                labels=["Concept"],
                limit=5
            )

            return [
                {
                    "doc_id": node.id,
                    "doc_name": node.properties.get("name", ""),
                    "chunk_id": node.id,
                    "content": node.properties.get("description", ""),
                    "score": 0.7,
                    "source_type": "graph"
                }
                for node in nodes
            ]
        except Exception as e:
            logger.warning(f"Graph query failed: {e}")
            return []

    def _build_context(self, sources: List[Dict[str, Any]]) -> str:
        """Build context string from sources"""
        context_parts = []

        for i, source in enumerate(sources, 1):
            content = source.get("content", "")
            doc_name = source.get("doc_name", "Unknown")
            context_parts.append(f"[Source {i}: {doc_name}]\n{content}")

        return "\n\n".join(context_parts)

    async def _generate_answer(
        self,
        question: str,
        context: str,
        language: str
    ) -> tuple[str, int]:
        """Generate answer using LLM"""

        system_prompt = """You are a helpful assistant that answers questions based on the provided context.
Answer in the same language as the question.
If the context doesn't contain relevant information, say so clearly."""

        user_prompt = f"""Context:
{context}

Question: {question}

Please provide a clear and comprehensive answer based on the context above."""

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMRole.USER, content=user_prompt)
        ]

        config = LLMConfig(temperature=0.7, max_tokens=2048)
        response = await self.llm.generate(messages, config)

        return response.content, response.usage.total_tokens

    def _calculate_confidence(self, sources: List[Dict[str, Any]]) -> float:
        """Calculate confidence score based on sources"""
        if not sources:
            return 0.3

        avg_score = sum(s.get("score", 0) for s in sources) / len(sources)
        return min(0.95, avg_score)


class ClassifyQueryUseCase(UseCase[ClassifyInput, ClassifyOutput]):
    """
    Classify query to determine optimal retrieval strategy.

    Analyzes the question to determine:
    - Best retrieval strategy (vector, keyword, hybrid, graph)
    - Language
    - Whether it's a code-related query
    - Complexity level
    """

    def __init__(self, llm: LLMPort):
        self.llm = llm

    async def execute(
        self,
        input: ClassifyInput,
        context: UseCaseContext
    ) -> UseCaseResult[ClassifyOutput]:
        """Execute query classification"""
        start_time = time.time()

        try:
            # Analyze question characteristics
            is_code = self._is_code_query(input.question)
            is_comprehensive = self._is_comprehensive(input.question)
            language = self._detect_language(input.question)

            # Determine strategy
            strategy, confidence, probabilities = await self._classify_strategy(
                input.question,
                is_code,
                is_comprehensive
            )

            output = ClassifyOutput(
                question=input.question,
                strategy=strategy,
                confidence=confidence,
                language=language,
                is_code_query=is_code,
                is_comprehensive=is_comprehensive,
                probabilities=probabilities
            )

            execution_time = int((time.time() - start_time) * 1000)
            return UseCaseResult.success(output, execution_time)

        except Exception as e:
            logger.exception(f"Query classification failed: {e}")
            return UseCaseResult.failure(str(e))

    def _is_code_query(self, question: str) -> bool:
        """Check if query is code-related"""
        code_keywords = [
            "코드", "code", "함수", "function", "에러", "error",
            "버그", "bug", "구현", "implement", "클래스", "class"
        ]
        return any(kw in question.lower() for kw in code_keywords)

    def _is_comprehensive(self, question: str) -> bool:
        """Check if query requires comprehensive answer"""
        comprehensive_keywords = [
            "설명", "explain", "비교", "compare", "차이", "difference",
            "어떻게", "how", "왜", "why", "모든", "all"
        ]
        return any(kw in question.lower() for kw in comprehensive_keywords)

    def _detect_language(self, question: str) -> str:
        """Detect question language"""
        korean_chars = sum(1 for c in question if '\uac00' <= c <= '\ud7af')
        return "ko" if korean_chars > len(question) * 0.3 else "en"

    async def _classify_strategy(
        self,
        question: str,
        is_code: bool,
        is_comprehensive: bool
    ) -> tuple[str, float, Dict[str, float]]:
        """Classify optimal retrieval strategy"""

        # Simple heuristic-based classification
        # In production, this could use a trained classifier

        probabilities = {
            "vector": 0.25,
            "keyword": 0.25,
            "hybrid": 0.25,
            "graph": 0.25
        }

        if is_code:
            probabilities["keyword"] += 0.3
            probabilities["vector"] -= 0.1

        if is_comprehensive:
            probabilities["hybrid"] += 0.2
            probabilities["graph"] += 0.2
            probabilities["keyword"] -= 0.2

        # Normalize
        total = sum(probabilities.values())
        probabilities = {k: v/total for k, v in probabilities.items()}

        # Select best strategy
        best_strategy = max(probabilities, key=probabilities.get)
        confidence = probabilities[best_strategy]

        return best_strategy, confidence, probabilities
