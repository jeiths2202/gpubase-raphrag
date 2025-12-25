"""
Retrieval Stage
Handles document retrieval for RAG pipeline.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Protocol
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)


# ==================== Ports (Interfaces) ====================

class VectorStorePort(Protocol):
    """Port for vector store operations"""

    async def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search by vector similarity"""
        ...


class KeywordSearchPort(Protocol):
    """Port for keyword/full-text search"""

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search by keywords"""
        ...


class GraphStorePort(Protocol):
    """Port for graph-based retrieval"""

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search using graph relationships"""
        ...


# ==================== Enums ====================

class RetrievalStrategy(str, Enum):
    """Available retrieval strategies"""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    GRAPH = "graph"


class RerankingMethod(str, Enum):
    """Available reranking methods"""
    NONE = "none"
    CROSS_ENCODER = "cross_encoder"
    LLM = "llm"
    RECIPROCAL_RANK = "reciprocal_rank"


# ==================== Configuration ====================

@dataclass
class RetrievalConfig:
    """Configuration for retrieval stage"""
    strategy: RetrievalStrategy = RetrievalStrategy.VECTOR
    top_k: int = 10
    min_score: float = 0.0
    # Hybrid settings
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    # Reranking
    reranking: RerankingMethod = RerankingMethod.NONE
    rerank_top_k: int = 20
    # Filtering
    filters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0


# ==================== Result ====================

@dataclass
class RetrievedDocument:
    """A single retrieved document"""
    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # vector, keyword, graph

    @property
    def doc_name(self) -> str:
        return self.metadata.get("doc_name", self.id)


@dataclass
class RetrievalResult:
    """Result from retrieval stage"""
    documents: List[RetrievedDocument]
    query: str
    strategy: RetrievalStrategy
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.documents)

    @property
    def top_document(self) -> Optional[RetrievedDocument]:
        return self.documents[0] if self.documents else None

    def get_context(self, max_length: int = 8000) -> str:
        """Build context string from documents"""
        parts = []
        current_length = 0

        for doc in self.documents:
            part = f"[{doc.doc_name}] (score: {doc.score:.2f})\n{doc.content}"
            if current_length + len(part) > max_length:
                break
            parts.append(part)
            current_length += len(part)

        return "\n\n---\n\n".join(parts)


# ==================== Stage Implementation ====================

class RetrievalStage:
    """
    Retrieval stage of the RAG pipeline.

    Responsibilities:
    1. Execute retrieval using configured strategy
    2. Merge results from multiple sources (hybrid)
    3. Apply reranking if configured
    4. Filter and score documents

    This stage is completely independent of:
    - Embedding logic (receives vectors)
    - Generation logic
    - LLM concerns

    Example:
        stage = RetrievalStage(
            vector_store=vector_store,
            config=RetrievalConfig(strategy=RetrievalStrategy.HYBRID)
        )

        result = await stage.retrieve(
            query="What is RAG?",
            query_vector=embedding,
            user_id="user123"
        )

        for doc in result.documents:
            print(f"{doc.doc_name}: {doc.score:.2f}")
    """

    def __init__(
        self,
        vector_store: VectorStorePort,
        config: Optional[RetrievalConfig] = None,
        keyword_search: Optional[KeywordSearchPort] = None,
        graph_store: Optional[GraphStorePort] = None
    ):
        self.vector_store = vector_store
        self.config = config or RetrievalConfig()
        self.keyword_search = keyword_search
        self.graph_store = graph_store

    async def retrieve(
        self,
        query: str,
        query_vector: List[float],
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """
        Retrieve relevant documents.

        Args:
            query: Original query text
            query_vector: Query embedding
            user_id: Optional user filter
            session_id: Optional session filter
            filters: Additional filters

        Returns:
            RetrievalResult with ranked documents
        """
        start_time = time.time()

        # Build filters
        merged_filters = self._build_filters(user_id, session_id, filters)

        # Execute retrieval based on strategy
        documents = await self._execute_strategy(
            query, query_vector, merged_filters
        )

        # Apply reranking if configured
        if self.config.reranking != RerankingMethod.NONE:
            documents = await self._rerank(query, documents)

        # Filter by minimum score
        if self.config.min_score > 0:
            documents = [
                d for d in documents
                if d.score >= self.config.min_score
            ]

        # Limit to top_k
        documents = documents[:self.config.top_k]

        duration = (time.time() - start_time) * 1000

        return RetrievalResult(
            documents=documents,
            query=query,
            strategy=self.config.strategy,
            duration_ms=duration,
            metadata={
                "filters": merged_filters,
                "reranking": self.config.reranking.value
            }
        )

    async def _execute_strategy(
        self,
        query: str,
        query_vector: List[float],
        filters: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """Execute retrieval based on configured strategy"""
        strategy = self.config.strategy

        if strategy == RetrievalStrategy.VECTOR:
            return await self._vector_search(query_vector, filters)

        elif strategy == RetrievalStrategy.KEYWORD:
            if not self.keyword_search:
                logger.warning("Keyword search not available, falling back to vector")
                return await self._vector_search(query_vector, filters)
            return await self._keyword_search(query, filters)

        elif strategy == RetrievalStrategy.HYBRID:
            return await self._hybrid_search(query, query_vector, filters)

        elif strategy == RetrievalStrategy.GRAPH:
            if not self.graph_store:
                logger.warning("Graph store not available, falling back to vector")
                return await self._vector_search(query_vector, filters)
            return await self._graph_search(query, filters)

        else:
            return await self._vector_search(query_vector, filters)

    async def _vector_search(
        self,
        query_vector: List[float],
        filters: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """Execute vector similarity search"""
        results = await self.vector_store.search(
            query_vector=query_vector,
            top_k=self.config.rerank_top_k if self.config.reranking != RerankingMethod.NONE else self.config.top_k,
            filters=filters if filters else None
        )

        return [
            RetrievedDocument(
                id=r.get("id", r.get("chunk_id", "")),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
                source="vector"
            )
            for r in results
        ]

    async def _keyword_search(
        self,
        query: str,
        filters: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """Execute keyword search"""
        results = await self.keyword_search.search(
            query=query,
            top_k=self.config.top_k,
            filters=filters if filters else None
        )

        return [
            RetrievedDocument(
                id=r.get("id", r.get("chunk_id", "")),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
                source="keyword"
            )
            for r in results
        ]

    async def _graph_search(
        self,
        query: str,
        filters: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """Execute graph-based search"""
        results = await self.graph_store.search(
            query=query,
            top_k=self.config.top_k,
            filters=filters if filters else None
        )

        return [
            RetrievedDocument(
                id=r.get("id", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
                source="graph"
            )
            for r in results
        ]

    async def _hybrid_search(
        self,
        query: str,
        query_vector: List[float],
        filters: Dict[str, Any]
    ) -> List[RetrievedDocument]:
        """Execute hybrid search (vector + keyword)"""
        # Get vector results
        vector_docs = await self._vector_search(query_vector, filters)

        # Get keyword results if available
        keyword_docs = []
        if self.keyword_search:
            keyword_docs = await self._keyword_search(query, filters)

        # Merge results
        return self._merge_results(vector_docs, keyword_docs)

    def _merge_results(
        self,
        vector_docs: List[RetrievedDocument],
        keyword_docs: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """Merge and rerank results from multiple sources"""
        merged: Dict[str, RetrievedDocument] = {}

        # Add vector results with weighted score
        for rank, doc in enumerate(vector_docs):
            score = self.config.vector_weight * (1.0 / (rank + 1))
            merged[doc.id] = RetrievedDocument(
                id=doc.id,
                content=doc.content,
                score=score,
                metadata={**doc.metadata, "sources": ["vector"]},
                source="hybrid"
            )

        # Add/merge keyword results
        for rank, doc in enumerate(keyword_docs):
            score = self.config.keyword_weight * (1.0 / (rank + 1))
            if doc.id in merged:
                merged[doc.id].score += score
                merged[doc.id].metadata["sources"].append("keyword")
            else:
                merged[doc.id] = RetrievedDocument(
                    id=doc.id,
                    content=doc.content,
                    score=score,
                    metadata={**doc.metadata, "sources": ["keyword"]},
                    source="hybrid"
                )

        # Sort by combined score
        sorted_docs = sorted(
            merged.values(),
            key=lambda x: x.score,
            reverse=True
        )

        return sorted_docs

    async def _rerank(
        self,
        query: str,
        documents: List[RetrievedDocument]
    ) -> List[RetrievedDocument]:
        """Apply reranking to documents"""
        method = self.config.reranking

        if method == RerankingMethod.RECIPROCAL_RANK:
            # Simple reciprocal rank fusion (already applied in merge)
            return documents

        # For cross_encoder and llm reranking, would need additional ports
        # Placeholder for now
        logger.warning(f"Reranking method {method} not implemented, skipping")
        return documents

    def _build_filters(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        additional_filters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build merged filter dictionary"""
        filters = {**self.config.filters}

        if user_id:
            filters["user_id"] = user_id

        if session_id:
            filters["session_id"] = session_id

        if additional_filters:
            filters.update(additional_filters)

        return filters

    def with_strategy(self, strategy: RetrievalStrategy) -> "RetrievalStage":
        """Create new stage with different strategy"""
        new_config = RetrievalConfig(
            strategy=strategy,
            top_k=self.config.top_k,
            min_score=self.config.min_score,
            vector_weight=self.config.vector_weight,
            keyword_weight=self.config.keyword_weight,
            reranking=self.config.reranking,
            rerank_top_k=self.config.rerank_top_k,
            filters=self.config.filters
        )
        return RetrievalStage(
            self.vector_store,
            new_config,
            self.keyword_search,
            self.graph_store
        )

    def with_filters(self, filters: Dict[str, Any]) -> "RetrievalStage":
        """Create new stage with additional filters"""
        new_config = RetrievalConfig(
            strategy=self.config.strategy,
            top_k=self.config.top_k,
            min_score=self.config.min_score,
            vector_weight=self.config.vector_weight,
            keyword_weight=self.config.keyword_weight,
            reranking=self.config.reranking,
            rerank_top_k=self.config.rerank_top_k,
            filters={**self.config.filters, **filters}
        )
        return RetrievalStage(
            self.vector_store,
            new_config,
            self.keyword_search,
            self.graph_store
        )
