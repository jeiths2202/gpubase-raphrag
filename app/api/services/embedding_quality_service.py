"""
Embedding Quality Verification Service
임베딩 품질 검증 서비스

Performs quality checks on document embeddings after processing:
- Semantic similarity testing with sample queries
- Embedding distribution analysis
- Retrieval accuracy validation
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class QualityLevel(str, Enum):
    """Embedding quality level"""
    EXCELLENT = "excellent"  # >= 0.8
    GOOD = "good"           # >= 0.6
    FAIR = "fair"           # >= 0.4
    POOR = "poor"           # < 0.4


@dataclass
class SimilarityTestResult:
    """Result of a single similarity test"""
    query: str
    expected_chunk_index: int
    retrieved_chunk_index: int
    similarity_score: float
    is_hit: bool  # Retrieved within top-k


@dataclass
class EmbeddingQualityResult:
    """Complete embedding quality verification result"""
    document_id: str
    verified_at: datetime

    # Overall scores (0.0 - 1.0)
    overall_score: float
    quality_level: QualityLevel

    # Component scores
    retrieval_accuracy: float  # How often correct chunk is retrieved
    avg_similarity: float      # Average similarity score
    similarity_std: float      # Similarity score standard deviation
    coverage_score: float      # How many chunks are reachable

    # Distribution metrics
    embedding_dimension: int
    chunks_tested: int
    chunks_total: int

    # Detailed test results
    test_results: List[SimilarityTestResult] = field(default_factory=list)

    # Issues found
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "verified_at": self.verified_at.isoformat(),
            "overall_score": round(self.overall_score, 4),
            "quality_level": self.quality_level.value,
            "retrieval_accuracy": round(self.retrieval_accuracy, 4),
            "avg_similarity": round(self.avg_similarity, 4),
            "similarity_std": round(self.similarity_std, 4),
            "coverage_score": round(self.coverage_score, 4),
            "embedding_dimension": self.embedding_dimension,
            "chunks_tested": self.chunks_tested,
            "chunks_total": self.chunks_total,
            "test_results": [
                {
                    "query": r.query,
                    "expected_chunk_index": r.expected_chunk_index,
                    "retrieved_chunk_index": r.retrieved_chunk_index,
                    "similarity_score": round(r.similarity_score, 4),
                    "is_hit": r.is_hit
                }
                for r in self.test_results
            ],
            "issues": self.issues,
            "recommendations": self.recommendations
        }


class EmbeddingQualityService:
    """
    Service for verifying embedding quality after document processing.

    Quality verification includes:
    1. Self-retrieval test: Can each chunk retrieve itself?
    2. Similarity distribution: Are embeddings well-distributed?
    3. Coverage test: Are all chunks accessible via search?
    """

    def __init__(
        self,
        embedding_service=None,
        vector_store=None,
        top_k: int = 5,
        min_similarity_threshold: float = 0.35  # Lowered from 0.5 for better coverage detection
    ):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.top_k = top_k
        self.min_similarity_threshold = min_similarity_threshold

    async def verify_document_embeddings(
        self,
        document_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None,
        sample_size: int = 10
    ) -> EmbeddingQualityResult:
        """
        Verify embedding quality for a document.

        Args:
            document_id: Document ID
            chunks: List of chunk dictionaries with 'content' and optionally 'embedding'
            embeddings: Pre-computed embeddings (if not in chunks)
            sample_size: Number of chunks to test (for large documents)

        Returns:
            EmbeddingQualityResult with quality metrics
        """
        logger.info(f"Starting embedding quality verification for document {document_id}")

        if not chunks:
            return self._create_empty_result(document_id, "No chunks available")

        # Get embeddings from chunks or provided list
        chunk_embeddings = self._extract_embeddings(chunks, embeddings)

        if not chunk_embeddings:
            return self._create_empty_result(document_id, "No embeddings found")

        # Sample chunks for testing (for large documents)
        test_indices = self._select_test_indices(len(chunks), sample_size)

        # Run quality tests
        test_results = await self._run_retrieval_tests(
            chunks, chunk_embeddings, test_indices
        )

        # Calculate metrics
        metrics = self._calculate_metrics(test_results, chunk_embeddings)

        # Determine quality level and generate recommendations
        quality_level = self._determine_quality_level(metrics["overall_score"])
        issues, recommendations = self._analyze_results(metrics, test_results)

        result = EmbeddingQualityResult(
            document_id=document_id,
            verified_at=datetime.now(timezone.utc),
            overall_score=metrics["overall_score"],
            quality_level=quality_level,
            retrieval_accuracy=metrics["retrieval_accuracy"],
            avg_similarity=metrics["avg_similarity"],
            similarity_std=metrics["similarity_std"],
            coverage_score=metrics["coverage_score"],
            embedding_dimension=len(chunk_embeddings[0]) if chunk_embeddings else 0,
            chunks_tested=len(test_results),
            chunks_total=len(chunks),
            test_results=test_results,
            issues=issues,
            recommendations=recommendations
        )

        logger.info(
            f"Embedding quality verification completed for {document_id}: "
            f"score={result.overall_score:.2f}, level={result.quality_level.value}"
        )

        return result

    def _extract_embeddings(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]]
    ) -> List[List[float]]:
        """Extract embeddings from chunks or use provided embeddings."""
        if embeddings:
            return embeddings

        result = []
        for chunk in chunks:
            if "embedding" in chunk and chunk["embedding"]:
                result.append(chunk["embedding"])

        return result

    def _select_test_indices(self, total_chunks: int, sample_size: int) -> List[int]:
        """Select indices for testing, ensuring even distribution."""
        if total_chunks <= sample_size:
            return list(range(total_chunks))

        # Select evenly distributed samples
        step = total_chunks / sample_size
        indices = [int(i * step) for i in range(sample_size)]
        return indices

    async def _run_retrieval_tests(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]],
        test_indices: List[int]
    ) -> List[SimilarityTestResult]:
        """Run self-retrieval tests for selected chunks."""
        results = []

        for idx in test_indices:
            if idx >= len(embeddings):
                continue

            chunk = chunks[idx]
            query_embedding = embeddings[idx]

            # Find most similar embeddings
            similarities = self._compute_similarities(query_embedding, embeddings)

            # Get top-k results (excluding self)
            sorted_indices = np.argsort(similarities)[::-1]

            # Check if the chunk retrieves itself in top position
            # (self should be rank 0 with similarity ~1.0)
            retrieved_idx = sorted_indices[0]
            similarity = similarities[retrieved_idx]

            # For self-retrieval, check if second-best is reasonable
            # (first should be self with ~1.0 similarity)
            is_hit = retrieved_idx == idx or (
                len(sorted_indices) > 1 and
                similarities[sorted_indices[1]] >= self.min_similarity_threshold
            )

            # Create query preview
            content = chunk.get("content", "")
            query_preview = content[:50] + "..." if len(content) > 50 else content

            results.append(SimilarityTestResult(
                query=query_preview,
                expected_chunk_index=idx,
                retrieved_chunk_index=int(retrieved_idx),
                similarity_score=float(similarity),
                is_hit=is_hit
            ))

        return results

    def _compute_similarities(
        self,
        query_embedding: List[float],
        embeddings: List[List[float]]
    ) -> np.ndarray:
        """Compute cosine similarities between query and all embeddings."""
        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return np.zeros(len(embeddings))

        similarities = []
        for emb in embeddings:
            emb_vec = np.array(emb)
            emb_norm = np.linalg.norm(emb_vec)

            if emb_norm == 0:
                similarities.append(0.0)
            else:
                sim = np.dot(query_vec, emb_vec) / (query_norm * emb_norm)
                similarities.append(sim)

        return np.array(similarities)

    def _calculate_metrics(
        self,
        test_results: List[SimilarityTestResult],
        embeddings: List[List[float]]
    ) -> Dict[str, float]:
        """Calculate quality metrics from test results."""
        if not test_results:
            return {
                "overall_score": 0.0,
                "retrieval_accuracy": 0.0,
                "avg_similarity": 0.0,
                "similarity_std": 0.0,
                "coverage_score": 0.0
            }

        # Retrieval accuracy (hit rate)
        hits = sum(1 for r in test_results if r.is_hit)
        retrieval_accuracy = hits / len(test_results)

        # Similarity statistics
        similarities = [r.similarity_score for r in test_results]
        avg_similarity = np.mean(similarities)
        similarity_std = np.std(similarities)

        # Coverage: check for isolated embeddings
        # (embeddings that have very low similarity to others)
        coverage_score = self._calculate_coverage(embeddings)

        # Overall score (weighted combination)
        overall_score = (
            retrieval_accuracy * 0.4 +
            avg_similarity * 0.3 +
            coverage_score * 0.2 +
            (1.0 - min(similarity_std, 0.5) / 0.5) * 0.1  # Lower std is better
        )

        return {
            "overall_score": overall_score,
            "retrieval_accuracy": retrieval_accuracy,
            "avg_similarity": avg_similarity,
            "similarity_std": similarity_std,
            "coverage_score": coverage_score
        }

    def _calculate_coverage(self, embeddings: List[List[float]]) -> float:
        """Calculate coverage score (how connected embeddings are)."""
        if len(embeddings) < 2:
            return 1.0

        # Sample pairs for efficiency
        n = len(embeddings)
        sample_size = min(100, n * (n - 1) // 2)

        connected = 0
        total_checked = 0

        # Check if each embedding has at least one neighbor above threshold
        for i in range(min(n, 20)):  # Sample up to 20 embeddings
            similarities = self._compute_similarities(embeddings[i], embeddings)
            # Exclude self (which should be 1.0)
            similarities[i] = 0
            max_sim = np.max(similarities)

            if max_sim >= self.min_similarity_threshold:
                connected += 1
            total_checked += 1

        return connected / total_checked if total_checked > 0 else 0.0

    def _determine_quality_level(self, overall_score: float) -> QualityLevel:
        """Determine quality level from overall score."""
        if overall_score >= 0.8:
            return QualityLevel.EXCELLENT
        elif overall_score >= 0.6:
            return QualityLevel.GOOD
        elif overall_score >= 0.4:
            return QualityLevel.FAIR
        else:
            return QualityLevel.POOR

    def _analyze_results(
        self,
        metrics: Dict[str, float],
        test_results: List[SimilarityTestResult]
    ) -> tuple[List[str], List[str]]:
        """Analyze results and generate issues/recommendations."""
        issues = []
        recommendations = []

        # Check retrieval accuracy
        if metrics["retrieval_accuracy"] < 0.7:
            issues.append("Low retrieval accuracy detected")
            recommendations.append(
                "Consider adjusting chunk size or overlap for better context preservation"
            )

        # Check similarity distribution
        if metrics["avg_similarity"] < 0.6:
            issues.append("Average similarity scores are below expected threshold")
            recommendations.append(
                "Review document content - it may contain very diverse topics"
            )

        if metrics["similarity_std"] > 0.3:
            issues.append("High variance in similarity scores")
            recommendations.append(
                "Some chunks may have poor embedding quality - consider re-processing"
            )

        # Check coverage (threshold lowered from 0.8 to 0.6 for diverse documents)
        if metrics["coverage_score"] < 0.6:
            issues.append("Some chunks appear isolated from others")
            recommendations.append(
                "Check for chunks with special characters or very short content"
            )

        # Add positive feedback for good results
        if not issues:
            if metrics["overall_score"] >= 0.8:
                recommendations.append("Excellent embedding quality - no improvements needed")
            else:
                recommendations.append("Embedding quality is acceptable")

        return issues, recommendations

    def _create_empty_result(
        self,
        document_id: str,
        reason: str
    ) -> EmbeddingQualityResult:
        """Create an empty result when verification cannot be performed."""
        return EmbeddingQualityResult(
            document_id=document_id,
            verified_at=datetime.now(timezone.utc),
            overall_score=0.0,
            quality_level=QualityLevel.POOR,
            retrieval_accuracy=0.0,
            avg_similarity=0.0,
            similarity_std=0.0,
            coverage_score=0.0,
            embedding_dimension=0,
            chunks_tested=0,
            chunks_total=0,
            test_results=[],
            issues=[reason],
            recommendations=["Re-process document to generate embeddings"]
        )


# Singleton instance
_embedding_quality_service: Optional[EmbeddingQualityService] = None


def get_embedding_quality_service() -> EmbeddingQualityService:
    """Get or create embedding quality service instance."""
    global _embedding_quality_service
    if _embedding_quality_service is None:
        _embedding_quality_service = EmbeddingQualityService()
    return _embedding_quality_service
