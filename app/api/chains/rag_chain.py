"""
RAG Chain
Complete Retrieval-Augmented Generation pipeline.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Protocol
import logging

from .base import Chain, ChainStep, ChainConfig, ChainResult, CompositeChain
from .retrieval_chain import (
    RetrievalChain,
    RetrievalChainConfig,
    RetrievalInput,
    RetrievalOutput,
    EmbeddingPort,
    VectorStorePort,
    KeywordSearchPort
)
from .generation_chain import (
    GenerationChain,
    GenerationChainConfig,
    GenerationInput,
    GenerationOutput,
    LLMPort,
    PromptTemplatePort
)

logger = logging.getLogger(__name__)


# ==================== Data Classes ====================

@dataclass
class RAGChainConfig(ChainConfig):
    """Configuration for full RAG chain"""
    # Retrieval settings
    retrieval_top_k: int = 10
    use_hybrid: bool = False
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    min_score: float = 0.0
    # Generation settings
    temperature: float = 0.7
    max_tokens: int = 2048
    max_context_length: int = 8000
    # Pipeline settings
    include_sources: bool = True
    language: str = "auto"


@dataclass
class RAGInput:
    """Input for RAG chain"""
    question: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    system_prompt: Optional[str] = None


@dataclass
class RAGOutput:
    """Output from RAG chain"""
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== Chain Steps ====================

class PrepareRetrievalStep(ChainStep[RAGInput, RetrievalInput]):
    """Convert RAG input to retrieval input"""

    def __init__(self):
        super().__init__("prepare_retrieval")

    async def execute(
        self,
        input: RAGInput,
        context: Dict[str, Any]
    ) -> RetrievalInput:
        return RetrievalInput(
            query=input.question,
            user_id=input.user_id,
            session_id=input.session_id,
            filters=input.filters
        )


class BuildContextStep(ChainStep[RetrievalOutput, Dict[str, Any]]):
    """Build context from retrieved documents"""

    def __init__(self, config: RAGChainConfig):
        super().__init__("build_context")
        self.config = config

    async def execute(
        self,
        input: RetrievalOutput,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build context string from documents"""
        documents = input.documents
        context_parts = []
        current_length = 0

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            doc_name = doc.get("doc_name", f"Source {i}")
            score = doc.get("score", 0)

            part = f"[{doc_name}] (relevance: {score:.2f})\n{content}"

            if current_length + len(part) > self.config.max_context_length:
                break

            context_parts.append(part)
            current_length += len(part)

        context_str = "\n\n---\n\n".join(context_parts)

        return {
            "context": context_str,
            "documents": documents,
            "retrieval_count": len(documents)
        }


class PrepareGenerationStep(ChainStep[Dict[str, Any], GenerationInput]):
    """Prepare input for generation chain"""

    def __init__(self, config: RAGChainConfig):
        super().__init__("prepare_generation")
        self.config = config

    async def execute(
        self,
        input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> GenerationInput:
        """Prepare generation input"""
        # Get original RAG input from context
        rag_input: RAGInput = context.get("rag_input")

        return GenerationInput(
            question=rag_input.question if rag_input else "",
            context=input["context"],
            system_prompt=rag_input.system_prompt if rag_input else None,
            additional_context={
                "retrieval_count": input["retrieval_count"],
                "language": self.config.language
            }
        )


class FormatRAGOutputStep(ChainStep[GenerationOutput, RAGOutput]):
    """Format final RAG output"""

    def __init__(self, config: RAGChainConfig):
        super().__init__("format_rag_output")
        self.config = config

    async def execute(
        self,
        input: GenerationOutput,
        context: Dict[str, Any]
    ) -> RAGOutput:
        """Format RAG output with sources"""
        documents = context.get("documents", [])

        sources = []
        if self.config.include_sources:
            for doc in documents:
                sources.append({
                    "doc_name": doc.get("doc_name", "Unknown"),
                    "score": doc.get("score", 0),
                    "chunk_id": doc.get("chunk_id"),
                    "page": doc.get("page")
                })

        return RAGOutput(
            answer=input.answer,
            sources=sources,
            retrieval_count=len(documents),
            metadata={
                **input.metadata,
                "prompt_tokens": input.prompt_tokens,
                "completion_tokens": input.completion_tokens
            }
        )


# ==================== RAG Chain ====================

class RAGChain(Chain[RAGInput, RAGOutput]):
    """
    Complete RAG (Retrieval-Augmented Generation) Chain.

    Combines:
    1. Query embedding
    2. Document retrieval (vector/hybrid)
    3. Context building
    4. Answer generation

    Example:
        config = RAGChainConfig(
            retrieval_top_k=10,
            use_hybrid=True,
            temperature=0.7
        )

        chain = RAGChain(
            embedder=embedder,
            vector_store=vector_store,
            llm=llm,
            config=config
        )

        result = await chain.run(RAGInput(
            question="What is RAG?",
            user_id="user123"
        ))

        if result.is_success:
            print(result.output.answer)
            print(f"Sources: {result.output.sources}")
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        vector_store: VectorStorePort,
        llm: LLMPort,
        config: Optional[RAGChainConfig] = None,
        prompt_template: Optional[PromptTemplatePort] = None,
        keyword_search: Optional[KeywordSearchPort] = None
    ):
        self._config = config or RAGChainConfig()
        super().__init__("rag", self._config)

        self.embedder = embedder
        self.vector_store = vector_store
        self.llm = llm
        self.prompt_template = prompt_template
        self.keyword_search = keyword_search

        # Build sub-chains
        self._retrieval_chain = self._build_retrieval_chain()
        self._generation_chain = self._build_generation_chain()

        # Build steps
        self._steps = self._build_steps()

    def _build_retrieval_chain(self) -> RetrievalChain:
        """Build retrieval sub-chain"""
        retrieval_config = RetrievalChainConfig(
            top_k=self._config.retrieval_top_k,
            use_hybrid=self._config.use_hybrid,
            vector_weight=self._config.vector_weight,
            keyword_weight=self._config.keyword_weight,
            min_score=self._config.min_score
        )
        return RetrievalChain(
            self.embedder,
            self.vector_store,
            retrieval_config,
            self.keyword_search
        )

    def _build_generation_chain(self) -> GenerationChain:
        """Build generation sub-chain"""
        generation_config = GenerationChainConfig(
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            language=self._config.language
        )
        return GenerationChain(
            self.llm,
            self.prompt_template,
            generation_config
        )

    def _build_steps(self) -> List[ChainStep]:
        """Build main chain steps"""
        return [
            PrepareRetrievalStep(),
            # Retrieval and generation are handled in run()
            BuildContextStep(self._config),
            PrepareGenerationStep(self._config),
            FormatRAGOutputStep(self._config)
        ]

    def get_steps(self) -> List[ChainStep]:
        return self._steps

    async def run(
        self,
        input: RAGInput,
        context: Optional[Dict[str, Any]] = None
    ) -> ChainResult[RAGOutput]:
        """Execute the RAG pipeline"""
        context = context or {}
        context["rag_input"] = input

        result = ChainResult[RAGOutput](status="success")

        try:
            # Step 1: Prepare retrieval input
            retrieval_input = RetrievalInput(
                query=input.question,
                user_id=input.user_id,
                session_id=input.session_id,
                filters=input.filters
            )

            # Step 2: Run retrieval chain
            retrieval_result = await self._retrieval_chain.run(
                retrieval_input, context
            )

            if not retrieval_result.is_success:
                result.status = "failed"
                result.error = f"Retrieval failed: {retrieval_result.error}"
                return result

            # Add retrieval steps to result
            for step in retrieval_result.steps:
                result.add_step(step)

            # Store documents in context
            context["documents"] = retrieval_result.output.documents

            # Step 3: Build context
            build_step = BuildContextStep(self._config)
            context_data = await build_step.execute(
                retrieval_result.output, context
            )

            # Step 4: Prepare generation input
            generation_input = GenerationInput(
                question=input.question,
                context=context_data["context"],
                system_prompt=input.system_prompt
            )

            # Step 5: Run generation chain
            generation_result = await self._generation_chain.run(
                generation_input, context
            )

            if not generation_result.is_success:
                result.status = "failed"
                result.error = f"Generation failed: {generation_result.error}"
                return result

            # Add generation steps to result
            for step in generation_result.steps:
                result.add_step(step)

            # Step 6: Format output
            format_step = FormatRAGOutputStep(self._config)
            final_output = await format_step.execute(
                generation_result.output, context
            )

            result.output = final_output
            result.status = "success"

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.error(f"RAG chain failed: {e}")

        return result

    def with_filters(self, filters: Dict[str, Any]) -> "RAGChain":
        """Create new chain with additional filters"""
        new_config = RAGChainConfig(
            retrieval_top_k=self._config.retrieval_top_k,
            use_hybrid=self._config.use_hybrid,
            vector_weight=self._config.vector_weight,
            keyword_weight=self._config.keyword_weight,
            min_score=self._config.min_score,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            max_context_length=self._config.max_context_length,
            include_sources=self._config.include_sources,
            language=self._config.language
        )

        chain = RAGChain(
            self.embedder,
            self.vector_store,
            self.llm,
            new_config,
            self.prompt_template,
            self.keyword_search
        )
        chain._retrieval_chain = self._retrieval_chain.with_filters(filters)
        return chain

    def with_prompt(
        self,
        prompt_template: PromptTemplatePort
    ) -> "RAGChain":
        """Create new chain with different prompt template"""
        return RAGChain(
            self.embedder,
            self.vector_store,
            self.llm,
            self._config,
            prompt_template,
            self.keyword_search
        )


# ==================== Factory ====================

class RAGChainFactory:
    """
    Factory for creating RAG chains with different configurations.

    Example:
        factory = RAGChainFactory(embedder, vector_store, llm)

        # Create standard RAG chain
        rag_chain = factory.create_standard()

        # Create hybrid RAG chain
        hybrid_chain = factory.create_hybrid(keyword_search)

        # Create analysis chain
        analysis_chain = factory.create_for_analysis()
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
    ) -> RAGChain:
        """Create standard RAG chain"""
        return RAGChain(
            self.embedder,
            self.vector_store,
            self.llm,
            prompt_template=prompt_template
        )

    def create_hybrid(
        self,
        keyword_search: KeywordSearchPort,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGChain:
        """Create hybrid RAG chain"""
        config = RAGChainConfig(
            use_hybrid=True,
            vector_weight=0.7,
            keyword_weight=0.3
        )
        return RAGChain(
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
    ) -> RAGChain:
        """Create RAG chain optimized for analysis"""
        config = RAGChainConfig(
            retrieval_top_k=15,
            temperature=0.5,
            max_tokens=4096,
            max_context_length=12000
        )
        return RAGChain(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template
        )

    def create_for_code(
        self,
        prompt_template: Optional[PromptTemplatePort] = None
    ) -> RAGChain:
        """Create RAG chain optimized for code"""
        config = RAGChainConfig(
            retrieval_top_k=20,
            temperature=0.3,
            max_tokens=4096
        )
        return RAGChain(
            self.embedder,
            self.vector_store,
            self.llm,
            config,
            prompt_template
        )
