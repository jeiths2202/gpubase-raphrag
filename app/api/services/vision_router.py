"""
Vision-Aware Router

Intelligent routing service that decides between Vision LLM and Text LLM
based on query analysis, document characteristics, and retrieved context.

Three-level routing:
1. Document-Time: When document is uploaded
2. Query-Time: When query is received
3. Context-Time: After documents are retrieved
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.api.models.vision import (
    DocumentVisualProfile,
    ProcessedImage,
    RoutingDecision,
    VisualQuerySignals,
)
from app.api.services.document_analyzer import DocumentAnalyzer
from app.api.services.query_visual_detector import QueryVisualSignalDetector

logger = logging.getLogger(__name__)


@dataclass
class DocumentContext:
    """Context about a document for routing decisions"""
    document_id: str
    visual_profile: Optional[DocumentVisualProfile] = None
    has_images: bool = False
    image_count: int = 0
    relevance_score: float = 0.0


@dataclass
class RoutingContext:
    """Complete context for making routing decision"""
    query: str
    language: str = "auto"
    query_signals: Optional[VisualQuerySignals] = None
    documents: List[DocumentContext] = None
    visual_doc_count: int = 0
    visual_doc_ratio: float = 0.0
    force_vision: bool = False
    force_text: bool = False


class VisionAwareRouter:
    """
    Vision-aware routing decision engine.

    Makes intelligent decisions about which LLM to use:
    - Vision LLM: GPT-4V, Claude 3 Vision
    - Text LLM: Nemotron, GPT-4
    - Code LLM: Mistral NeMo, specialized code models

    Routing is based on:
    1. Query analysis (visual signals in the question)
    2. Document profiles (visual complexity of source documents)
    3. Retrieved context (visual content in relevant documents)

    Usage:
        router = VisionAwareRouter()

        # Query-time routing
        decision = await router.route(
            query="이 차트의 트렌드를 분석해주세요",
            retrieved_docs=[doc1, doc2, doc3],
        )

        if decision.selected_llm == "vision":
            # Use Vision LLM
            ...
    """

    # Routing thresholds
    VISUAL_QUERY_CONFIDENCE_THRESHOLD = 0.3
    VISUAL_DOC_RATIO_THRESHOLD = 0.3
    VISUAL_COMPLEXITY_THRESHOLD = 0.4

    # LLM type weights for final decision
    QUERY_WEIGHT = 0.5
    DOCUMENT_WEIGHT = 0.3
    CONTEXT_WEIGHT = 0.2

    def __init__(
        self,
        query_detector: Optional[QueryVisualSignalDetector] = None,
        document_analyzer: Optional[DocumentAnalyzer] = None,
        visual_query_threshold: float = 0.3,
        visual_doc_ratio_threshold: float = 0.3,
    ):
        """
        Initialize router.

        Args:
            query_detector: Query visual signal detector
            document_analyzer: Document visual analyzer
            visual_query_threshold: Confidence threshold for visual queries
            visual_doc_ratio_threshold: Ratio threshold for visual documents
        """
        self.query_detector = query_detector or QueryVisualSignalDetector()
        self.document_analyzer = document_analyzer or DocumentAnalyzer()
        self.visual_query_threshold = visual_query_threshold
        self.visual_doc_ratio_threshold = visual_doc_ratio_threshold

    async def route(
        self,
        query: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        document_profiles: Optional[Dict[str, DocumentVisualProfile]] = None,
        language: str = "auto",
        force_vision: bool = False,
        force_text: bool = False,
    ) -> RoutingDecision:
        """
        Make routing decision for a query.

        This is the main entry point for routing decisions.

        Args:
            query: User query text
            retrieved_docs: List of retrieved documents with metadata
            document_profiles: Pre-computed visual profiles for documents
            language: Language hint for query analysis
            force_vision: Force use of Vision LLM
            force_text: Force use of Text LLM

        Returns:
            RoutingDecision with selected LLM and reasoning
        """
        # Handle forced routing
        if force_vision:
            return RoutingDecision(
                selected_llm="vision",
                reasoning="Forced Vision LLM by request",
                confidence=1.0,
                query_type="hybrid",
            )

        if force_text:
            return RoutingDecision(
                selected_llm="text",
                reasoning="Forced Text LLM by request",
                confidence=1.0,
                query_type="vector",
            )

        # Step 1: Analyze query for visual signals
        query_signals = self.query_detector.detect(query, language)

        # Check for code query
        if query_signals.suggested_model == "code":
            return RoutingDecision(
                selected_llm="code",
                reasoning="Query requests code generation",
                confidence=query_signals.confidence,
                query_type="code",
            )

        # Step 2: Analyze document context
        doc_contexts = self._build_document_contexts(
            retrieved_docs or [],
            document_profiles or {}
        )

        visual_doc_count = sum(
            1 for ctx in doc_contexts
            if ctx.visual_profile and ctx.visual_profile.requires_vision_llm
        )
        visual_doc_ratio = (
            visual_doc_count / len(doc_contexts)
            if doc_contexts else 0.0
        )

        # Step 3: Build complete routing context
        routing_context = RoutingContext(
            query=query,
            language=language,
            query_signals=query_signals,
            documents=doc_contexts,
            visual_doc_count=visual_doc_count,
            visual_doc_ratio=visual_doc_ratio,
        )

        # Step 4: Make routing decision
        return self._make_decision(routing_context)

    async def route_for_document(
        self,
        visual_profile: DocumentVisualProfile,
    ) -> RoutingDecision:
        """
        Make routing decision for document processing.

        Called during document ingestion to determine processing mode.

        Args:
            visual_profile: Document's visual profile

        Returns:
            RoutingDecision for document processing
        """
        if visual_profile.requires_vision_llm:
            reasoning = self._build_document_reasoning(visual_profile)
            return RoutingDecision(
                selected_llm="vision",
                reasoning=reasoning,
                confidence=min(0.9, 0.5 + visual_profile.visual_complexity_score),
                query_type="multimodal",
            )

        return RoutingDecision(
            selected_llm="text",
            reasoning="Document is primarily text-based",
            confidence=0.9,
            query_type="vector",
        )

    def analyze_query(
        self,
        query: str,
        language: str = "auto",
    ) -> VisualQuerySignals:
        """
        Analyze query for visual signals.

        Convenience method for query-only analysis.

        Args:
            query: Query text
            language: Language hint

        Returns:
            VisualQuerySignals
        """
        return self.query_detector.detect(query, language)

    def _build_document_contexts(
        self,
        retrieved_docs: List[Dict[str, Any]],
        profiles: Dict[str, DocumentVisualProfile],
    ) -> List[DocumentContext]:
        """Build document contexts from retrieved documents."""
        contexts = []

        for doc in retrieved_docs:
            doc_id = doc.get("id") or doc.get("document_id", "")
            profile = profiles.get(doc_id)

            contexts.append(DocumentContext(
                document_id=doc_id,
                visual_profile=profile,
                has_images=profile.image_count > 0 if profile else False,
                image_count=profile.image_count if profile else 0,
                relevance_score=doc.get("score", 0.0),
            ))

        return contexts

    def _make_decision(
        self,
        context: RoutingContext,
    ) -> RoutingDecision:
        """
        Make final routing decision based on all context.

        Decision matrix:
        | Query Signal | Doc Context    | Selected LLM |
        |--------------|----------------|--------------|
        | Visual       | ANY            | Vision       |
        | Code         | ANY            | Code         |
        | Text         | Visual >= 0.3  | Vision       |
        | Text         | Visual < 0.3   | Text         |
        """
        query_signals = context.query_signals
        reasons = []

        # Calculate weighted score
        query_visual_score = 0.0
        doc_visual_score = 0.0

        # Query analysis contribution
        if query_signals:
            if query_signals.is_visual_query:
                query_visual_score = query_signals.confidence
                reasons.append(
                    f"Query contains visual signals ({', '.join(query_signals.visual_aspects[:3])})"
                )

        # Document context contribution
        if context.visual_doc_ratio >= self.visual_doc_ratio_threshold:
            doc_visual_score = context.visual_doc_ratio
            reasons.append(
                f"Retrieved docs are {context.visual_doc_ratio:.0%} visual"
            )

        # Weighted decision
        total_visual_score = (
            query_visual_score * self.QUERY_WEIGHT +
            doc_visual_score * self.DOCUMENT_WEIGHT
        )

        # Determine LLM
        if total_visual_score >= 0.25:
            selected_llm = "vision"
            query_type = "hybrid"
        else:
            selected_llm = "text"
            query_type = "vector"
            reasons = ["Standard text-based query"] if not reasons else reasons

        # Calculate confidence
        if selected_llm == "vision":
            confidence = min(0.95, 0.5 + total_visual_score)
        else:
            confidence = max(0.7, 1.0 - total_visual_score)

        return RoutingDecision(
            selected_llm=selected_llm,
            reasoning="; ".join(reasons) if reasons else "Default routing",
            confidence=confidence,
            query_type=query_type,
        )

    def _build_document_reasoning(
        self,
        profile: DocumentVisualProfile,
    ) -> str:
        """Build reasoning string for document routing."""
        reasons = []

        if profile.is_pure_image:
            reasons.append("Pure image document")
        if profile.has_charts:
            reasons.append("Contains charts/graphs")
        if profile.has_diagrams:
            reasons.append("Contains diagrams")
        if profile.requires_ocr:
            reasons.append("Requires OCR")
        if profile.image_area_ratio >= 0.3:
            reasons.append(f"High image ratio ({profile.image_area_ratio:.0%})")
        if profile.visual_complexity_score >= 0.4:
            reasons.append(f"High visual complexity ({profile.visual_complexity_score:.2f})")

        return "; ".join(reasons) if reasons else "Visual content detected"

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics and configuration."""
        return {
            "thresholds": {
                "visual_query_confidence": self.visual_query_threshold,
                "visual_doc_ratio": self.visual_doc_ratio_threshold,
                "visual_complexity": self.VISUAL_COMPLEXITY_THRESHOLD,
            },
            "weights": {
                "query": self.QUERY_WEIGHT,
                "document": self.DOCUMENT_WEIGHT,
                "context": self.CONTEXT_WEIGHT,
            },
            "supported_languages": self.query_detector.get_supported_languages(),
        }

    def explain_routing(
        self,
        query: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        document_profiles: Optional[Dict[str, DocumentVisualProfile]] = None,
        language: str = "auto",
    ) -> Dict[str, Any]:
        """
        Get detailed explanation of routing decision.

        Useful for debugging and understanding routing logic.

        Args:
            query: Query text
            retrieved_docs: Retrieved documents
            document_profiles: Document profiles
            language: Language hint

        Returns:
            Detailed explanation dict
        """
        # Analyze query
        query_signals = self.query_detector.detect(query, language)
        query_explanation = self.query_detector.explain_detection(query, language)

        # Build document contexts
        doc_contexts = self._build_document_contexts(
            retrieved_docs or [],
            document_profiles or {}
        )

        visual_docs = [
            {
                "id": ctx.document_id,
                "has_images": ctx.has_images,
                "image_count": ctx.image_count,
                "requires_vision": (
                    ctx.visual_profile.requires_vision_llm
                    if ctx.visual_profile else False
                ),
            }
            for ctx in doc_contexts
        ]

        visual_doc_count = sum(1 for d in visual_docs if d["requires_vision"])
        visual_doc_ratio = visual_doc_count / len(visual_docs) if visual_docs else 0.0

        # Build routing context and make decision
        routing_context = RoutingContext(
            query=query,
            language=language,
            query_signals=query_signals,
            documents=doc_contexts,
            visual_doc_count=visual_doc_count,
            visual_doc_ratio=visual_doc_ratio,
        )

        decision = self._make_decision(routing_context)

        return {
            "query": query,
            "detected_language": query_signals.language,
            "query_analysis": query_explanation,
            "document_analysis": {
                "total_docs": len(visual_docs),
                "visual_docs": visual_doc_count,
                "visual_ratio": visual_doc_ratio,
                "documents": visual_docs,
            },
            "routing_decision": {
                "selected_llm": decision.selected_llm,
                "reasoning": decision.reasoning,
                "confidence": decision.confidence,
                "query_type": decision.query_type,
            },
            "thresholds_used": self.get_routing_stats()["thresholds"],
        }


class VisionRouterFactory:
    """Factory for creating configured VisionAwareRouter instances."""

    @staticmethod
    def create_default() -> VisionAwareRouter:
        """Create router with default settings."""
        return VisionAwareRouter()

    @staticmethod
    def create_aggressive() -> VisionAwareRouter:
        """Create router that favors Vision LLM (lower thresholds)."""
        return VisionAwareRouter(
            visual_query_threshold=0.2,
            visual_doc_ratio_threshold=0.2,
        )

    @staticmethod
    def create_conservative() -> VisionAwareRouter:
        """Create router that favors Text LLM (higher thresholds)."""
        return VisionAwareRouter(
            visual_query_threshold=0.5,
            visual_doc_ratio_threshold=0.5,
        )

    @staticmethod
    def create_from_settings(settings: Dict[str, Any]) -> VisionAwareRouter:
        """Create router from settings dict."""
        return VisionAwareRouter(
            visual_query_threshold=settings.get(
                "visual_query_threshold", 0.3
            ),
            visual_doc_ratio_threshold=settings.get(
                "visual_doc_ratio_threshold", 0.3
            ),
        )
