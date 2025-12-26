"""
Tests for Vision Data Models

Tests the data models and their serialization/deserialization.
"""

import pytest
from datetime import datetime
from app.api.models.vision import (
    DocumentVisualProfile,
    ProcessedImage,
    RoutingDecision,
    VisualQuerySignals,
    ChartData,
    TableData,
    DiagramStructure,
    DiagramNode,
    DiagramEdge,
    BoundingBox,
    ImageType,
    ProcessingMode,
    DataPoint,
    AxisInfo,
    UnifiedQueryResponse,
    RoutingInfo,
    SourceInfo,
    ResponseMetadata,
    VisualAnalysis,
    ImageAnalysisResult,
)


class TestDocumentVisualProfile:
    """Tests for DocumentVisualProfile model"""

    def test_create_basic_profile(self):
        """Test creating a basic document profile"""
        profile = DocumentVisualProfile(
            document_id="doc-123",
            mime_type="application/pdf",
            extension=".pdf",
            image_count=5,
        )

        assert profile.document_id == "doc-123"
        assert profile.image_count == 5
        assert profile.is_pure_image is False

    def test_profile_with_visual_content(self):
        """Test profile with various visual content"""
        profile = DocumentVisualProfile(
            document_id="doc-456",
            mime_type="application/pdf",
            extension=".pdf",
            image_count=10,
            has_charts=True,
            has_diagrams=True,
            visual_complexity_score=0.75,
        )

        assert profile.has_charts is True
        assert profile.has_diagrams is True
        assert profile.visual_complexity_score == 0.75
        assert profile.requires_vision_llm is True

    def test_profile_to_dict(self):
        """Test converting profile to dictionary"""
        profile = DocumentVisualProfile(
            document_id="doc-789",
            mime_type="application/pdf",
            extension=".pdf",
            image_count=3,
            visual_complexity_score=0.5,
        )

        result = profile.to_dict()

        assert isinstance(result, dict)
        assert result["document_id"] == "doc-789"
        assert result["image_count"] == 3
        assert result["visual_complexity_score"] == 0.5

    def test_pure_image_document(self):
        """Test pure image document detection"""
        profile = DocumentVisualProfile(
            document_id="img-doc",
            mime_type="image/png",
            extension=".png",
            is_pure_image=True,
            image_count=1,
            image_area_ratio=1.0,
        )

        assert profile.is_pure_image is True
        assert profile.image_area_ratio == 1.0
        assert profile.requires_vision_llm is True

    def test_requires_vision_llm_conditions(self):
        """Test various conditions that require Vision LLM"""
        # Pure image
        profile1 = DocumentVisualProfile(
            document_id="doc1",
            mime_type="image/png",
            extension=".png",
            is_pure_image=True,
        )
        assert profile1.requires_vision_llm is True

        # High visual complexity
        profile2 = DocumentVisualProfile(
            document_id="doc2",
            mime_type="application/pdf",
            extension=".pdf",
            visual_complexity_score=0.5,
        )
        assert profile2.requires_vision_llm is True

        # Has charts
        profile3 = DocumentVisualProfile(
            document_id="doc3",
            mime_type="application/pdf",
            extension=".pdf",
            has_charts=True,
        )
        assert profile3.requires_vision_llm is True

        # Low complexity, no visual content
        profile4 = DocumentVisualProfile(
            document_id="doc4",
            mime_type="application/pdf",
            extension=".pdf",
            visual_complexity_score=0.1,
        )
        assert profile4.requires_vision_llm is False

    def test_recommended_processing_mode(self):
        """Test processing mode recommendations"""
        # Pure image -> MULTIMODAL
        profile1 = DocumentVisualProfile(
            document_id="doc1",
            mime_type="image/png",
            extension=".png",
            is_pure_image=True,
        )
        assert profile1.recommended_processing_mode == ProcessingMode.MULTIMODAL

        # High complexity -> MULTIMODAL
        profile2 = DocumentVisualProfile(
            document_id="doc2",
            mime_type="application/pdf",
            extension=".pdf",
            visual_complexity_score=0.5,
        )
        assert profile2.recommended_processing_mode == ProcessingMode.MULTIMODAL

        # Low complexity -> TEXT_ONLY
        profile3 = DocumentVisualProfile(
            document_id="doc3",
            mime_type="application/pdf",
            extension=".pdf",
            visual_complexity_score=0.1,
        )
        assert profile3.recommended_processing_mode == ProcessingMode.TEXT_ONLY


class TestProcessedImage:
    """Tests for ProcessedImage model"""

    def test_create_processed_image(self):
        """Test creating a processed image"""
        image = ProcessedImage(
            image_bytes=b"fake_image_data",
            mime_type="image/png",
            original_size=(800, 600),
            processed_size=(400, 300),
            format="PNG",
        )

        assert image.mime_type == "image/png"
        assert image.original_size == (800, 600)
        assert image.processed_size == (400, 300)
        assert image.file_size_bytes == len(b"fake_image_data")

    def test_image_with_page_info(self):
        """Test image with page information"""
        image = ProcessedImage(
            image_bytes=b"data",
            mime_type="image/jpeg",
            original_size=(1024, 768),
            processed_size=(512, 384),
            format="JPEG",
            page_number=3,
            image_type=ImageType.CHART,
        )

        assert image.page_number == 3
        assert image.image_type == ImageType.CHART


class TestBoundingBox:
    """Tests for BoundingBox model"""

    def test_create_bounding_box(self):
        """Test creating a bounding box"""
        box = BoundingBox(x=0.1, y=0.2, width=0.5, height=0.3)

        assert box.x == 0.1
        assert box.y == 0.2
        assert box.width == 0.5
        assert box.height == 0.3

    def test_bounding_box_area(self):
        """Test bounding box area calculation"""
        box = BoundingBox(x=0, y=0, width=0.5, height=0.4)
        assert box.area == 0.2


class TestRoutingDecision:
    """Tests for RoutingDecision model"""

    def test_vision_routing_decision(self):
        """Test vision routing decision"""
        decision = RoutingDecision(
            selected_llm="vision",
            reasoning="Query contains chart analysis request",
            confidence=0.85,
            query_type="hybrid",
        )

        assert decision.selected_llm == "vision"
        assert decision.confidence == 0.85
        assert "chart" in decision.reasoning.lower()

    def test_text_routing_decision(self):
        """Test text routing decision"""
        decision = RoutingDecision(
            selected_llm="text",
            reasoning="Standard text-based query",
            confidence=0.9,
            query_type="vector",
        )

        assert decision.selected_llm == "text"
        assert decision.query_type == "vector"

    def test_code_routing_decision(self):
        """Test code routing decision"""
        decision = RoutingDecision(
            selected_llm="code",
            reasoning="Query requests code generation",
            confidence=0.95,
            query_type="code",
        )

        assert decision.selected_llm == "code"


class TestVisualQuerySignals:
    """Tests for VisualQuerySignals model"""

    def test_visual_query_signals(self):
        """Test visual query signals"""
        signals = VisualQuerySignals(
            is_visual_query=True,
            visual_aspects=["chart", "data_viz"],
            confidence=0.8,
            suggested_model="vision",
            detected_patterns=["bar chart", "trend"],
        )

        assert signals.is_visual_query is True
        assert "chart" in signals.visual_aspects
        assert signals.suggested_model == "vision"

    def test_non_visual_query_signals(self):
        """Test non-visual query signals"""
        signals = VisualQuerySignals(
            is_visual_query=False,
            visual_aspects=[],
            confidence=0.1,
            suggested_model="text",
        )

        assert signals.is_visual_query is False
        assert len(signals.visual_aspects) == 0


class TestChartData:
    """Tests for ChartData model"""

    def test_create_chart_data(self):
        """Test creating chart data"""
        chart = ChartData(
            chart_type="bar",
            title="Monthly Sales",
            data_points=[
                DataPoint(x="Jan", y=100),
                DataPoint(x="Feb", y=150),
                DataPoint(x="Mar", y=200),
            ],
        )

        assert chart.chart_type == "bar"
        assert chart.title == "Monthly Sales"
        assert len(chart.data_points) == 3

    def test_chart_with_axis_info(self):
        """Test chart with axis information"""
        chart = ChartData(
            chart_type="line",
            title="Trend Analysis",
            x_axis=AxisInfo(label="Month", unit=""),
            y_axis=AxisInfo(label="Sales", unit="$"),
            data_points=[],
        )

        assert chart.x_axis.label == "Month"
        assert chart.y_axis.unit == "$"

    def test_chart_to_dict(self):
        """Test chart to_dict method"""
        chart = ChartData(
            chart_type="line",
            title="Trend Analysis",
            data_points=[],
        )

        result = chart.to_dict()
        assert result["chart_type"] == "line"
        assert result["title"] == "Trend Analysis"


class TestTableData:
    """Tests for TableData model"""

    def test_create_table_data(self):
        """Test creating table data"""
        table = TableData(
            headers=["Name", "Age", "City"],
            rows=[
                ["Alice", "30", "Seoul"],
                ["Bob", "25", "Busan"],
            ],
            title="User Data",
        )

        assert len(table.headers) == 3
        assert len(table.rows) == 2
        assert table.rows[0][0] == "Alice"

    def test_table_properties(self):
        """Test table properties"""
        table = TableData(
            headers=["A", "B", "C"],
            rows=[["1", "2", "3"], ["4", "5", "6"]],
        )

        assert table.row_count == 2
        assert table.col_count == 3

    def test_table_to_dict(self):
        """Test table to_dict method"""
        table = TableData(
            headers=["A", "B"],
            rows=[["1", "2"]],
        )

        result = table.to_dict()
        assert result["headers"] == ["A", "B"]
        assert result["rows"] == [["1", "2"]]


class TestDiagramStructure:
    """Tests for DiagramStructure model"""

    def test_create_diagram(self):
        """Test creating a diagram structure"""
        diagram = DiagramStructure(
            diagram_type="flowchart",
            title="Process Flow",
            nodes=[
                DiagramNode(id="1", label="Start"),
                DiagramNode(id="2", label="Process"),
                DiagramNode(id="3", label="End"),
            ],
            edges=[
                DiagramEdge(source_id="1", target_id="2"),
                DiagramEdge(source_id="2", target_id="3"),
            ],
        )

        assert diagram.diagram_type == "flowchart"
        assert len(diagram.nodes) == 3
        assert len(diagram.edges) == 2

    def test_diagram_to_dict(self):
        """Test diagram to_dict method"""
        diagram = DiagramStructure(
            diagram_type="sequence",
            nodes=[DiagramNode(id="1", label="Actor")],
            edges=[],
        )

        result = diagram.to_dict()
        assert result["diagram_type"] == "sequence"
        assert len(result["nodes"]) == 1


class TestUnifiedQueryResponse:
    """Tests for UnifiedQueryResponse model"""

    def test_create_unified_response(self):
        """Test creating unified query response"""
        response = UnifiedQueryResponse(
            answer="차트는 상승 추세를 보여줍니다.",
            confidence=0.9,
            routing=RoutingInfo(
                selected_llm="vision",
                reasoning="Visual query detected",
                query_type="hybrid",
                visual_signals_detected=True,
            ),
            sources=[
                SourceInfo(
                    document_id="doc-1",
                    filename="report.pdf",
                    page_number=5,
                    relevance_score=0.95,
                )
            ],
        )

        assert response.answer == "차트는 상승 추세를 보여줍니다."
        assert response.confidence == 0.9
        assert response.routing.selected_llm == "vision"

    def test_response_with_metadata(self):
        """Test response with metadata"""
        response = UnifiedQueryResponse(
            answer="The chart shows growth.",
            confidence=0.85,
            routing=RoutingInfo(
                selected_llm="vision",
                reasoning="Chart analysis",
                query_type="hybrid",
                visual_signals_detected=True,
            ),
            sources=[],
            metadata=ResponseMetadata(
                total_tokens=1500,
                latency_ms=250.5,
                model_used="gpt-4o",
                vision_model_used="gpt-4o",
                cache_hit=False,
                cost=0.025,
            ),
        )

        assert response.metadata.total_tokens == 1500
        assert response.metadata.model_used == "gpt-4o"

    def test_response_to_dict(self):
        """Test response to_dict method"""
        response = UnifiedQueryResponse(
            answer="Test answer",
            confidence=0.8,
            routing=RoutingInfo(
                selected_llm="text",
                reasoning="Text query",
                query_type="vector",
                visual_signals_detected=False,
            ),
            sources=[],
        )

        result = response.to_dict()
        assert "answer" in result
        assert "confidence" in result
        assert "routing" in result
        assert "sources" in result


class TestImageAnalysisResult:
    """Tests for ImageAnalysisResult model"""

    def test_create_analysis_result(self):
        """Test creating image analysis result"""
        result = ImageAnalysisResult(
            image_id="img-001",
            page_number=1,
            description="Bar chart showing sales data",
            extracted_text="Sales: $100K",
            confidence=0.9,
            processing_time_ms=150.5,
        )

        assert result.image_id == "img-001"
        assert result.page_number == 1
        assert result.confidence == 0.9


class TestVisualAnalysis:
    """Tests for VisualAnalysis model"""

    def test_create_visual_analysis(self):
        """Test creating visual analysis"""
        analysis = VisualAnalysis(
            analyzed_images=[
                ImageAnalysisResult(
                    image_id="img-1",
                    page_number=1,
                    description="Chart",
                )
            ],
            extracted_data={"charts": 1, "tables": 0},
            visual_summary="Document contains one bar chart",
            total_processing_time_ms=500.0,
        )

        assert len(analysis.analyzed_images) == 1
        assert analysis.visual_summary is not None
        assert analysis.total_processing_time_ms == 500.0


class TestImageType:
    """Tests for ImageType enum"""

    def test_image_types(self):
        """Test different image types"""
        types = [
            ImageType.PAGE,
            ImageType.EMBEDDED,
            ImageType.CHART,
            ImageType.TABLE,
            ImageType.DIAGRAM,
            ImageType.SCREENSHOT,
            ImageType.PHOTO,
        ]

        for img_type in types:
            assert isinstance(img_type.value, str)


class TestProcessingMode:
    """Tests for ProcessingMode enum"""

    def test_processing_modes(self):
        """Test different processing modes"""
        modes = [
            ProcessingMode.TEXT_ONLY,
            ProcessingMode.VLM_ENHANCED,
            ProcessingMode.MULTIMODAL,
            ProcessingMode.OCR,
        ]

        for mode in modes:
            assert isinstance(mode.value, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
