"""
RAG Pipeline Orchestrator
Coordinates Embedding, Retrieval, and Generation stages.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, AsyncIterator
import logging
import time

from .embedding import (
    EmbeddingStage,
    EmbeddingConfig,
    EmbeddingResult,
    EmbeddingPort,
    QueryEmbeddingStage
)
from .retrieval import (
    RetrievalStage,
    RetrievalConfig,
    RetrievalResult,
    RetrievalStrategy,
    VectorStorePort,
    KeywordSearchPort,
    GraphStorePort
)
from .generation import (
    GenerationStage,
    GenerationConfig,
    GenerationResult,
    LLMPort,
    PromptTemplatePort,
    StreamingLLMPort
)

logger = logging.getLogger(__name__)


# ==================== Configuration ====================

@dataclass
class PipelineConfig:
    """Configuration for complete RAG pipeline"""
    # Embedding settings
    embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    embedding_dimension: int = 1024
    # Retrieval settings
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.VECTOR
    retrieval_top_k: int = 10
    use_hybrid: bool = False
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    min_score: float = 0.0
    # Generation settings
    temperature: float = 0.7
    max_tokens: int = 2048
    max_context_length: int = 8000
    language: str = "auto"
    # Pipeline settings
    include_sources: bool = True
    enable_streaming: bool = False
    timeout_seconds: float = 120.0


@dataclass
class PipelineInput:
    """Input for RAG pipeline"""
    question: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    system_prompt: Optional[str] = None


@dataclass
class PipelineResult:
    """Result from RAG pipeline"""
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    embedding_duration_ms: float = 0.0
    retrieval_duration_ms: float = 0.0
    generation_duration_ms: float = 0.0
    total_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_count(self) -> int:
        return len(self.sources)


# ==================== Pipeline Orchestrator ====================

class RAGPipeline:
    """
    Complete RAG Pipeline Orchestrator.

    Coordinates three independent stages:
    1. Embedding Stage: Converts query to vector
    2. Retrieval Stage: Finds relevant documents
    3. Generation Stage: Produces answer from context

    Each stage is:
    - Independently testable
    - Swappable (different implementations)
    - Configurable
    - Observable (metrics, logging)

    Example:
        pipeline = RAGPipeline(
            embedder=embedder,
            vector_store=vector_store,
            llm=llm,
            config=PipelineConfig(
                retrieval_top_k=10,
                temperature=0.7
            )
        )

        result = await pipeline.run(PipelineInput(
            question="What is RAG?",
            user_id="user123"
        ))

        print(result.answer)
        print(f"Sources: {result.source_count}")
        print(f"Total time: {result.total_duration_ms:.2f}ms")
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        vector_store: VectorStorePort,
        llm: LLMPort,
        config: Optional[PipelineConfig] = None,
        prompt_template: Optional[PromptTemplatePort] = None,
        keyword_search: Optional[KeywordSearchPort] = None,
        graph_store: Optional[GraphStorePort] = None,
        streaming_llm: Optional[StreamingLLMPort] = None
    ):
        self.config = config or PipelineConfig()

        # Initialize stages
        self._embedding_stage = self._create_embedding_stage(embedder)
        self._retrieval_stage = self._create_retrieval_stage(
            vector_store, keyword_search, graph_store
        )
        self._generation_stage = self._create_generation_stage(
            llm, prompt_template, streaming_llm
        )

    def _create_embedding_stage(
        self,
        embedder: EmbeddingPort
    ) -> EmbeddingStage:
        """Create embedding stage"""
        config = EmbeddingConfig(
            model_name=self.config.embedding_model,
            dimension=self.config.embedding_dimension
        )
        return QueryEmbeddingStage(embedder, config)

    def _create_retrieval_stage(
        self,
        vector_store: VectorStorePort,
        keyword_search: Optional[KeywordSearchPort],
        graph_store: Optional[GraphStorePort]
    ) -> RetrievalStage:
        """Create retrieval stage"""
        strategy = self.config.retrieval_strategy
        if self.config.use_hybrid:
            strategy = RetrievalStrategy.HYBRID

        config = RetrievalConfig(
            strategy=strategy,
            top_k=self.config.retrieval_top_k,
            min_score=self.config.min_score,
            vector_weight=self.config.vector_weight,
            keyword_weight=self.config.keyword_weight
        )
        return RetrievalStage(
            vector_store, config, keyword_search, graph_store
        )

    def _create_generation_stage(
        self,
        llm: LLMPort,
        prompt_template: Optional[PromptTemplatePort],
        streaming_llm: Optional[StreamingLLMPort]
    ) -> GenerationStage:
        """Create generation stage"""
        config = GenerationConfig(
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            max_context_length=self.config.max_context_length,
            language=self.config.language,
            include_sources=self.config.include_sources
        )
        return GenerationStage(llm, prompt_template, config, streaming_llm)

    async def run(self, input: PipelineInput) -> PipelineResult:
        """
        Execute the complete RAG pipeline.

        Args:
            input: Pipeline input with question and filters

        Returns:
            PipelineResult with answer and metadata
        """
        start_time = time.time()
        metadata: Dict[str, Any] = {}

        try:
            # Stage 1: Embedding
            embedding_result = await self._run_embedding_stage(input.question)
            metadata["embedding"] = {
                "duration_ms": embedding_result.duration_ms,
                "dimension": embedding_result.dimension
            }

            # Stage 2: Retrieval
            retrieval_result = await self._run_retrieval_stage(
                query=input.question,
                query_vector=embedding_result.embeddings[0],
                user_id=input.user_id,
                session_id=input.session_id,
                filters=input.filters
            )
            metadata["retrieval"] = {
                "duration_ms": retrieval_result.duration_ms,
                "document_count": retrieval_result.count,
                "strategy": retrieval_result.strategy.value
            }

            # Stage 3: Generation
            context = retrieval_result.get_context(self.config.max_context_length)
            generation_result = await self._run_generation_stage(
                question=input.question,
                context=context,
                system_prompt=input.system_prompt
            )
            metadata["generation"] = {
                "duration_ms": generation_result.duration_ms,
                "context_length": len(context)
            }

            # Build sources
            sources = self._build_sources(retrieval_result)

            total_duration = (time.time() - start_time) * 1000

            return PipelineResult(
                answer=generation_result.answer,
                sources=sources,
                embedding_duration_ms=embedding_result.duration_ms,
                retrieval_duration_ms=retrieval_result.duration_ms,
                generation_duration_ms=generation_result.duration_ms,
                total_duration_ms=total_duration,
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            total_duration = (time.time() - start_time) * 1000
            return PipelineResult(
                answer=f"Error: {str(e)}",
                total_duration_ms=total_duration,
                metadata={"error": str(e)}
            )

    async def stream(
        self,
        input: PipelineInput
    ) -> AsyncIterator[str]:
        """
        Stream execute the RAG pipeline.

        Yields:
            Response tokens as they arrive
        """
        # Stage 1: Embedding
        embedding_result = await self._run_embedding_stage(input.question)

        # Stage 2: Retrieval
        retrieval_result = await self._run_retrieval_stage(
            query=input.question,
            query_vector=embedding_result.embeddings[0],
            user_id=input.user_id,
            session_id=input.session_id,
            filters=input.filters
        )

        # Stage 3: Stream Generation
        context = retrieval_result.get_context(self.config.max_context_length)

        async for token in self._generation_stage.stream_generate(
            question=input.question,
            context=context,
            system_prompt=input.system_prompt
        ):
            yield token

    async def _run_embedding_stage(self, query: str) -> EmbeddingResult:
        """Run embedding stage"""
        return await self._embedding_stage.embed_text(query)

    async def _run_retrieval_stage(
        self,
        query: str,
        query_vector: List[float],
        user_id: Optional[str],
        session_id: Optional[str],
        filters: Dict[str, Any]
    ) -> RetrievalResult:
        """Run retrieval stage"""
        return await self._retrieval_stage.retrieve(
            query=query,
            query_vector=query_vector,
            user_id=user_id,
            session_id=session_id,
            filters=filters
        )

    async def _run_generation_stage(
        self,
        question: str,
        context: str,
        system_prompt: Optional[str]
    ) -> GenerationResult:
        """Run generation stage"""
        return await self._generation_stage.generate(
            question=question,
            context=context,
            system_prompt=system_prompt
        )

    def _build_sources(self, retrieval_result: RetrievalResult) -> List[Dict[str, Any]]:
        """Build source list from retrieval result"""
        if not self.config.include_sources:
            return []

        return [
            {
                "doc_name": doc.doc_name,
                "score": doc.score,
                "id": doc.id,
                "source": doc.source
            }
            for doc in retrieval_result.documents
        ]

    # ==================== Stage Access ====================

    @property
    def embedding_stage(self) -> EmbeddingStage:
        """Access embedding stage directly"""
        return self._embedding_stage

    @property
    def retrieval_stage(self) -> RetrievalStage:
        """Access retrieval stage directly"""
        return self._retrieval_stage

    @property
    def generation_stage(self) -> GenerationStage:
        """Access generation stage directly"""
        return self._generation_stage

    # ==================== Pipeline Modification ====================

    def with_embedding_stage(
        self,
        embedding_stage: EmbeddingStage
    ) -> "RAGPipeline":
        """Create new pipeline with different embedding stage"""
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.config = self.config
        pipeline._embedding_stage = embedding_stage
        pipeline._retrieval_stage = self._retrieval_stage
        pipeline._generation_stage = self._generation_stage
        return pipeline

    def with_retrieval_stage(
        self,
        retrieval_stage: RetrievalStage
    ) -> "RAGPipeline":
        """Create new pipeline with different retrieval stage"""
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.config = self.config
        pipeline._embedding_stage = self._embedding_stage
        pipeline._retrieval_stage = retrieval_stage
        pipeline._generation_stage = self._generation_stage
        return pipeline

    def with_generation_stage(
        self,
        generation_stage: GenerationStage
    ) -> "RAGPipeline":
        """Create new pipeline with different generation stage"""
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline.config = self.config
        pipeline._embedding_stage = self._embedding_stage
        pipeline._retrieval_stage = self._retrieval_stage
        pipeline._generation_stage = generation_stage
        return pipeline

    def with_filters(self, filters: Dict[str, Any]) -> "RAGPipeline":
        """Create new pipeline with additional filters"""
        return self.with_retrieval_stage(
            self._retrieval_stage.with_filters(filters)
        )


# ==================== Factory ====================

class PipelineFactory:
    """
    Factory for creating RAG pipelines.

    Example:
        factory = PipelineFactory(embedder, vector_store, llm)

        # Standard pipeline
        pipeline = factory.create_standard()

        # Hybrid pipeline
        hybrid = factory.create_hybrid(keyword_search)

        # Analysis pipeline
        analysis = factory.create_for_analysis()
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        vector_store: VectorStorePort,
        llm: LLMPort
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.llm = llm

    def create_standard(
        self,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGPipeline:
        """Create standard pipeline"""
        return RAGPipeline(
            self.embedder,
            self.vector_store,
            self.llm,
            prompt_template=prompt_template
        )

    def create_hybrid(
        self,
        keyword_search: KeywordSearchPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGPipeline:
        """Create hybrid retrieval pipeline"""
        config = PipelineConfig(use_hybrid=True)
        return RAGPipeline(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template,
            keyword_search
        )

    def create_for_analysis(
        self,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGPipeline:
        """Create pipeline optimized for analysis"""
        config = PipelineConfig(
            retrieval_top_k=15,
            temperature=0.5,
            max_tokens=4096,
            max_context_length=12000
        )
        return RAGPipeline(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template
        )

    def create_for_code(
        self,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGPipeline:
        """Create pipeline optimized for code"""
        config = PipelineConfig(
            retrieval_top_k=20,
            temperature=0.3,
            max_tokens=4096
        )
        return RAGPipeline(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template
        )

    def create_streaming(
        self,
        streaming_llm: StreamingLLMPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGPipeline:
        """Create streaming pipeline"""
        config = PipelineConfig(enable_streaming=True)
        return RAGPipeline(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template,
            streaming_llm=streaming_llm
        )
