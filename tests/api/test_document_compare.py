"""
Tests for Document Compare Service

Tests document comparison functionality with mock services.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.api.models.document import (
    DocumentCompareRequest,
    DocumentSection,
    DocumentCompareResult,
    ComparisonDifference,
    ComparisonSummary,
)
from app.api.services.document_compare_service import (
    DocumentCompareService,
    get_document_compare_service,
)


# API prefix used by the application
API_PREFIX = "/api/v1"


class TestDocumentCompareServiceInit:
    """Tests for DocumentCompareService initialization"""

    def test_init_with_hybrid_rag(self):
        """Test initialization with hybrid_rag"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        assert service.hybrid_rag == mock_rag
        assert service.llm_adapter is None

    def test_init_with_llm_adapter(self):
        """Test initialization with llm_adapter"""
        mock_rag = MagicMock()
        mock_llm = MagicMock()
        service = DocumentCompareService(mock_rag, mock_llm)
        assert service.hybrid_rag == mock_rag
        assert service.llm_adapter == mock_llm

    def test_default_settings(self):
        """Test default settings are applied"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        assert service.max_sections_per_doc >= 1
        assert service.max_documents >= 2
        assert service.summary_max_tokens >= 100


class TestLanguagePrompts:
    """Tests for language-specific prompts"""

    def test_korean_prompts(self):
        """Test Korean prompt retrieval"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        prompts = service._get_language_prompts("ko")

        assert "system" in prompts
        assert "task" in prompts
        assert "문서" in prompts["system"] or "분석" in prompts["system"]

    def test_english_prompts(self):
        """Test English prompt retrieval"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        prompts = service._get_language_prompts("en")

        assert "system" in prompts
        assert "task" in prompts
        assert "document" in prompts["system"].lower()

    def test_japanese_prompts(self):
        """Test Japanese prompt retrieval"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        prompts = service._get_language_prompts("ja")

        assert "system" in prompts
        assert "task" in prompts
        assert "文書" in prompts["system"]

    def test_unknown_language_defaults_to_korean(self):
        """Test unknown language defaults to Korean"""
        mock_rag = MagicMock()
        service = DocumentCompareService(mock_rag)
        prompts = service._get_language_prompts("xyz")

        assert prompts == service._get_language_prompts("ko")


class TestSearchDocument:
    """Tests for document search functionality"""

    @pytest.fixture
    def service(self):
        """Create service with mock hybrid_rag"""
        mock_rag = MagicMock()
        mock_rag.vector_search = MagicMock(return_value=[
            {
                "content": "Test content 1",
                "section_title": "Section 1",
                "page_number": 1,
                "score": 0.9,
                "chunk_id": "chunk1",
            },
            {
                "content": "Test content 2",
                "section_title": "Section 2",
                "page_number": 2,
                "score": 0.8,
                "chunk_id": "chunk2",
            },
        ])
        return DocumentCompareService(mock_rag)

    @pytest.mark.asyncio
    async def test_search_returns_sections(self, service):
        """Test that search returns DocumentSection objects"""
        sections = await service._search_document("doc1", "test topic", top_k=3)

        assert isinstance(sections, list)
        for section in sections:
            assert isinstance(section, DocumentSection)

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        """Test handling of empty search results"""
        mock_rag = MagicMock()
        mock_rag.vector_search = MagicMock(return_value=[])
        service = DocumentCompareService(mock_rag)

        sections = await service._search_document("doc1", "test topic")
        assert sections == []

    @pytest.mark.asyncio
    async def test_search_handles_exception(self):
        """Test that search handles exceptions gracefully"""
        mock_rag = MagicMock()
        mock_rag.vector_search = MagicMock(side_effect=Exception("Search failed"))
        service = DocumentCompareService(mock_rag)

        # Should not raise, returns empty list
        sections = await service._search_document("doc1", "test topic")
        assert sections == []


class TestCompare:
    """Tests for compare functionality"""

    @pytest.fixture
    def mock_service(self):
        """Create service with all mocks"""
        mock_rag = MagicMock()
        mock_rag.vector_search = MagicMock(return_value=[
            {
                "content": "Sample content for comparison",
                "section_title": "Introduction",
                "page_number": 1,
                "score": 0.85,
            }
        ])

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value='{"summary": "Test summary", "commonalities": ["Common 1"], "differences": []}')

        service = DocumentCompareService(mock_rag, mock_llm)
        return service

    @pytest.mark.asyncio
    async def test_compare_returns_comparison_summary(self, mock_service):
        """Test that compare returns ComparisonSummary"""
        with patch.object(mock_service, '_get_document_name', new_callable=AsyncMock) as mock_name:
            mock_name.return_value = "Test Document"

            request = DocumentCompareRequest(
                document_ids=["doc1", "doc2"],
                topic="Test topic"
            )
            result = await mock_service.compare(request)

            assert isinstance(result, ComparisonSummary)
            assert result.topic == "Test topic"
            assert len(result.documents) == 2

    @pytest.mark.asyncio
    async def test_compare_limits_documents(self, mock_service):
        """Test that compare limits number of documents"""
        with patch.object(mock_service, '_get_document_name', new_callable=AsyncMock) as mock_name:
            mock_name.return_value = "Test Document"

            mock_service.max_documents = 3
            request = DocumentCompareRequest(
                document_ids=["doc1", "doc2", "doc3", "doc4", "doc5"],
                topic="Test topic"
            )
            result = await mock_service.compare(request)

            # Should only process max_documents
            assert len(result.documents) == 3


class TestStreamCompare:
    """Tests for streaming compare functionality"""

    @pytest.fixture
    def mock_service(self):
        """Create service with mocks for streaming"""
        mock_rag = MagicMock()
        mock_rag.vector_search = MagicMock(return_value=[
            {
                "content": "Content for streaming",
                "section_title": "Section",
                "score": 0.8,
            }
        ])

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value='{"summary": "Streamed summary", "commonalities": [], "differences": []}')

        return DocumentCompareService(mock_rag, mock_llm)

    @pytest.mark.asyncio
    async def test_stream_yields_start_event(self, mock_service):
        """Test that stream_compare yields compare_start event"""
        with patch.object(mock_service, '_get_document_name', new_callable=AsyncMock) as mock_name:
            mock_name.return_value = "Document"

            request = DocumentCompareRequest(
                document_ids=["doc1", "doc2"],
                topic="Topic"
            )

            events = []
            async for event in mock_service.stream_compare(request):
                events.append(event)

            # First event should be compare_start
            assert events[0]["type"] == "compare_start"
            assert events[0]["data"]["document_count"] == 2

    @pytest.mark.asyncio
    async def test_stream_yields_document_events(self, mock_service):
        """Test that stream_compare yields document events"""
        with patch.object(mock_service, '_get_document_name', new_callable=AsyncMock) as mock_name:
            mock_name.return_value = "Document"

            request = DocumentCompareRequest(
                document_ids=["doc1", "doc2"],
                topic="Topic"
            )

            events = []
            async for event in mock_service.stream_compare(request):
                events.append(event)

            event_types = [e["type"] for e in events]
            assert "document_start" in event_types
            assert "document_result" in event_types

    @pytest.mark.asyncio
    async def test_stream_yields_done_event(self, mock_service):
        """Test that stream_compare yields compare_done event at the end"""
        with patch.object(mock_service, '_get_document_name', new_callable=AsyncMock) as mock_name:
            mock_name.return_value = "Document"

            request = DocumentCompareRequest(
                document_ids=["doc1", "doc2"],
                topic="Topic"
            )

            events = []
            async for event in mock_service.stream_compare(request):
                events.append(event)

            # Last event should be compare_done
            assert events[-1]["type"] == "compare_done"
            assert "summary" in events[-1]["data"]
            assert "documents" in events[-1]["data"]


class TestDocumentCompareEndpoints:
    """Tests for document compare API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from app.api.main import app
        return TestClient(app)

    def test_compare_endpoint_exists(self, client):
        """Test that POST /documents/compare endpoint exists"""
        response = client.post(f"{API_PREFIX}/documents/compare")
        # Should not be 404 (endpoint exists)
        # May be 401 (auth required), 422 (validation), or 500 (service unavailable)
        assert response.status_code != 404

    def test_compare_stream_endpoint_exists(self, client):
        """Test that POST /documents/compare/stream endpoint exists"""
        response = client.post(f"{API_PREFIX}/documents/compare/stream")
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_compare_requires_body(self, client):
        """Test that compare requires request body"""
        response = client.post(f"{API_PREFIX}/documents/compare")
        # Should fail validation or require auth
        assert response.status_code in [400, 401, 422]

    def test_compare_requires_document_ids(self, client):
        """Test that compare requires document_ids"""
        response = client.post(
            f"{API_PREFIX}/documents/compare",
            json={"topic": "test topic"}
        )
        # Should fail validation (missing document_ids)
        assert response.status_code in [400, 401, 422]

    def test_compare_requires_topic(self, client):
        """Test that compare requires topic"""
        response = client.post(
            f"{API_PREFIX}/documents/compare",
            json={"document_ids": ["doc1", "doc2"]}
        )
        # Should fail validation (missing topic)
        assert response.status_code in [400, 401, 422]

    def test_compare_minimum_documents(self, client):
        """Test that compare requires at least 2 documents"""
        response = client.post(
            f"{API_PREFIX}/documents/compare",
            json={
                "document_ids": ["doc1"],  # Only 1 document
                "topic": "test topic"
            }
        )
        # Should fail validation (need at least 2 documents)
        assert response.status_code in [400, 401, 422]

    def test_compare_with_valid_request(self, client):
        """Test compare with valid request structure"""
        response = client.post(
            f"{API_PREFIX}/documents/compare",
            json={
                "document_ids": ["doc1", "doc2"],
                "topic": "test topic"
            }
        )
        # Should be handled (may need auth or service unavailable)
        assert response.status_code in [200, 401, 500, 503]


class TestDocumentCompareModels:
    """Tests for document compare Pydantic models"""

    def test_document_section_model(self):
        """Test DocumentSection model"""
        section = DocumentSection(
            content="Test content",
            score=0.85,
            section_title="Title",
            page_number=1,
        )
        assert section.content == "Test content"
        assert section.score == 0.85

    def test_document_compare_result_model(self):
        """Test DocumentCompareResult model"""
        section = DocumentSection(content="Content", score=0.8)
        result = DocumentCompareResult(
            doc_id="doc1",
            doc_name="Test Document",
            relevant_sections=[section],
        )
        assert result.doc_id == "doc1"
        assert len(result.relevant_sections) == 1

    def test_comparison_difference_model(self):
        """Test ComparisonDifference model"""
        diff = ComparisonDifference(
            aspect="Performance",
            documents={"doc1": "Fast", "doc2": "Slow"}
        )
        assert diff.aspect == "Performance"
        assert "doc1" in diff.documents

    def test_comparison_summary_model(self):
        """Test ComparisonSummary model"""
        section = DocumentSection(content="Content", score=0.8)
        doc_result = DocumentCompareResult(
            doc_id="doc1",
            doc_name="Document 1",
            relevant_sections=[section]
        )
        diff = ComparisonDifference(aspect="Test", documents={})

        summary = ComparisonSummary(
            topic="Test Topic",
            documents=[doc_result],
            summary="Summary text",
            commonalities=["Common 1"],
            differences=[diff],
        )

        assert summary.topic == "Test Topic"
        assert len(summary.documents) == 1
        assert len(summary.commonalities) == 1
        assert len(summary.differences) == 1

    def test_document_compare_request_validation(self):
        """Test DocumentCompareRequest validation"""
        # Valid request
        request = DocumentCompareRequest(
            document_ids=["doc1", "doc2"],
            topic="Test topic"
        )
        assert len(request.document_ids) == 2

        # Test minimum document validation
        with pytest.raises(ValueError):
            DocumentCompareRequest(
                document_ids=["doc1"],  # Need at least 2
                topic="Test"
            )

    def test_document_compare_request_max_documents(self):
        """Test DocumentCompareRequest max documents validation"""
        # Model validates max_length=5, so 6 documents should raise error
        with pytest.raises(ValueError):
            DocumentCompareRequest(
                document_ids=["doc1", "doc2", "doc3", "doc4", "doc5", "doc6"],
                topic="Test"
            )

        # 5 documents should be accepted
        request = DocumentCompareRequest(
            document_ids=["doc1", "doc2", "doc3", "doc4", "doc5"],
            topic="Test"
        )
        assert len(request.document_ids) == 5


class TestSingletonAccessor:
    """Tests for singleton service accessor"""

    def test_get_document_compare_service_creates_instance(self):
        """Test that get_document_compare_service creates instance"""
        import app.api.services.document_compare_service as module

        # Reset singleton
        module._compare_service = None

        mock_rag = MagicMock()
        service = get_document_compare_service(mock_rag)

        assert isinstance(service, DocumentCompareService)

    def test_get_document_compare_service_returns_same_instance(self):
        """Test that get_document_compare_service returns same instance"""
        import app.api.services.document_compare_service as module

        # Reset singleton
        module._compare_service = None

        mock_rag = MagicMock()
        service1 = get_document_compare_service(mock_rag)
        service2 = get_document_compare_service()

        assert service1 is service2
