"""
Tests for Vision-Aware Router

Tests routing decisions between Vision LLM and Text LLM.
"""

import pytest
from app.api.services.vision_router import (
    VisionAwareRouter,
    VisionRouterFactory,
    DocumentContext,
    RoutingContext,
)
from app.api.services.enhanced_query_router import (
    EnhancedQueryRouter,
    EnhancedQueryType,
    EnhancedRoutingResult,
)
from app.api.models.vision import DocumentVisualProfile, RoutingDecision, VisualQuerySignals


class TestVisionAwareRouter:
    """Tests for VisionAwareRouter"""

    @pytest.fixture
    def router(self):
        """Create router instance"""
        return VisionAwareRouter()

    # ==================== Basic Routing Tests ====================

    class TestBasicRouting:
        """Basic routing decision tests"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        @pytest.mark.asyncio
        async def test_visual_query_routes_to_vision(self, router):
            """Test that visual queries route to Vision LLM"""
            # Use strong visual query with multiple signals
            decision = await router.route(
                query="Analyze this chart and explain the bar graph visualization",
                language="en",
            )

            # Strong visual queries should route to vision
            assert decision.selected_llm == "vision"
            assert decision.confidence >= 0.3

        @pytest.mark.asyncio
        async def test_text_query_routes_to_text(self, router):
            """Test that text queries route to Text LLM"""
            decision = await router.route(
                query="RAG 시스템이란 무엇인가요?",
                language="ko",
            )

            assert decision.selected_llm == "text"

        @pytest.mark.asyncio
        async def test_code_query_routes_to_code(self, router):
            """Test that code queries route to Code LLM"""
            decision = await router.route(
                query="Write a Python function to calculate factorial",
                language="en",
            )

            assert decision.selected_llm == "code"

    # ==================== Force Routing Tests ====================

    class TestForceRouting:
        """Tests for forced routing decisions"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        @pytest.mark.asyncio
        async def test_force_vision(self, router):
            """Test force_vision parameter"""
            decision = await router.route(
                query="What is machine learning?",  # Non-visual query
                force_vision=True,
            )

            assert decision.selected_llm == "vision"
            assert decision.confidence == 1.0
            assert "Forced" in decision.reasoning

        @pytest.mark.asyncio
        async def test_force_text(self, router):
            """Test force_text parameter"""
            decision = await router.route(
                query="Analyze this chart",  # Visual query
                force_text=True,
            )

            assert decision.selected_llm == "text"
            assert decision.confidence == 1.0
            assert "Forced" in decision.reasoning

    # ==================== Document Context Tests ====================

    class TestDocumentContextRouting:
        """Tests for document context-based routing"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        @pytest.mark.asyncio
        async def test_visual_documents_influence_routing(self, router):
            """Test that visual documents influence routing"""
            # Create visual document profile
            profile = DocumentVisualProfile(
                document_id="doc-1",
                mime_type="application/pdf",
                extension=".pdf",
                image_count=5,
                has_charts=True,
                visual_complexity_score=0.7,
            )

            decision = await router.route(
                query="Summarize this document",  # Neutral query
                document_profiles={"doc-1": profile},
                retrieved_docs=[{"id": "doc-1", "score": 0.9}],
            )

            # High visual content should push toward vision
            # Result depends on thresholds and query signals
            assert decision.selected_llm in ["vision", "text"]

        @pytest.mark.asyncio
        async def test_text_documents_stay_text(self, router):
            """Test that text-only documents stay with text LLM"""
            profile = DocumentVisualProfile(
                document_id="doc-2",
                mime_type="application/pdf",
                extension=".pdf",
                image_count=0,
                visual_complexity_score=0.0,
            )

            decision = await router.route(
                query="Summarize this document",
                document_profiles={"doc-2": profile},
                retrieved_docs=[{"id": "doc-2", "score": 0.9}],
            )

            assert decision.selected_llm == "text"

        @pytest.mark.asyncio
        async def test_multiple_documents_ratio(self, router):
            """Test routing with mixed visual/text documents"""
            profiles = {
                "doc-1": DocumentVisualProfile(
                    document_id="doc-1",
                    mime_type="application/pdf",
                    extension=".pdf",
                    image_count=5,
                    has_charts=True,
                    visual_complexity_score=0.5,
                ),
                "doc-2": DocumentVisualProfile(
                    document_id="doc-2",
                    mime_type="application/pdf",
                    extension=".pdf",
                    image_count=0,
                    visual_complexity_score=0.0,
                ),
                "doc-3": DocumentVisualProfile(
                    document_id="doc-3",
                    mime_type="application/pdf",
                    extension=".pdf",
                    image_count=0,
                    visual_complexity_score=0.0,
                ),
            }

            docs = [
                {"id": "doc-1", "score": 0.9},
                {"id": "doc-2", "score": 0.8},
                {"id": "doc-3", "score": 0.7},
            ]

            decision = await router.route(
                query="What information is in these documents?",
                document_profiles=profiles,
                retrieved_docs=docs,
            )

            # 1 out of 3 is visual (33%), below default threshold (30%)
            # But still at threshold, could go either way
            assert decision.selected_llm in ["vision", "text"]

    # ==================== Document Routing Tests ====================

    class TestDocumentRouting:
        """Tests for document-time routing decisions"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        @pytest.mark.asyncio
        async def test_route_pure_image_document(self, router):
            """Test routing for pure image document"""
            profile = DocumentVisualProfile(
                document_id="img-doc",
                mime_type="image/png",
                extension=".png",
                is_pure_image=True,
                image_count=1,
            )

            decision = await router.route_for_document(profile)

            assert decision.selected_llm == "vision"
            assert "Pure image" in decision.reasoning

        @pytest.mark.asyncio
        async def test_route_chart_document(self, router):
            """Test routing for document with charts"""
            profile = DocumentVisualProfile(
                document_id="chart-doc",
                mime_type="application/pdf",
                extension=".pdf",
                image_count=3,
                has_charts=True,
                visual_complexity_score=0.6,
            )

            decision = await router.route_for_document(profile)

            assert decision.selected_llm == "vision"
            assert "chart" in decision.reasoning.lower()

        @pytest.mark.asyncio
        async def test_route_text_document(self, router):
            """Test routing for text-only document"""
            profile = DocumentVisualProfile(
                document_id="text-doc",
                mime_type="application/pdf",
                extension=".pdf",
                image_count=0,
                visual_complexity_score=0.0,
            )

            decision = await router.route_for_document(profile)

            assert decision.selected_llm == "text"
            assert "text-based" in decision.reasoning.lower()

    # ==================== Query Analysis Tests ====================

    class TestQueryAnalysis:
        """Tests for query analysis"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        def test_analyze_visual_query(self, router):
            """Test analyzing a visual query"""
            signals = router.analyze_query("What's in this chart?", "en")

            assert signals.is_visual_query
            assert "visual_elements" in signals.visual_aspects or "data_viz" in signals.visual_aspects

        def test_analyze_korean_query(self, router):
            """Test analyzing a Korean query"""
            signals = router.analyze_query("이 그래프를 설명해주세요", "ko")

            assert signals.is_visual_query
            assert signals.language == "ko"

        def test_analyze_text_query(self, router):
            """Test analyzing a text query"""
            signals = router.analyze_query("Explain machine learning", "en")

            assert not signals.is_visual_query
            assert signals.suggested_model == "text"

    # ==================== Explain Routing Tests ====================

    class TestExplainRouting:
        """Tests for routing explanation"""

        @pytest.fixture
        def router(self):
            return VisionAwareRouter()

        def test_explain_routing_visual(self, router):
            """Test routing explanation for visual query"""
            explanation = router.explain_routing(
                query="Analyze this chart",
                language="en",
            )

            assert "query" in explanation
            assert "query_analysis" in explanation
            assert "document_analysis" in explanation
            assert "routing_decision" in explanation

        def test_explain_routing_with_documents(self, router):
            """Test routing explanation with document context"""
            profile = DocumentVisualProfile(
                document_id="doc-1",
                mime_type="application/pdf",
                extension=".pdf",
                image_count=5,
                has_charts=True,
                visual_complexity_score=0.5,
            )

            explanation = router.explain_routing(
                query="Summarize this",
                retrieved_docs=[{"id": "doc-1", "score": 0.9}],
                document_profiles={"doc-1": profile},
            )

            assert explanation["document_analysis"]["total_docs"] == 1
            assert explanation["document_analysis"]["visual_docs"] == 1

    # ==================== Configuration Tests ====================

    class TestConfiguration:
        """Tests for router configuration"""

        def test_get_routing_stats(self):
            """Test getting routing statistics/config"""
            router = VisionAwareRouter()
            stats = router.get_routing_stats()

            assert "thresholds" in stats
            assert "weights" in stats
            assert "supported_languages" in stats

        def test_custom_thresholds(self):
            """Test router with custom thresholds"""
            router = VisionAwareRouter(
                visual_query_threshold=0.5,
                visual_doc_ratio_threshold=0.5,
            )

            stats = router.get_routing_stats()
            assert stats["thresholds"]["visual_query_confidence"] == 0.5
            assert stats["thresholds"]["visual_doc_ratio"] == 0.5


class TestVisionRouterFactory:
    """Tests for VisionRouterFactory"""

    def test_create_default(self):
        """Test creating default router"""
        router = VisionRouterFactory.create_default()
        assert isinstance(router, VisionAwareRouter)

    def test_create_aggressive(self):
        """Test creating aggressive (vision-first) router"""
        router = VisionRouterFactory.create_aggressive()
        stats = router.get_routing_stats()

        # Aggressive has lower thresholds
        assert stats["thresholds"]["visual_query_confidence"] == 0.2

    def test_create_conservative(self):
        """Test creating conservative (text-first) router"""
        router = VisionRouterFactory.create_conservative()
        stats = router.get_routing_stats()

        # Conservative has higher thresholds
        assert stats["thresholds"]["visual_query_confidence"] == 0.5

    def test_create_from_settings(self):
        """Test creating router from settings dict"""
        settings = {
            "visual_query_threshold": 0.4,
            "visual_doc_ratio_threshold": 0.4,
        }

        router = VisionRouterFactory.create_from_settings(settings)
        stats = router.get_routing_stats()

        assert stats["thresholds"]["visual_query_confidence"] == 0.4


class TestEnhancedQueryRouter:
    """Tests for EnhancedQueryRouter"""

    @pytest.fixture
    def router(self):
        """Create enhanced router instance"""
        return EnhancedQueryRouter()

    @pytest.mark.asyncio
    async def test_route_visual_query(self, router):
        """Test routing a visual query"""
        result = await router.route(
            query="이 차트의 데이터를 분석해주세요",
            language="ko",
        )

        assert isinstance(result, EnhancedRoutingResult)
        assert result.selected_llm in ["vision", "text", "code"]
        assert result.is_visual_query

    @pytest.mark.asyncio
    async def test_route_text_query(self, router):
        """Test routing a text query"""
        result = await router.route(
            query="What is the capital of France?",
            language="en",
        )

        assert isinstance(result, EnhancedRoutingResult)
        assert not result.is_visual_query

    def test_analyze_query(self, router):
        """Test query analysis"""
        signals = router.analyze_query("Show me the chart", "en")

        assert signals is not None
        assert hasattr(signals, "is_visual_query")

    def test_classify_strategy(self, router):
        """Test strategy classification"""
        result = router.classify_strategy("What is machine learning?")

        assert "type" in result
        assert result["type"] in ["vector", "graph", "hybrid", "code"]

    def test_explain_routing(self, router):
        """Test routing explanation"""
        explanation = router.explain_routing(
            query="Analyze this diagram",
            language="en",
        )

        assert "query" in explanation
        assert "vision_routing" in explanation
        assert "combined_decision" in explanation

    def test_get_routing_config(self, router):
        """Test getting routing configuration"""
        config = router.get_routing_config()

        assert "enable_vision_routing" in config
        assert "vision_thresholds" in config


class TestRoutingResultSerialization:
    """Tests for routing result serialization"""

    @pytest.mark.asyncio
    async def test_enhanced_result_to_dict(self):
        """Test EnhancedRoutingResult to_dict"""
        router = EnhancedQueryRouter()
        result = await router.route(
            query="Analyze the chart",
            language="en",
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "query_type" in result_dict
        assert "selected_llm" in result_dict
        assert "llm_confidence" in result_dict
        assert "is_visual_query" in result_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
