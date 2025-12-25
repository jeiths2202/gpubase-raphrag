"""
Retrieval Chain
Chain for document retrieval with embedding and vector search.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Protocol
import logging

from .base import Chain, ChainStep, ChainConfig, ChainResult

logger = logging.getLogger(__name__)


# ==================== Protocols for Dependencies ====================

class EmbeddingPort(Protocol):
    """Protocol for embedding service"""
    async def embed(self, text: str) -> List[float]: ...
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...


class VectorStorePort(Protocol):
    """Protocol for vector store"""
    async def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]: ...


class KeywordSearchPort(Protocol):
    """Protocol for keyword search (optional)"""
    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict[str, Any]]: ...


# ==================== Data Classes ====================

@dataclass
class RetrievalChainConfig(ChainConfig):
    """Configuration for retrieval chain"""
    top_k: int = 10
    use_hybrid: bool = False
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    min_score: float = 0.0
    rerank: bool = False
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalInput:
    """Input for retrieval chain"""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalOutput:
    """Output from retrieval chain"""
    documents: List[Dict[str, Any]]
    query_embedding: Optional[List[float]] = None
    total_found: int = 0


# ==================== Chain Steps ====================

class EmbedQueryStep(ChainStep[RetrievalInput, Dict[str, Any]]):
    """Step to embed the query"""

    def __init__(self, embedder: EmbeddingPort):
        super().__init__("embed_query")
        self.embedder = embedder

    async def execute(
        self,
        input: RetrievalInput,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Embed the query text"""
        embedding = await self.embedder.embed(input.query)

        return {
            "query": input.query,
            "embedding": embedding,
            "filters": input.filters,
            "user_id": input.user_id,
            "session_id": input.session_id
        }


class VectorSearchStep(ChainStep[Dict[str, Any], Dict[str, Any]]):
    """Step to search vector store"""

    def __init__(self, vector_store: VectorStorePort, config: RetrievalChainConfig):
        super().__init__("vector_search")
        self.vector_store = vector_store
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Search vector store with query embedding"""
        # Merge filters
        filters = {**self.config.filters, **input.get("filters", {})}

        # Add user/session filters if present
        if input.get("user_id"):
            filters["user_id"] = input["user_id"]

        results = await self.vector_store.search(
            query_vector=input["embedding"],
            top_k=self.config.top_k,
            filters=filters if filters else None
        )

        return {
            **input,
            "vector_results": results
        }


class KeywordSearchStep(ChainStep[Dict[str, Any], Dict[str, Any]]):
    """Step for keyword search (hybrid retrieval)"""

    def __init__(
        self,
        keyword_search: KeywordSearchPort,
        config: RetrievalChainConfig
    ):
        super().__init__("keyword_search")
        self.keyword_search = keyword_search
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform keyword search"""
        filters = {**self.config.filters, **input.get("filters", {})}

        results = await self.keyword_search.search(
            query=input["query"],
            top_k=self.config.top_k,
            filters=filters if filters else None
        )

        return {
            **input,
            "keyword_results": results
        }


class MergeResultsStep(ChainStep[Dict[str, Any], Dict[str, Any]]):
    """Step to merge vector and keyword results"""

    def __init__(self, config: RetrievalChainConfig):
        super().__init__("merge_results")
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge and rerank results from different sources"""
        vector_results = input.get("vector_results", [])
        keyword_results = input.get("keyword_results", [])

        if not keyword_results:
            # No hybrid, just use vector results
            merged = vector_results
        else:
            # Hybrid merge with weighted scoring
            merged = self._merge_results(vector_results, keyword_results)

        # Filter by minimum score
        if self.config.min_score > 0:
            merged = [
                r for r in merged
                if r.get("score", 0) >= self.config.min_score
            ]

        return {
            **input,
            "documents": merged[:self.config.top_k]
        }

    def _merge_results(
        self,
        vector_results: List[Dict],
        keyword_results: List[Dict]
    ) -> List[Dict]:
        """Merge results with weighted scoring"""
        # Create lookup by document ID
        merged: Dict[str, Dict] = {}

        # Add vector results
        for rank, doc in enumerate(vector_results):
            doc_id = doc.get("id") or doc.get("chunk_id")
            if doc_id:
                score = self.config.vector_weight * (1.0 / (rank + 1))
                merged[doc_id] = {**doc, "score": score, "sources": ["vector"]}

        # Add/merge keyword results
        for rank, doc in enumerate(keyword_results):
            doc_id = doc.get("id") or doc.get("chunk_id")
            if doc_id:
                score = self.config.keyword_weight * (1.0 / (rank + 1))
                if doc_id in merged:
                    merged[doc_id]["score"] += score
                    merged[doc_id]["sources"].append("keyword")
                else:
                    merged[doc_id] = {**doc, "score": score, "sources": ["keyword"]}

        # Sort by combined score
        sorted_results = sorted(
            merged.values(),
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        return sorted_results


class FormatOutputStep(ChainStep[Dict[str, Any], RetrievalOutput]):
    """Step to format final output"""

    def __init__(self):
        super().__init__("format_output")

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> RetrievalOutput:
        """Format the retrieval output"""
        documents = input.get("documents", [])

        return RetrievalOutput(
            documents=documents,
            query_embedding=input.get("embedding"),
            total_found=len(documents)
        )


# ==================== Retrieval Chain ====================

class RetrievalChain(Chain[RetrievalInput, RetrievalOutput]):
    """
    Chain for document retrieval.

    Supports:
    - Vector similarity search
    - Optional hybrid search (vector + keyword)
    - Result merging and ranking
    - Filtering by user/session

    Example:
        config = RetrievalChainConfig(top_k=10, use_hybrid=True)
        chain = RetrievalChain(embedder, vector_store, config, keyword_search)

        result = await chain.run(RetrievalInput(query="What is RAG?"))
        if result.is_success:
            for doc in result.output.documents:
                print(doc["content"])
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        vector_store: VectorStorePort,
        config: Optional[RetrievalChainConfig] = None,
        keyword_search: Optional[KeywordSearchPort] = None
    ):
        self._config = config or RetrievalChainConfig()
        super().__init__("retrieval", self._config)

        self.embedder = embedder
        self.vector_store = vector_store
        self.keyword_search = keyword_search

        # Build steps
        self._steps = self._build_steps()

    def _build_steps(self) -> List[ChainStep]:
        """Build chain steps based on configuration"""
        steps = [
            EmbedQueryStep(self.embedder),
            VectorSearchStep(self.vector_store, self._config)
        ]

        # Add keyword search for hybrid
        if self._config.use_hybrid and self.keyword_search:
            steps.append(KeywordSearchStep(self.keyword_search, self._config))

        # Add merge step
        steps.append(MergeResultsStep(self._config))

        # Add format step
        steps.append(FormatOutputStep())

        return steps

    def get_steps(self) -> List[ChainStep]:
        return self._steps

    def with_filters(self, filters: Dict[str, Any]) -> "RetrievalChain":
        """Create new chain with additional filters"""
        new_config = RetrievalChainConfig(
            top_k=self._config.top_k,
            use_hybrid=self._config.use_hybrid,
            vector_weight=self._config.vector_weight,
            keyword_weight=self._config.keyword_weight,
            min_score=self._config.min_score,
            rerank=self._config.rerank,
            filters={**self._config.filters, **filters}
        )
        return RetrievalChain(
            self.embedder,
            self.vector_store,
            new_config,
            self.keyword_search
        )
