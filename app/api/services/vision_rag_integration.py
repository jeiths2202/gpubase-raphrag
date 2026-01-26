"""
Vision-RAG Integration Service

Integrates Vision LLM capabilities with the existing RAG service.
Provides unified query handling that automatically routes between
Vision LLM and Text LLM based on content analysis.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.api.models.vision import (
    DocumentVisualProfile,
    ExtractedVisualInfo,
    UnifiedQueryResponse,
)
from app.api.services.enhanced_query_router import (
    EnhancedQueryRouter,
    EnhancedRoutingResult,
)
from app.api.services.response_normalizer import (
    NormalizationConfig,
    ResponseNormalizer,
)
from app.api.services.vision_cache import VisionCache, get_vision_cache

logger = logging.getLogger(__name__)


@dataclass
class VisionRAGConfig:
    """Configuration for Vision-RAG integration"""
    enable_vision: bool = True
    vision_confidence_threshold: float = 0.3
    max_images_per_query: int = 5
    parallel_processing: bool = True
    cache_visual_profiles: bool = True
    fallback_to_text: bool = True
    normalize_responses: bool = True


@dataclass
class IntegratedQueryResult:
    """Result from integrated Vision-RAG query"""
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    language: str

    # Vision-specific
    used_vision: bool = False
    visual_info: Optional[ExtractedVisualInfo] = None
    visual_sources: List[str] = field(default_factory=list)

    # Routing info
    routing_decision: Optional[Dict[str, Any]] = None

    # Original RAG data
    query_analysis: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "confidence": self.confidence,
            "model_used": self.model_used,
            "language": self.language,
            "used_vision": self.used_vision,
            "visual_info": self.visual_info.to_dict() if self.visual_info else None,
            "visual_sources": self.visual_sources,
            "routing_decision": self.routing_decision,
            "query_analysis": self.query_analysis,
        }


class VisionRAGIntegration:
    """
    Integrates Vision LLM with existing RAG service.

    Key features:
    1. Automatic routing between Vision and Text LLM
    2. Visual document analysis and caching
    3. Combined context from text and visual sources
    4. Response normalization across LLM types

    Usage:
        integration = VisionRAGIntegration()

        # Query with automatic routing
        result = await integration.query(
            question="이 차트의 트렌드를 분석해주세요",
            session_id="session-123",
            user_id="user-456"
        )

        if result.used_vision:
            print("Visual analysis:", result.visual_info)
    """

    def __init__(
        self,
        config: Optional[VisionRAGConfig] = None,
        enhanced_router: Optional[EnhancedQueryRouter] = None,
        vision_cache: Optional[VisionCache] = None,
        normalizer: Optional[ResponseNormalizer] = None,
    ):
        """
        Initialize Vision-RAG integration.

        Args:
            config: Integration configuration
            enhanced_router: Query router with vision support
            vision_cache: Cache for visual profiles
            normalizer: Response normalizer
        """
        self.config = config or VisionRAGConfig()
        self.router = enhanced_router or EnhancedQueryRouter()
        self.cache = vision_cache or get_vision_cache()
        self.normalizer = normalizer or ResponseNormalizer()

        # Lazy-loaded components
        self._rag_service = None
        self._vision_orchestrator = None

    @property
    def rag_service(self):
        """Lazy load RAG service"""
        if self._rag_service is None:
            from app.api.services.rag_service import get_rag_service
            self._rag_service = get_rag_service()
        return self._rag_service

    @property
    def vision_orchestrator(self):
        """Lazy load Vision orchestrator"""
        if self._vision_orchestrator is None:
            from app.api.pipeline.vision_orchestrator import (
                get_vision_pipeline_orchestrator,
            )
            self._vision_orchestrator = get_vision_pipeline_orchestrator()
        return self._vision_orchestrator

    async def query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        session_id: Optional[str] = None,
        use_session_docs: bool = True,
        user_id: Optional[str] = None,
        use_external_resources: bool = True,
        force_vision: bool = False,
        force_text: bool = False,
        document_ids: Optional[List[str]] = None,
    ) -> IntegratedQueryResult:
        """
        Execute integrated Vision-RAG query.

        Automatically routes between Vision LLM and Text LLM based on:
        1. Query visual signals (chart, graph, diagram keywords)
        2. Document visual profiles (if available)
        3. Configuration thresholds

        Args:
            question: User's question
            strategy: RAG strategy (auto, vector, graph, hybrid, code)
            language: Response language (auto, ko, ja, en)
            top_k: Number of results to retrieve
            conversation_id: Conversation session ID
            conversation_history: Previous Q&A pairs
            session_id: Session ID for uploaded documents
            use_session_docs: Use session documents
            user_id: User ID for external resources
            use_external_resources: Use external resources
            force_vision: Force Vision LLM
            force_text: Force Text LLM
            document_ids: Specific documents to query

        Returns:
            IntegratedQueryResult with answer and metadata
        """
        # Skip vision if disabled
        if not self.config.enable_vision:
            return await self._text_only_query(
                question=question,
                strategy=strategy,
                language=language,
                top_k=top_k,
                conversation_id=conversation_id,
                conversation_history=conversation_history,
                session_id=session_id,
                use_session_docs=use_session_docs,
                user_id=user_id,
                use_external_resources=use_external_resources,
            )

        # Step 1: Get document visual profiles (if available)
        document_profiles = await self._get_document_profiles(document_ids)

        # Step 2: Route query
        routing_result = await self.router.route(
            query=question,
            document_profiles=document_profiles,
            language=language,
            force_vision=force_vision,
            force_text=force_text,
        )

        logger.info(
            f"Routing decision: {routing_result.selected_llm} "
            f"(confidence: {routing_result.llm_confidence:.2f})"
        )

        # Step 3: Execute appropriate query path
        if routing_result.selected_llm == "vision":
            return await self._vision_query(
                question=question,
                routing_result=routing_result,
                document_ids=document_ids,
                session_id=session_id,
                user_id=user_id,
                language=language,
                top_k=top_k,
            )
        else:
            return await self._text_query_with_routing(
                question=question,
                routing_result=routing_result,
                strategy=strategy,
                language=language,
                top_k=top_k,
                conversation_id=conversation_id,
                conversation_history=conversation_history,
                session_id=session_id,
                use_session_docs=use_session_docs,
                user_id=user_id,
                use_external_resources=use_external_resources,
            )

    async def _get_document_profiles(
        self,
        document_ids: Optional[List[str]],
    ) -> Dict[str, DocumentVisualProfile]:
        """Get cached or compute visual profiles for documents."""
        if not document_ids:
            return {}

        profiles = {}

        for doc_id in document_ids:
            # Check cache first
            cached = self.cache.get_document_profile(doc_id)
            if cached:
                profiles[doc_id] = cached
            else:
                # Compute profile if needed (async)
                try:
                    profile = await self._compute_document_profile(doc_id)
                    if profile:
                        profiles[doc_id] = profile
                        if self.config.cache_visual_profiles:
                            self.cache.set_document_profile(doc_id, profile)
                except Exception as e:
                    logger.warning(f"Failed to compute profile for {doc_id}: {e}")

        return profiles

    async def _compute_document_profile(
        self,
        document_id: str,
    ) -> Optional[DocumentVisualProfile]:
        """Compute visual profile for a document."""
        try:
            from app.api.services.document_analyzer import DocumentAnalyzer

            analyzer = DocumentAnalyzer()

            # This would need document content access
            # For now, return None (profile computed on upload)
            return None

        except Exception as e:
            logger.error(f"Profile computation failed: {e}")
            return None

    async def _vision_query(
        self,
        question: str,
        routing_result: EnhancedRoutingResult,
        document_ids: Optional[List[str]],
        session_id: Optional[str],
        user_id: Optional[str],
        language: str,
        top_k: int,
    ) -> IntegratedQueryResult:
        """Execute query using Vision LLM."""
        try:
            # Use Vision orchestrator
            vision_result = await self.vision_orchestrator.process_query(
                query=question,
                document_ids=document_ids,
                language=language,
            )

            # Also get text context for hybrid response
            text_context = await self._get_text_context(
                question=question,
                session_id=session_id,
                user_id=user_id,
                top_k=top_k // 2,  # Fewer text results when using vision
            )

            # Combine sources
            combined_sources = self._merge_sources(
                vision_sources=vision_result.sources,
                text_sources=text_context.get("sources", []),
            )

            return IntegratedQueryResult(
                answer=vision_result.answer,
                sources=combined_sources,
                confidence=vision_result.confidence,
                model_used=vision_result.model_used,
                language=vision_result.language,
                used_vision=True,
                visual_info=vision_result.visual_info,
                visual_sources=vision_result.sources,
                routing_decision=routing_result.to_dict(),
                query_analysis={
                    "is_visual_query": routing_result.is_visual_query,
                    "visual_aspects": routing_result.visual_aspects,
                    "visual_doc_ratio": routing_result.visual_doc_ratio,
                },
            )

        except Exception as e:
            logger.error(f"Vision query failed: {e}")

            # Fallback to text if enabled
            if self.config.fallback_to_text:
                logger.info("Falling back to text query")
                return await self._text_only_query(
                    question=question,
                    strategy="auto",
                    language=language,
                    top_k=top_k,
                    session_id=session_id,
                    user_id=user_id,
                )

            raise

    async def _text_query_with_routing(
        self,
        question: str,
        routing_result: EnhancedRoutingResult,
        strategy: str,
        language: str,
        top_k: int,
        conversation_id: Optional[str],
        conversation_history: Optional[List[Dict]],
        session_id: Optional[str],
        use_session_docs: bool,
        user_id: Optional[str],
        use_external_resources: bool,
    ) -> IntegratedQueryResult:
        """Execute text query with routing information."""
        # Use existing RAG service
        rag_result = await self.rag_service.query(
            question=question,
            strategy=routing_result.query_type.value if hasattr(routing_result.query_type, 'value') else strategy,
            language=language,
            top_k=top_k,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            session_id=session_id,
            use_session_docs=use_session_docs,
            user_id=user_id,
            use_external_resources=use_external_resources,
        )

        return IntegratedQueryResult(
            answer=rag_result.get("answer", ""),
            sources=rag_result.get("sources", []),
            confidence=rag_result.get("confidence", 0.85),
            model_used="text/nemotron",  # Default text model
            language=rag_result.get("language", language),
            used_vision=False,
            visual_info=None,
            routing_decision=routing_result.to_dict(),
            query_analysis=rag_result.get("query_analysis"),
        )

    async def _text_only_query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        session_id: Optional[str] = None,
        use_session_docs: bool = True,
        user_id: Optional[str] = None,
        use_external_resources: bool = True,
    ) -> IntegratedQueryResult:
        """Execute text-only query (no vision routing)."""
        rag_result = await self.rag_service.query(
            question=question,
            strategy=strategy,
            language=language,
            top_k=top_k,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            session_id=session_id,
            use_session_docs=use_session_docs,
            user_id=user_id,
            use_external_resources=use_external_resources,
        )

        return IntegratedQueryResult(
            answer=rag_result.get("answer", ""),
            sources=rag_result.get("sources", []),
            confidence=rag_result.get("confidence", 0.85),
            model_used="text/nemotron",
            language=rag_result.get("language", language),
            used_vision=False,
            query_analysis=rag_result.get("query_analysis"),
        )

    async def _get_text_context(
        self,
        question: str,
        session_id: Optional[str],
        user_id: Optional[str],
        top_k: int,
    ) -> Dict[str, Any]:
        """Get text context for hybrid vision-text response."""
        try:
            return await self.rag_service.query(
                question=question,
                strategy="vector",
                top_k=top_k,
                session_id=session_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Text context retrieval failed: {e}")
            return {"sources": []}

    def _merge_sources(
        self,
        vision_sources: List[str],
        text_sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge vision and text sources."""
        merged = []
        seen_ids = set()

        # Add vision sources first
        for vs in vision_sources:
            merged.append({
                "doc_id": vs,
                "source_type": "vision",
                "is_visual_source": True,
            })
            seen_ids.add(vs)

        # Add text sources
        for ts in text_sources:
            doc_id = ts.get("doc_id", "")
            if doc_id not in seen_ids:
                ts["is_visual_source"] = False
                merged.append(ts)
                seen_ids.add(doc_id)

        return merged

    async def analyze_document(
        self,
        document_id: str,
        content: Optional[bytes] = None,
        filename: Optional[str] = None,
    ) -> DocumentVisualProfile:
        """
        Analyze a document for visual content.

        Called during document upload to cache visual profile.

        Args:
            document_id: Document identifier
            content: Document content bytes
            filename: Original filename

        Returns:
            DocumentVisualProfile for routing decisions
        """
        from app.api.services.document_analyzer import DocumentAnalyzer

        analyzer = DocumentAnalyzer()

        # Analyze document
        profile = await analyzer.analyze_document(
            document_id=document_id,
            content=content,
            filename=filename,
        )

        # Cache the profile
        if self.config.cache_visual_profiles:
            self.cache.set_document_profile(document_id, profile)

        return profile

    def get_routing_explanation(
        self,
        question: str,
        language: str = "auto",
    ) -> Dict[str, Any]:
        """
        Get explanation of how a query would be routed.

        Useful for debugging and transparency.
        """
        return self.router.explain_routing(
            query=question,
            language=language,
        )

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "enable_vision": self.config.enable_vision,
            "vision_confidence_threshold": self.config.vision_confidence_threshold,
            "max_images_per_query": self.config.max_images_per_query,
            "parallel_processing": self.config.parallel_processing,
            "cache_visual_profiles": self.config.cache_visual_profiles,
            "fallback_to_text": self.config.fallback_to_text,
            "routing_config": self.router.get_routing_config(),
        }


# Singleton instance
_integration: Optional[VisionRAGIntegration] = None


def get_vision_rag_integration() -> VisionRAGIntegration:
    """Get global Vision-RAG integration instance."""
    global _integration
    if _integration is None:
        _integration = VisionRAGIntegration()
    return _integration


def create_vision_rag_integration(
    config: Optional[VisionRAGConfig] = None,
) -> VisionRAGIntegration:
    """Create new Vision-RAG integration with custom config."""
    return VisionRAGIntegration(config=config)
