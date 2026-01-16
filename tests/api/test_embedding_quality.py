"""
Tests for Embedding Quality Verification Service
"""
import pytest
import numpy as np
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Test imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.api.services.embedding_quality_service import (
    EmbeddingQualityService,
    EmbeddingQualityResult,
    SimilarityTestResult,
    QualityLevel,
    get_embedding_quality_service
)


class TestEmbeddingQualityService:
    """Test suite for EmbeddingQualityService"""

    @pytest.fixture
    def service(self):
        """Create a fresh service instance for each test"""
        return EmbeddingQualityService(top_k=5, min_similarity_threshold=0.5)

    @pytest.fixture
    def sample_chunks_with_embeddings(self):
        """Create sample chunks with embeddings for testing"""
        # Generate deterministic embeddings
        np.random.seed(42)

        chunks = []
        for i in range(5):
            # Create embeddings that are similar to each other
            base_embedding = np.random.randn(768).astype(np.float32)
            base_embedding = base_embedding / np.linalg.norm(base_embedding)

            chunks.append({
                "id": f"chunk_{i}",
                "index": i,
                "content": f"This is sample content for chunk {i}. It contains some text for testing.",
                "content_length": 50,
                "has_embedding": True,
                "embedding": base_embedding.tolist()
            })

        return chunks

    @pytest.fixture
    def diverse_chunks_with_embeddings(self):
        """Create diverse chunks with very different embeddings"""
        np.random.seed(123)

        chunks = []
        for i in range(5):
            # Create very different embeddings for each chunk
            embedding = np.zeros(768, dtype=np.float32)
            embedding[i * 150:(i + 1) * 150] = 1.0  # Different non-zero regions
            embedding = embedding / np.linalg.norm(embedding)

            chunks.append({
                "id": f"chunk_{i}",
                "index": i,
                "content": f"Completely different content {i}",
                "content_length": 30,
                "has_embedding": True,
                "embedding": embedding.tolist()
            })

        return chunks

    # ==========================================================================
    # Basic Functionality Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_verify_empty_chunks(self, service):
        """Test verification with empty chunks list"""
        result = await service.verify_document_embeddings(
            document_id="doc_123",
            chunks=[],
            sample_size=10
        )

        assert result.document_id == "doc_123"
        assert result.overall_score == 0.0
        assert result.quality_level == QualityLevel.POOR
        assert len(result.issues) > 0
        assert "No chunks available" in result.issues[0]

    @pytest.mark.asyncio
    async def test_verify_chunks_without_embeddings(self, service):
        """Test verification with chunks that have no embeddings"""
        chunks = [
            {"id": "chunk_1", "content": "Test content", "index": 0},
            {"id": "chunk_2", "content": "More content", "index": 1}
        ]

        result = await service.verify_document_embeddings(
            document_id="doc_456",
            chunks=chunks,
            sample_size=10
        )

        assert result.overall_score == 0.0
        assert result.quality_level == QualityLevel.POOR
        assert "No embeddings found" in result.issues[0]

    @pytest.mark.asyncio
    async def test_verify_with_valid_embeddings(self, service, sample_chunks_with_embeddings):
        """Test verification with valid embeddings"""
        result = await service.verify_document_embeddings(
            document_id="doc_789",
            chunks=sample_chunks_with_embeddings,
            sample_size=5
        )

        assert result.document_id == "doc_789"
        assert result.verified_at is not None
        assert 0.0 <= result.overall_score <= 1.0
        assert result.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD,
                                         QualityLevel.FAIR, QualityLevel.POOR]
        assert result.chunks_total == 5
        assert result.chunks_tested <= 5
        assert result.embedding_dimension == 768

    @pytest.mark.asyncio
    async def test_verify_with_external_embeddings(self, service):
        """Test verification with externally provided embeddings"""
        chunks = [
            {"id": "chunk_1", "content": "Test content 1", "index": 0},
            {"id": "chunk_2", "content": "Test content 2", "index": 1}
        ]

        # Provide embeddings separately
        np.random.seed(42)
        embeddings = [
            (np.random.randn(768) / 10).tolist(),
            (np.random.randn(768) / 10).tolist()
        ]

        result = await service.verify_document_embeddings(
            document_id="doc_external",
            chunks=chunks,
            embeddings=embeddings,
            sample_size=2
        )

        assert result.chunks_total == 2
        assert result.embedding_dimension == 768

    # ==========================================================================
    # Quality Level Tests
    # ==========================================================================

    def test_determine_quality_level_excellent(self, service):
        """Test quality level determination for excellent score"""
        assert service._determine_quality_level(0.85) == QualityLevel.EXCELLENT
        assert service._determine_quality_level(0.95) == QualityLevel.EXCELLENT
        assert service._determine_quality_level(1.0) == QualityLevel.EXCELLENT

    def test_determine_quality_level_good(self, service):
        """Test quality level determination for good score"""
        assert service._determine_quality_level(0.65) == QualityLevel.GOOD
        assert service._determine_quality_level(0.75) == QualityLevel.GOOD
        assert service._determine_quality_level(0.79) == QualityLevel.GOOD

    def test_determine_quality_level_fair(self, service):
        """Test quality level determination for fair score"""
        assert service._determine_quality_level(0.45) == QualityLevel.FAIR
        assert service._determine_quality_level(0.55) == QualityLevel.FAIR
        assert service._determine_quality_level(0.59) == QualityLevel.FAIR

    def test_determine_quality_level_poor(self, service):
        """Test quality level determination for poor score"""
        assert service._determine_quality_level(0.0) == QualityLevel.POOR
        assert service._determine_quality_level(0.25) == QualityLevel.POOR
        assert service._determine_quality_level(0.39) == QualityLevel.POOR

    # ==========================================================================
    # Similarity Computation Tests
    # ==========================================================================

    def test_compute_similarities_identical(self, service):
        """Test similarity computation with identical vectors"""
        vec = np.array([1.0, 0.0, 0.0])
        embeddings = [vec.tolist(), vec.tolist(), vec.tolist()]

        similarities = service._compute_similarities(vec.tolist(), embeddings)

        # All similarities should be 1.0 for identical vectors
        assert np.allclose(similarities, [1.0, 1.0, 1.0], atol=0.01)

    def test_compute_similarities_orthogonal(self, service):
        """Test similarity computation with orthogonal vectors"""
        vec1 = np.array([1.0, 0.0, 0.0])
        vec2 = np.array([0.0, 1.0, 0.0])
        vec3 = np.array([0.0, 0.0, 1.0])

        embeddings = [vec1.tolist(), vec2.tolist(), vec3.tolist()]

        similarities = service._compute_similarities(vec1.tolist(), embeddings)

        # First should be 1.0, others should be 0.0
        assert np.isclose(similarities[0], 1.0, atol=0.01)
        assert np.isclose(similarities[1], 0.0, atol=0.01)
        assert np.isclose(similarities[2], 0.0, atol=0.01)

    def test_compute_similarities_zero_vector(self, service):
        """Test similarity computation with zero vector"""
        zero_vec = [0.0, 0.0, 0.0]
        embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        similarities = service._compute_similarities(zero_vec, embeddings)

        # All similarities should be 0 for zero vector
        assert np.allclose(similarities, [0.0, 0.0])

    # ==========================================================================
    # Metrics Calculation Tests
    # ==========================================================================

    def test_calculate_metrics_empty(self, service):
        """Test metrics calculation with empty results"""
        metrics = service._calculate_metrics([], [])

        assert metrics["overall_score"] == 0.0
        assert metrics["retrieval_accuracy"] == 0.0
        assert metrics["avg_similarity"] == 0.0

    def test_calculate_metrics_all_hits(self, service):
        """Test metrics calculation with all hits"""
        test_results = [
            SimilarityTestResult(
                query="q1", expected_chunk_index=0, retrieved_chunk_index=0,
                similarity_score=0.95, is_hit=True
            ),
            SimilarityTestResult(
                query="q2", expected_chunk_index=1, retrieved_chunk_index=1,
                similarity_score=0.90, is_hit=True
            )
        ]

        # Create dummy embeddings
        np.random.seed(42)
        embeddings = [np.random.randn(768).tolist() for _ in range(2)]

        metrics = service._calculate_metrics(test_results, embeddings)

        assert metrics["retrieval_accuracy"] == 1.0  # All hits
        assert metrics["avg_similarity"] == 0.925  # (0.95 + 0.90) / 2

    def test_calculate_metrics_no_hits(self, service):
        """Test metrics calculation with no hits"""
        test_results = [
            SimilarityTestResult(
                query="q1", expected_chunk_index=0, retrieved_chunk_index=1,
                similarity_score=0.3, is_hit=False
            ),
            SimilarityTestResult(
                query="q2", expected_chunk_index=1, retrieved_chunk_index=0,
                similarity_score=0.25, is_hit=False
            )
        ]

        np.random.seed(42)
        embeddings = [np.random.randn(768).tolist() for _ in range(2)]

        metrics = service._calculate_metrics(test_results, embeddings)

        assert metrics["retrieval_accuracy"] == 0.0

    # ==========================================================================
    # Sample Selection Tests
    # ==========================================================================

    def test_select_test_indices_small_dataset(self, service):
        """Test index selection when dataset is smaller than sample size"""
        indices = service._select_test_indices(total_chunks=3, sample_size=10)

        assert indices == [0, 1, 2]

    def test_select_test_indices_large_dataset(self, service):
        """Test index selection for large dataset"""
        indices = service._select_test_indices(total_chunks=100, sample_size=10)

        assert len(indices) == 10
        # Indices should be evenly distributed
        assert indices[0] == 0
        assert indices[-1] == 90

    def test_select_test_indices_exact_size(self, service):
        """Test index selection when dataset equals sample size"""
        indices = service._select_test_indices(total_chunks=5, sample_size=5)

        assert indices == [0, 1, 2, 3, 4]

    # ==========================================================================
    # Result Analysis Tests
    # ==========================================================================

    def test_analyze_results_good_metrics(self, service):
        """Test analysis with good metrics"""
        metrics = {
            "overall_score": 0.85,
            "retrieval_accuracy": 0.9,
            "avg_similarity": 0.8,
            "similarity_std": 0.1,
            "coverage_score": 0.95
        }

        issues, recommendations = service._analyze_results(metrics, [])

        assert len(issues) == 0
        assert any("Excellent" in r or "acceptable" in r for r in recommendations)

    def test_analyze_results_low_accuracy(self, service):
        """Test analysis with low retrieval accuracy"""
        metrics = {
            "overall_score": 0.5,
            "retrieval_accuracy": 0.5,
            "avg_similarity": 0.7,
            "similarity_std": 0.15,
            "coverage_score": 0.85
        }

        issues, recommendations = service._analyze_results(metrics, [])

        assert "Low retrieval accuracy" in issues[0]
        assert any("chunk size" in r for r in recommendations)

    def test_analyze_results_low_similarity(self, service):
        """Test analysis with low average similarity"""
        metrics = {
            "overall_score": 0.45,
            "retrieval_accuracy": 0.8,
            "avg_similarity": 0.4,
            "similarity_std": 0.15,
            "coverage_score": 0.85
        }

        issues, recommendations = service._analyze_results(metrics, [])

        assert any("similarity" in i.lower() for i in issues)

    def test_analyze_results_high_variance(self, service):
        """Test analysis with high similarity variance"""
        metrics = {
            "overall_score": 0.6,
            "retrieval_accuracy": 0.8,
            "avg_similarity": 0.7,
            "similarity_std": 0.4,  # High variance
            "coverage_score": 0.85
        }

        issues, recommendations = service._analyze_results(metrics, [])

        assert any("variance" in i.lower() for i in issues)

    # ==========================================================================
    # Result Serialization Tests
    # ==========================================================================

    def test_result_to_dict(self):
        """Test EmbeddingQualityResult serialization"""
        result = EmbeddingQualityResult(
            document_id="doc_123",
            verified_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            overall_score=0.85,
            quality_level=QualityLevel.EXCELLENT,
            retrieval_accuracy=0.9,
            avg_similarity=0.85,
            similarity_std=0.1,
            coverage_score=0.95,
            embedding_dimension=768,
            chunks_tested=10,
            chunks_total=20,
            test_results=[],
            issues=[],
            recommendations=["Excellent quality"]
        )

        result_dict = result.to_dict()

        assert result_dict["document_id"] == "doc_123"
        assert result_dict["overall_score"] == 0.85
        assert result_dict["quality_level"] == "excellent"
        assert result_dict["embedding_dimension"] == 768
        assert result_dict["chunks_tested"] == 10
        assert "Excellent quality" in result_dict["recommendations"]

    # ==========================================================================
    # Integration Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_full_verification_flow(self, service, sample_chunks_with_embeddings):
        """Test complete verification flow"""
        result = await service.verify_document_embeddings(
            document_id="doc_integration",
            chunks=sample_chunks_with_embeddings,
            sample_size=5
        )

        # Verify all required fields
        assert result.document_id == "doc_integration"
        assert isinstance(result.verified_at, datetime)
        assert 0 <= result.overall_score <= 1
        assert result.quality_level in QualityLevel
        assert 0 <= result.retrieval_accuracy <= 1
        assert 0 <= result.avg_similarity <= 1
        assert result.similarity_std >= 0
        assert 0 <= result.coverage_score <= 1
        assert result.embedding_dimension > 0
        assert result.chunks_tested > 0
        assert result.chunks_total == 5

        # Verify serialization works
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)

    @pytest.mark.asyncio
    async def test_diverse_embeddings_lower_score(self, service, diverse_chunks_with_embeddings):
        """Test that diverse/isolated embeddings result in lower quality score"""
        result = await service.verify_document_embeddings(
            document_id="doc_diverse",
            chunks=diverse_chunks_with_embeddings,
            sample_size=5
        )

        # Diverse embeddings should have lower coverage
        assert result.coverage_score < 0.8  # Low coverage due to isolation

    # ==========================================================================
    # Singleton Tests
    # ==========================================================================

    def test_get_embedding_quality_service_singleton(self):
        """Test that get_embedding_quality_service returns singleton"""
        service1 = get_embedding_quality_service()
        service2 = get_embedding_quality_service()

        assert service1 is service2


class TestQualityLevel:
    """Tests for QualityLevel enum"""

    def test_quality_level_values(self):
        """Test QualityLevel enum values"""
        assert QualityLevel.EXCELLENT.value == "excellent"
        assert QualityLevel.GOOD.value == "good"
        assert QualityLevel.FAIR.value == "fair"
        assert QualityLevel.POOR.value == "poor"

    def test_quality_level_from_string(self):
        """Test creating QualityLevel from string"""
        assert QualityLevel("excellent") == QualityLevel.EXCELLENT
        assert QualityLevel("good") == QualityLevel.GOOD
        assert QualityLevel("fair") == QualityLevel.FAIR
        assert QualityLevel("poor") == QualityLevel.POOR


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
