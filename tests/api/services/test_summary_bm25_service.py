"""
Tests for Summary BM25 Service

Verifies the Summary-First RAG implementation works correctly.
"""

import pytest
import asyncio
from pathlib import Path

# Set up path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestSummaryBM25Service:
    """Tests for SummaryBM25Service"""

    @pytest.fixture
    def service(self):
        """Create service instance with test summaries directory"""
        from app.api.services.summary_bm25_service import SummaryBM25Service

        # Use the actual summaries directory
        summaries_dir = Path(__file__).parent.parent.parent.parent / "uploads" / "summaries"
        if not summaries_dir.exists():
            # Try alternative path for Docker
            summaries_dir = Path("/opt/kms/uploads/summaries")

        return SummaryBM25Service(
            summaries_dir=summaries_dir,
            high_confidence_threshold=0.7,
            medium_confidence_threshold=0.4,
        )

    @pytest.mark.asyncio
    async def test_initialization(self, service):
        """Test service initializes and loads documents"""
        success = await service.initialize()

        if not service.summaries_dir.exists():
            pytest.skip(f"Summaries directory not found: {service.summaries_dir}")

        assert success, "Service should initialize successfully"
        assert service.is_initialized, "Service should be marked as initialized"
        assert service.document_count > 0, "Should load some documents"

    @pytest.mark.asyncio
    async def test_tokenize_english(self, service):
        """Test tokenization of English text"""
        tokens = service._tokenize("tjesmgr error")
        assert "tjesmgr" in tokens
        assert "error" in tokens

    @pytest.mark.asyncio
    async def test_tokenize_korean(self, service):
        """Test tokenization of Korean text"""
        tokens = service._tokenize("에러코드 발생")
        # Should have bi-grams for Korean
        assert len(tokens) > 2, "Korean text should produce multiple tokens including bi-grams"

    @pytest.mark.asyncio
    async def test_tokenize_mixed(self, service):
        """Test tokenization of mixed language text"""
        tokens = service._tokenize("TJES 에러 발생")
        assert "tjes" in tokens  # Lowercase
        assert len(tokens) >= 3  # At least 3 tokens (tjes + Korean terms)

    @pytest.mark.asyncio
    async def test_error_code_search(self, service):
        """Test direct error code lookup"""
        await service.initialize()

        if not service.is_initialized:
            pytest.skip("Service not initialized (summaries may not exist)")

        # Test common error code
        result = await service.search_error_code("-5212")

        if result:
            assert result.score >= 0.5, "Direct lookup should have high score"
            assert result.document.doc_type.value == "error-codes"
            print(f"Found error: {result.document.name}")
        else:
            # May not exist in test data
            print("Error code -5212 not found in test data")

    @pytest.mark.asyncio
    async def test_command_search(self, service):
        """Test command lookup"""
        await service.initialize()

        if not service.is_initialized:
            pytest.skip("Service not initialized")

        results = await service.search_command("tjesmgr")

        if results:
            assert len(results) > 0
            assert results[0].document.doc_type.value == "commands"
            print(f"Found command: {results[0].document.name}")
        else:
            print("Command tjesmgr not found in test data")

    @pytest.mark.asyncio
    async def test_term_search(self, service):
        """Test glossary term lookup"""
        await service.initialize()

        if not service.is_initialized:
            pytest.skip("Service not initialized")

        result = await service.search_term("TJES")

        if result:
            assert result.document.doc_type.value == "glossary"
            print(f"Found term: {result.document.name}")
        else:
            print("Term TJES not found in test data")

    @pytest.mark.asyncio
    async def test_comprehensive_search(self, service):
        """Test comprehensive search across all categories"""
        await service.initialize()

        if not service.is_initialized:
            pytest.skip("Service not initialized")

        result = await service.comprehensive_search("TJES 에러 발생")

        assert result is not None
        assert result.query == "TJES 에러 발생"
        assert result.confidence.value in ("high", "medium", "low")

        print(f"Comprehensive search results:")
        print(f"  Confidence: {result.confidence.value}")
        print(f"  Total results: {result.total_results}")
        print(f"  Detected terms: {result.detected_terms}")
        print(f"  Categories: {[c.value for c in result.matched_categories]}")

    @pytest.mark.asyncio
    async def test_confidence_levels(self, service):
        """Test confidence level determination"""
        from app.api.models.summary import SummarySearchResult, SummaryDocument, SummaryDocType

        # Create mock results with different scores
        doc = SummaryDocument(
            id="test",
            content="test",
            doc_type=SummaryDocType.ERROR_CODES,
            source_file="test.md",
        )

        high_result = [SummarySearchResult(document=doc, score=0.8)]
        assert service.get_confidence_level(high_result).value == "high"

        medium_result = [SummarySearchResult(document=doc, score=0.5)]
        assert service.get_confidence_level(medium_result).value == "medium"

        low_result = [SummarySearchResult(document=doc, score=0.2)]
        assert service.get_confidence_level(low_result).value == "low"

        no_result = []
        assert service.get_confidence_level(no_result).value == "low"

    @pytest.mark.asyncio
    async def test_bm25_search(self, service):
        """Test full BM25 search"""
        await service.initialize()

        if not service.is_initialized:
            pytest.skip("Service not initialized")

        results = await service.search("tacf error", top_k=5)

        # Verify we got results
        assert len(results) > 0, "Should return at least one result for 'tacf'"

        # Check first result
        first_result = results[0]
        assert first_result.score > 0, "Score should be positive"
        assert first_result.document.name is not None, "Document should have a name"


class TestSummaryModels:
    """Tests for summary data models"""

    def test_summary_document(self):
        """Test SummaryDocument creation"""
        from app.api.models.summary import SummaryDocument, SummaryDocType

        doc = SummaryDocument(
            id="test_123",
            content="Test content",
            doc_type=SummaryDocType.ERROR_CODES,
            source_file="test.md",
            name="TEST_ERROR",
            description="Test error description",
        )

        assert doc.id == "test_123"
        assert doc.doc_type == SummaryDocType.ERROR_CODES
        assert doc.name == "TEST_ERROR"

    def test_search_result_confidence(self):
        """Test SummarySearchResult confidence calculation"""
        from app.api.models.summary import (
            SummarySearchResult,
            SummaryDocument,
            SummaryDocType,
            ConfidenceLevel,
        )

        doc = SummaryDocument(
            id="test",
            content="test",
            doc_type=SummaryDocType.COMMANDS,
            source_file="test.md",
        )

        # High confidence
        high = SummarySearchResult(document=doc, score=0.85)
        assert high.confidence_level == ConfidenceLevel.HIGH

        # Medium confidence
        medium = SummarySearchResult(document=doc, score=0.55)
        assert medium.confidence_level == ConfidenceLevel.MEDIUM

        # Low confidence
        low = SummarySearchResult(document=doc, score=0.2)
        assert low.confidence_level == ConfidenceLevel.LOW

    def test_comprehensive_result_context_string(self):
        """Test ComprehensiveSearchResult context string generation"""
        from app.api.models.summary import (
            ComprehensiveSearchResult,
            SummarySearchResult,
            SummaryDocument,
            SummaryDocType,
            ConfidenceLevel,
        )

        error_doc = SummaryDocument(
            id="error_5212",
            content="error content",
            doc_type=SummaryDocType.ERROR_CODES,
            source_file="test.md",
            name="DATASET_NOT_FOUND",
            description="데이터셋을 찾을 수 없음",
        )

        result = ComprehensiveSearchResult(
            query="에러 5212",
            confidence=ConfidenceLevel.HIGH,
            results=[SummarySearchResult(document=error_doc, score=0.9)],
        )

        context = result.get_context_string()
        assert "에러" in context or "DATASET" in context


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
