"""
Enhanced Query Router

Extends the existing QueryRouter with Vision-aware routing capabilities.
Combines traditional RAG strategy selection with Vision LLM routing.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from app.api.models.vision import (
    DocumentVisualProfile,
    RoutingDecision,
    VisualQuerySignals,
)
from app.api.services.query_visual_detector import QueryVisualSignalDetector
from app.api.services.vision_router import VisionAwareRouter

logger = logging.getLogger(__name__)


class EnhancedQueryType(str, Enum):
    """Extended query types including vision"""
    VECTOR = "vector"      # Semantic similarity search
    GRAPH = "graph"        # Relationship/entity traversal
    HYBRID = "hybrid"      # Both approaches combined
    CODE = "code"          # Code generation/analysis
    VISION = "vision"      # Vision LLM for visual content


@dataclass
class EnhancedRoutingResult:
    """Complete routing result with strategy and LLM selection"""
    # RAG Strategy
    query_type: EnhancedQueryType
    strategy_confidence: float

    # LLM Selection
    selected_llm: Literal["vision", "text", "code"]
    llm_reasoning: str
    llm_confidence: float

    # Visual signals
    is_visual_query: bool
    visual_aspects: List[str]

    # Additional context
    language: str = "auto"
    visual_doc_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_type": self.query_type.value,
            "strategy_confidence": self.strategy_confidence,
            "selected_llm": self.selected_llm,
            "llm_reasoning": self.llm_reasoning,
            "llm_confidence": self.llm_confidence,
            "is_visual_query": self.is_visual_query,
            "visual_aspects": self.visual_aspects,
            "language": self.language,
            "visual_doc_ratio": self.visual_doc_ratio,
        }


class EnhancedQueryRouter:
    """
    Enhanced Query Router with Vision support.

    Combines:
    1. Traditional RAG strategy routing (VECTOR/GRAPH/HYBRID/CODE)
    2. Vision LLM routing based on visual signals

    Usage:
        router = EnhancedQueryRouter()
        result = await router.route(
            query="이 차트의 트렌드를 분석해주세요",
            retrieved_docs=[doc1, doc2],
            document_profiles={"doc1": profile1}
        )

        # Use result.selected_llm for LLM selection
        # Use result.query_type for RAG strategy
    """

    def __init__(
        self,
        base_router: Optional[Any] = None,  # QueryRouter from app.src
        vision_router: Optional[VisionAwareRouter] = None,
        enable_vision_routing: bool = True,
    ):
        """
        Initialize enhanced router.

        Args:
            base_router: Existing QueryRouter instance (optional)
            vision_router: VisionAwareRouter instance (optional)
            enable_vision_routing: Enable/disable vision routing
        """
        self._base_router = base_router
        self.vision_router = vision_router or VisionAwareRouter()
        self.enable_vision_routing = enable_vision_routing

    @property
    def base_router(self):
        """Lazy load base router"""
        if self._base_router is None:
            try:
                import sys
                from pathlib import Path

                # Add app/src to path if needed
                src_path = Path(__file__).parent.parent.parent / "src"
                if str(src_path) not in sys.path:
                    sys.path.insert(0, str(src_path))

                from query_router import QueryRouter
                self._base_router = QueryRouter()
            except ImportError as e:
                logger.warning(f"Could not import base QueryRouter: {e}")
                self._base_router = None

        return self._base_router

    async def route(
        self,
        query: str,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        document_profiles: Optional[Dict[str, DocumentVisualProfile]] = None,
        language: str = "auto",
        force_vision: bool = False,
        force_text: bool = False,
    ) -> EnhancedRoutingResult:
        """
        Route query to appropriate strategy and LLM.

        Args:
            query: User query text
            retrieved_docs: Retrieved documents with metadata
            document_profiles: Visual profiles for documents
            language: Language hint
            force_vision: Force Vision LLM
            force_text: Force Text LLM

        Returns:
            EnhancedRoutingResult with complete routing decision
        """
        # Step 1: Get Vision routing decision
        vision_decision = await self.vision_router.route(
            query=query,
            retrieved_docs=retrieved_docs,
            document_profiles=document_profiles,
            language=language,
            force_vision=force_vision,
            force_text=force_text,
        )

        # Step 2: Get traditional RAG strategy (if base router available)
        base_query_type = EnhancedQueryType.VECTOR
        strategy_confidence = 0.7

        if self.base_router:
            try:
                # Use base router's classify method
                base_result = self.base_router.classify(query)
                base_type = base_result.get("type", "vector")
                strategy_confidence = base_result.get("confidence", 0.7)

                # Map to EnhancedQueryType
                type_map = {
                    "vector": EnhancedQueryType.VECTOR,
                    "graph": EnhancedQueryType.GRAPH,
                    "hybrid": EnhancedQueryType.HYBRID,
                    "code": EnhancedQueryType.CODE,
                }
                base_query_type = type_map.get(base_type, EnhancedQueryType.VECTOR)

            except Exception as e:
                logger.warning(f"Base router classification failed: {e}")

        # Step 3: Determine final query type
        # If vision is selected, we may still use HYBRID for retrieval
        if vision_decision.selected_llm == "vision":
            query_type = EnhancedQueryType.HYBRID  # Use hybrid retrieval for visual queries
        elif vision_decision.selected_llm == "code":
            query_type = EnhancedQueryType.CODE
        else:
            query_type = base_query_type

        # Step 4: Get visual signals for response
        query_signals = self.vision_router.analyze_query(query, language)

        # Calculate visual doc ratio
        visual_doc_ratio = 0.0
        if retrieved_docs and document_profiles:
            visual_count = sum(
                1 for doc in retrieved_docs
                if doc.get("id") in document_profiles and
                document_profiles[doc.get("id")].requires_vision_llm
            )
            visual_doc_ratio = visual_count / len(retrieved_docs)

        return EnhancedRoutingResult(
            query_type=query_type,
            strategy_confidence=strategy_confidence,
            selected_llm=vision_decision.selected_llm,
            llm_reasoning=vision_decision.reasoning,
            llm_confidence=vision_decision.confidence,
            is_visual_query=query_signals.is_visual_query,
            visual_aspects=query_signals.visual_aspects,
            language=query_signals.language,
            visual_doc_ratio=visual_doc_ratio,
        )

    def analyze_query(
        self,
        query: str,
        language: str = "auto",
    ) -> VisualQuerySignals:
        """
        Analyze query for visual signals.

        Quick method for query-only analysis without document context.
        """
        return self.vision_router.analyze_query(query, language)

    def classify_strategy(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """
        Classify query using base router's strategy classification.

        Returns traditional VECTOR/GRAPH/HYBRID/CODE classification.
        """
        if self.base_router:
            try:
                return self.base_router.classify(query)
            except Exception as e:
                logger.warning(f"Strategy classification failed: {e}")

        return {
            "type": "vector",
            "confidence": 0.5,
            "error": "Base router not available",
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
        """
        # Vision routing explanation
        vision_explanation = self.vision_router.explain_routing(
            query=query,
            retrieved_docs=retrieved_docs,
            document_profiles=document_profiles,
            language=language,
        )

        # Base router explanation
        base_explanation = None
        if self.base_router:
            try:
                if hasattr(self.base_router, 'classify'):
                    base_explanation = self.base_router.classify(query)
            except Exception as e:
                base_explanation = {"error": str(e)}

        return {
            "query": query,
            "vision_routing": vision_explanation,
            "strategy_routing": base_explanation,
            "combined_decision": {
                "would_use_vision": vision_explanation["routing_decision"]["selected_llm"] == "vision",
                "query_type": vision_explanation["routing_decision"]["query_type"],
                "reasoning": vision_explanation["routing_decision"]["reasoning"],
            },
        }

    def get_routing_config(self) -> Dict[str, Any]:
        """Get current routing configuration."""
        return {
            "enable_vision_routing": self.enable_vision_routing,
            "vision_thresholds": self.vision_router.get_routing_stats(),
            "base_router_available": self.base_router is not None,
        }


# Factory functions for common configurations

def create_standard_router() -> EnhancedQueryRouter:
    """Create router with standard settings."""
    return EnhancedQueryRouter()


def create_vision_first_router() -> EnhancedQueryRouter:
    """Create router that prioritizes vision (lower thresholds)."""
    from app.api.services.vision_router import VisionRouterFactory
    return EnhancedQueryRouter(
        vision_router=VisionRouterFactory.create_aggressive()
    )


def create_text_first_router() -> EnhancedQueryRouter:
    """Create router that prioritizes text (higher thresholds)."""
    from app.api.services.vision_router import VisionRouterFactory
    return EnhancedQueryRouter(
        vision_router=VisionRouterFactory.create_conservative()
    )


def create_vision_disabled_router() -> EnhancedQueryRouter:
    """Create router with vision routing disabled."""
    return EnhancedQueryRouter(enable_vision_routing=False)
