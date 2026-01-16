"""
Tests for Embedding Quality API Endpoints
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


class TestEmbeddingQualityAPI:
    """Test suite for embedding quality API endpoints"""

    @pytest.fixture
    def mock_current_user(self):
        """Mock authenticated user"""
        return {
            "id": "user_123",
            "username": "testuser",
            "email": "test@example.com",
            "role": "user"
        }

    @pytest.fixture
    def mock_document_ready(self):
        """Mock document with completed embeddings"""
        return {
            "id": "doc_123",
            "filename": "test.pdf",
            "original_name": "test.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
            "document_type": "pdf",
            "status": "ready",
            "chunks_count": 10,
            "entities_count": 5,
            "embedding_status": "completed",
            "language": "auto",
            "processing_mode": "text_only",
            "vlm_processed": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "tags": [],
            "stats": {
                "pages": 5,
                "chunks_count": 10,
                "entities_count": 5,
                "avg_chunk_size": 500,
                "embedding_dimension": 768,
                "images_count": 0,
                "tables_count": 0,
                "figures_count": 0,
                "vlm_processed": False
            }
        }

    @pytest.fixture
    def mock_quality_result(self):
        """Mock quality verification result"""
        return {
            "document_id": "doc_123",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "overall_score": 0.85,
            "quality_level": "excellent",
            "retrieval_accuracy": 0.9,
            "avg_similarity": 0.85,
            "similarity_std": 0.1,
            "coverage_score": 0.95,
            "embedding_dimension": 768,
            "chunks_tested": 10,
            "chunks_total": 10,
            "test_results": [
                {
                    "query": "Test query...",
                    "expected_chunk_index": 0,
                    "retrieved_chunk_index": 0,
                    "similarity_score": 0.95,
                    "is_hit": True
                }
            ],
            "issues": [],
            "recommendations": ["Excellent embedding quality - no improvements needed"]
        }

    def test_quality_models_import(self):
        """Test that quality models can be imported"""
        from app.api.models.document import (
            QualityLevel,
            SimilarityTestResult,
            EmbeddingQualityMetrics,
            EmbeddingQualityResponse,
            EmbeddingQualitySummary
        )

        # Verify enum values
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.FAIR.value == "fair"
        assert QualityLevel.POOR.value == "poor"

    def test_quality_metrics_model(self):
        """Test EmbeddingQualityMetrics model validation"""
        from app.api.models.document import EmbeddingQualityMetrics, QualityLevel

        metrics = EmbeddingQualityMetrics(
            overall_score=0.85,
            quality_level=QualityLevel.EXCELLENT,
            retrieval_accuracy=0.9,
            avg_similarity=0.85,
            similarity_std=0.1,
            coverage_score=0.95
        )

        assert metrics.overall_score == 0.85
        assert metrics.quality_level == QualityLevel.EXCELLENT

    def test_quality_response_model(self):
        """Test EmbeddingQualityResponse model"""
        from app.api.models.document import (
            EmbeddingQualityResponse,
            EmbeddingQualityMetrics,
            QualityLevel,
            SimilarityTestResult
        )

        metrics = EmbeddingQualityMetrics(
            overall_score=0.85,
            quality_level=QualityLevel.EXCELLENT,
            retrieval_accuracy=0.9,
            avg_similarity=0.85,
            similarity_std=0.1,
            coverage_score=0.95
        )

        response = EmbeddingQualityResponse(
            document_id="doc_123",
            verified_at=datetime.now(timezone.utc),
            metrics=metrics,
            embedding_dimension=768,
            chunks_tested=10,
            chunks_total=20,
            test_results=[],
            issues=[],
            recommendations=["Good quality"]
        )

        assert response.document_id == "doc_123"
        assert response.metrics.overall_score == 0.85
        assert response.embedding_dimension == 768

    def test_quality_summary_model(self):
        """Test EmbeddingQualitySummary model"""
        from app.api.models.document import EmbeddingQualitySummary, QualityLevel

        summary = EmbeddingQualitySummary(
            overall_score=0.75,
            quality_level=QualityLevel.GOOD,
            verified_at=datetime.now(timezone.utc),
            has_issues=False
        )

        assert summary.overall_score == 0.75
        assert summary.quality_level == QualityLevel.GOOD
        assert not summary.has_issues

    def test_similarity_test_result_model(self):
        """Test SimilarityTestResult model"""
        from app.api.models.document import SimilarityTestResult

        result = SimilarityTestResult(
            query="Test query...",
            expected_chunk_index=0,
            retrieved_chunk_index=0,
            similarity_score=0.95,
            is_hit=True
        )

        assert result.query == "Test query..."
        assert result.is_hit is True
        assert result.similarity_score == 0.95


class TestDocumentServiceQualityMethods:
    """Test DocumentService quality verification methods"""

    @pytest.fixture
    def document_service(self):
        """Get DocumentService instance"""
        from app.api.core.deps import DocumentService
        return DocumentService()

    @pytest.mark.asyncio
    async def test_create_empty_quality_result(self, document_service):
        """Test creating empty quality result"""
        result = document_service._create_empty_quality_result(
            document_id="doc_test",
            reason="Test reason"
        )

        assert result["document_id"] == "doc_test"
        assert result["overall_score"] == 0.0
        assert result["quality_level"] == "poor"
        assert "Test reason" in result["issues"]

    @pytest.mark.asyncio
    async def test_verify_embedding_quality_no_document(self, document_service):
        """Test quality verification with non-existent document"""
        result = await document_service.verify_embedding_quality(
            document_id="nonexistent_doc",
            sample_size=10
        )

        # Should return None for non-existent document
        assert result is None

    @pytest.mark.asyncio
    async def test_get_embedding_quality_no_result(self, document_service):
        """Test getting quality when no verification has been done"""
        result = await document_service.get_embedding_quality(
            document_id="doc_no_quality"
        )

        # Should return None if no quality result exists
        assert result is None


class TestRouterImports:
    """Test that router imports work correctly"""

    def test_router_quality_imports(self):
        """Test that quality-related imports in router work"""
        from app.api.routers.documents import (
            EmbeddingQualityResponse,
            EmbeddingQualityMetrics,
            QualityLevel,
            SimilarityTestResult
        )

        # Verify imports work
        assert EmbeddingQualityResponse is not None
        assert EmbeddingQualityMetrics is not None
        assert QualityLevel is not None
        assert SimilarityTestResult is not None

    def test_router_endpoints_exist(self):
        """Test that quality endpoints are registered in router"""
        from app.api.routers.documents import router

        # Get all routes
        routes = [route.path for route in router.routes]

        # Check that quality endpoints exist (routes are relative to router prefix)
        # The router uses prefix="/documents", so paths are relative
        quality_endpoints_found = sum(
            1 for route in routes
            if "verify-embedding" in route or "embedding-quality" in route
        )
        assert quality_endpoints_found >= 2, f"Expected at least 2 quality endpoints, found {quality_endpoints_found}. Routes: {routes}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
