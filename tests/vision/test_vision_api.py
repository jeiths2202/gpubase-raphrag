"""
Tests for Vision API Endpoints

Tests FastAPI request/response models and schema validation.
These tests focus on API contract validation without requiring
full backend integration.
"""

import pytest
from pydantic import ValidationError


class TestVisionQueryRequest:
    """Tests for VisionQueryRequest model"""

    def test_valid_request(self):
        """Test creating a valid request"""
        from app.api.routers.vision import VisionQueryRequest

        request = VisionQueryRequest(
            query="이 차트를 분석해주세요",
            language="ko",
        )

        assert request.query == "이 차트를 분석해주세요"
        assert request.language == "ko"
        assert request.force_vision is False
        assert request.force_text is False

    def test_request_with_document_ids(self):
        """Test request with document IDs"""
        from app.api.routers.vision import VisionQueryRequest

        request = VisionQueryRequest(
            query="Summarize these documents",
            document_ids=["doc-1", "doc-2"],
            language="en",
        )

        assert request.document_ids == ["doc-1", "doc-2"]

    def test_request_force_options(self):
        """Test force vision/text options"""
        from app.api.routers.vision import VisionQueryRequest

        request_vision = VisionQueryRequest(
            query="Test",
            force_vision=True,
        )
        assert request_vision.force_vision is True

        request_text = VisionQueryRequest(
            query="Test",
            force_text=True,
        )
        assert request_text.force_text is True

    def test_request_defaults(self):
        """Test default values"""
        from app.api.routers.vision import VisionQueryRequest

        request = VisionQueryRequest(query="Test query")

        assert request.language == "auto"
        assert request.document_ids is None
        assert request.force_vision is False
        assert request.force_text is False
        assert request.include_images is True
        assert request.max_images == 5

    def test_request_missing_query(self):
        """Test that query is required"""
        from app.api.routers.vision import VisionQueryRequest

        with pytest.raises(ValidationError):
            VisionQueryRequest()


class TestImageAnalysisRequest:
    """Tests for ImageAnalysisRequest model"""

    def test_valid_request(self):
        """Test creating a valid request"""
        from app.api.routers.vision import ImageAnalysisRequest

        request = ImageAnalysisRequest(
            prompt="What's in this image?",
            language="en",
            extract_data=True,
        )

        assert request.prompt == "What's in this image?"
        assert request.language == "en"
        assert request.extract_data is True

    def test_request_defaults(self):
        """Test default values"""
        from app.api.routers.vision import ImageAnalysisRequest

        request = ImageAnalysisRequest(prompt="Analyze this")

        assert request.language == "auto"
        assert request.extract_data is True


class TestDocumentAnalysisRequest:
    """Tests for DocumentAnalysisRequest model"""

    def test_valid_request(self):
        """Test creating a valid request"""
        from app.api.routers.vision import DocumentAnalysisRequest

        request = DocumentAnalysisRequest(
            document_id="doc-123",
            include_images=True,
            force_reanalyze=False,
        )

        assert request.document_id == "doc-123"
        assert request.include_images is True

    def test_request_defaults(self):
        """Test default values"""
        from app.api.routers.vision import DocumentAnalysisRequest

        request = DocumentAnalysisRequest(document_id="doc-456")

        assert request.include_images is True
        assert request.force_reanalyze is False


class TestVisionQueryResponse:
    """Tests for VisionQueryResponse model"""

    def test_response_creation(self):
        """Test creating a response"""
        from app.api.routers.vision import VisionQueryResponse

        response = VisionQueryResponse(
            query_id="query-123",
            answer="차트는 상승 추세를 보여줍니다.",
            sources=["doc-1", "doc-2"],
            confidence=0.85,
            model_used="gpt-4o",
            language="ko",
            routing_decision={"selected_llm": "vision", "used_vision": True},
        )

        assert response.query_id == "query-123"
        assert response.confidence == 0.85
        assert response.model_used == "gpt-4o"
        assert response.language == "ko"

    def test_response_with_visual_info(self):
        """Test response with visual information"""
        from app.api.routers.vision import (
            VisionQueryResponse,
            VisualInfoResponse,
            ChartDataResponse,
        )

        visual_info = VisualInfoResponse(
            charts=[
                ChartDataResponse(
                    chart_type="bar",
                    title="Monthly Sales",
                    description="Sales data for Q1",
                    data_points=[{"month": "Jan", "value": 100}],
                )
            ],
            tables=[],
            images_analyzed=1,
        )

        response = VisionQueryResponse(
            query_id="query-456",
            answer="The chart shows growth.",
            sources=["doc-1"],
            confidence=0.9,
            model_used="gpt-4o",
            visual_info=visual_info,
            language="en",
            routing_decision={"selected_llm": "vision"},
        )

        assert response.visual_info is not None
        assert len(response.visual_info.charts) == 1
        assert response.visual_info.charts[0].chart_type == "bar"


class TestDocumentProfileResponse:
    """Tests for DocumentProfileResponse model"""

    def test_response_creation(self):
        """Test creating a document profile response"""
        from app.api.routers.vision import DocumentProfileResponse

        response = DocumentProfileResponse(
            document_id="doc-123",
            is_visual=True,
            visual_complexity_score=0.75,
            image_count=5,
            has_charts=True,
            has_tables=True,
            has_diagrams=False,
            requires_vision_llm=True,
            processing_recommendation="Vision LLM required for accurate analysis",
        )

        assert response.document_id == "doc-123"
        assert response.is_visual is True
        assert response.visual_complexity_score == 0.75
        assert response.requires_vision_llm is True


class TestRoutingExplanation:
    """Tests for RoutingExplanation model"""

    def test_explanation_creation(self):
        """Test creating a routing explanation"""
        from app.api.routers.vision import RoutingExplanation

        explanation = RoutingExplanation(
            selected_llm="vision",
            reasoning="Query contains chart analysis request",
            confidence=0.85,
            query_signals={
                "is_visual": True,
                "visual_aspects": ["chart", "data_viz"],
            },
            document_signals={
                "total_docs": 3,
                "visual_docs": 2,
                "visual_ratio": 0.67,
            },
        )

        assert explanation.selected_llm == "vision"
        assert explanation.confidence == 0.85
        assert explanation.query_signals["is_visual"] is True


class TestChartDataResponse:
    """Tests for ChartDataResponse model"""

    def test_chart_response(self):
        """Test chart data response"""
        from app.api.routers.vision import ChartDataResponse

        chart = ChartDataResponse(
            chart_type="line",
            title="Trend Analysis",
            description="Shows monthly trends",
            data_points=[
                {"x": "Jan", "y": 100},
                {"x": "Feb", "y": 150},
            ],
        )

        assert chart.chart_type == "line"
        assert len(chart.data_points) == 2


class TestTableDataResponse:
    """Tests for TableDataResponse model"""

    def test_table_response(self):
        """Test table data response"""
        from app.api.routers.vision import TableDataResponse

        table = TableDataResponse(
            headers=["Name", "Value"],
            rows=[["Item A", "100"], ["Item B", "200"]],
            title="Data Table",
        )

        assert len(table.headers) == 2
        assert len(table.rows) == 2


class TestVisualInfoResponse:
    """Tests for VisualInfoResponse model"""

    def test_visual_info_response(self):
        """Test visual info response"""
        from app.api.routers.vision import (
            VisualInfoResponse,
            ChartDataResponse,
            TableDataResponse,
        )

        response = VisualInfoResponse(
            charts=[
                ChartDataResponse(
                    chart_type="pie",
                    title="Distribution",
                    description="Market share",
                    data_points=[],
                )
            ],
            tables=[
                TableDataResponse(
                    headers=["A", "B"],
                    rows=[["1", "2"]],
                )
            ],
            images_analyzed=2,
        )

        assert len(response.charts) == 1
        assert len(response.tables) == 1
        assert response.images_analyzed == 2


class TestRequestValidation:
    """Tests for request validation edge cases"""

    def test_empty_query_string(self):
        """Test with empty query string"""
        from app.api.routers.vision import VisionQueryRequest

        # Empty string is technically valid for Pydantic
        request = VisionQueryRequest(query="")
        assert request.query == ""

    def test_long_query(self):
        """Test with very long query"""
        from app.api.routers.vision import VisionQueryRequest

        long_query = "Analyze this chart " * 100
        request = VisionQueryRequest(query=long_query)
        assert len(request.query) > 1000

    def test_unicode_query(self):
        """Test with unicode characters"""
        from app.api.routers.vision import VisionQueryRequest

        request = VisionQueryRequest(
            query="이 차트를 분석해주세요 📊",
            language="ko",
        )
        assert "📊" in request.query

    def test_special_characters_in_document_id(self):
        """Test document ID with special characters"""
        from app.api.routers.vision import DocumentAnalysisRequest

        request = DocumentAnalysisRequest(
            document_id="doc-123_special.pdf"
        )
        assert request.document_id == "doc-123_special.pdf"


class TestResponseSerialization:
    """Tests for response serialization"""

    def test_response_dict_conversion(self):
        """Test response can be converted to dict"""
        from app.api.routers.vision import VisionQueryResponse

        response = VisionQueryResponse(
            query_id="q-1",
            answer="Test answer",
            sources=["doc-1"],
            confidence=0.9,
            model_used="gpt-4o",
            language="en",
            routing_decision={"selected_llm": "vision"},
        )

        # Pydantic v2 uses model_dump()
        response_dict = response.model_dump()
        assert isinstance(response_dict, dict)
        assert response_dict["query_id"] == "q-1"
        assert response_dict["confidence"] == 0.9

    def test_response_json_conversion(self):
        """Test response can be converted to JSON"""
        from app.api.routers.vision import VisionQueryResponse

        response = VisionQueryResponse(
            query_id="q-2",
            answer="Test",
            sources=[],
            confidence=0.8,
            model_used="claude-3",
            language="ko",
            routing_decision={},
        )

        json_str = response.model_dump_json()
        assert isinstance(json_str, str)
        assert "q-2" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
