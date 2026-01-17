"""
Adaptive Quality Evaluator Service
적응형 품질 평가 서비스

Evaluates embedding quality with focus on retrieval accuracy and hallucination detection.
"""
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..models.adaptive_chunk import (
    AdaptiveChunk,
    QualityMetrics,
    QualityLevel,
)
from ..ports.adaptive_embedding_port import AdaptiveQualityEvaluatorPort
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


class AdaptiveQualityEvaluator(AdaptiveQualityEvaluatorPort):
    """
    Evaluates embedding quality for adaptive chunks.
    적응형 청크의 임베딩 품질 평가
    """

    def __init__(
        self,
        min_similarity_threshold: float = None,
        top_k_default: int = None,
        excellent_threshold: float = None,
        good_threshold: float = None,
        fair_threshold: float = None
    ):
        """
        Initialize evaluator.

        Args:
            min_similarity_threshold: Minimum similarity for retrieval (uses settings if None)
            top_k_default: Default K for top-k metrics (uses settings if None)
            excellent_threshold: Score threshold for excellent quality (uses settings if None)
            good_threshold: Score threshold for good quality (uses settings if None)
            fair_threshold: Score threshold for fair quality (uses settings if None)
        """
        # Only load settings if any parameter needs default value
        needs_settings = any(p is None for p in [
            min_similarity_threshold, top_k_default,
            excellent_threshold, good_threshold, fair_threshold
        ])

        if needs_settings:
            settings = get_settings()
            adaptive = settings.adaptive_embedding
            self.min_similarity_threshold = (
                min_similarity_threshold
                if min_similarity_threshold is not None
                else adaptive.quality_min_similarity
            )
            self.top_k_default = top_k_default if top_k_default is not None else adaptive.quality_top_k
            self.excellent_threshold = (
                excellent_threshold
                if excellent_threshold is not None
                else adaptive.quality_excellent_threshold
            )
            self.good_threshold = (
                good_threshold
                if good_threshold is not None
                else adaptive.quality_good_threshold
            )
            self.fair_threshold = (
                fair_threshold
                if fair_threshold is not None
                else adaptive.quality_fair_threshold
            )
        else:
            self.min_similarity_threshold = min_similarity_threshold
            self.top_k_default = top_k_default
            self.excellent_threshold = excellent_threshold
            self.good_threshold = good_threshold
            self.fair_threshold = fair_threshold

    async def evaluate_quality(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk],
        sample_size: int = 10
    ) -> QualityMetrics:
        """
        Evaluate embedding quality for a document.
        """
        if not chunks:
            logger.warning(f"QUALITY_DEBUG: No chunks received for {pdf_id}")
            return self._create_empty_metrics()

        # Debug: Check chunk status before filtering
        logger.info(f"QUALITY_DEBUG: Received {len(chunks)} chunks for {pdf_id}")
        has_embedding_count = sum(1 for c in chunks if c.has_embedding)
        has_actual_embedding = sum(1 for c in chunks if c.embedding is not None and len(c.embedding) > 0)
        logger.info(f"QUALITY_DEBUG: has_embedding={has_embedding_count}, actual_embedding={has_actual_embedding}")

        # Sample first 3 chunks
        for i, c in enumerate(chunks[:3]):
            emb_len = len(c.embedding) if c.embedding else 0
            logger.info(f"QUALITY_DEBUG: Chunk[{i}] has_embedding={c.has_embedding}, embedding_len={emb_len}, _db_has={c._db_has_embedding}")

        # Filter chunks with embeddings
        embedded_chunks = [c for c in chunks if c.has_embedding and c.embedding]
        logger.info(f"QUALITY_DEBUG: After filter: {len(embedded_chunks)} embedded chunks")
        if not embedded_chunks:
            return self._create_empty_metrics()

        # Select sample for evaluation
        sample_chunks = self._select_sample(embedded_chunks, sample_size)

        # Compute metrics
        top_k_recall = await self.compute_top_k_recall(embedded_chunks, self.top_k_default)
        section_precision = await self.compute_section_precision(embedded_chunks)

        # Compute average similarity
        avg_similarity = self._compute_avg_similarity(sample_chunks, embedded_chunks)

        # Detect hallucination issues
        hallucination_results = []
        for chunk in sample_chunks[:5]:  # Check first 5 samples
            retrieved = self._retrieve_similar(chunk, embedded_chunks, k=3)
            hallucination = await self.detect_hallucination(chunk, retrieved)
            if hallucination.get("hallucination_detected"):
                hallucination_results.append(hallucination)

        hallucination_detected = len(hallucination_results) > 0

        # Determine quality level
        overall_score = (top_k_recall * 0.4 + section_precision * 0.4 + avg_similarity * 0.2)
        quality_level = self._determine_quality_level(overall_score)

        return QualityMetrics(
            top_k_recall=top_k_recall,
            section_precision=section_precision,
            avg_similarity=avg_similarity,
            embedding_dimension=len(embedded_chunks[0].embedding) if embedded_chunks[0].embedding else 0,
            quality_level=quality_level,
            hallucination_detected=hallucination_detected,
            hallucination_details=[h.get("details", "") for h in hallucination_results]
        )

    async def compute_top_k_recall(
        self,
        chunks: List[AdaptiveChunk],
        k: int = 5
    ) -> float:
        """
        Compute Top-K recall metric.
        Tests if each chunk can retrieve itself in top-k results.
        """
        if len(chunks) < 2:
            return 1.0

        hits = 0
        tested = 0

        for chunk in chunks:
            if not chunk.embedding:
                continue

            # Retrieve top-k similar chunks
            retrieved = self._retrieve_similar(chunk, chunks, k=k)
            retrieved_ids = [c.chunk_id for c in retrieved]

            # Check if self is in top-k
            if chunk.chunk_id in retrieved_ids:
                hits += 1
            tested += 1

        return hits / tested if tested > 0 else 0.0

    async def compute_section_precision(
        self,
        chunks: List[AdaptiveChunk]
    ) -> float:
        """
        Compute section precision metric.
        Checks if retrieved chunks are from the same section.
        """
        if len(chunks) < 2:
            return 1.0

        # Group chunks by section
        section_chunks = defaultdict(list)
        for chunk in chunks:
            section = chunk.section_path or "no_section"
            section_chunks[section].append(chunk)

        # For each chunk with a section, check if retrieved chunks are from same section
        correct = 0
        tested = 0

        for chunk in chunks:
            if not chunk.embedding or not chunk.section_path:
                continue

            # Retrieve top-3 similar chunks (excluding self)
            retrieved = self._retrieve_similar(chunk, chunks, k=4)
            retrieved_other = [c for c in retrieved if c.chunk_id != chunk.chunk_id][:3]

            if not retrieved_other:
                continue

            # Check how many are from the same section or parent section
            same_section = 0
            for r_chunk in retrieved_other:
                if r_chunk.section_path:
                    # Same section or parent-child relationship
                    if (r_chunk.section_path == chunk.section_path or
                        r_chunk.section_path.startswith(chunk.section_path + ".") or
                        chunk.section_path.startswith(r_chunk.section_path + ".")):
                        same_section += 1

            correct += same_section / len(retrieved_other)
            tested += 1

        return correct / tested if tested > 0 else 1.0

    async def detect_hallucination(
        self,
        chunk: AdaptiveChunk,
        retrieved_chunks: List[AdaptiveChunk]
    ) -> Dict[str, Any]:
        """
        Detect potential hallucination issues.
        Checks for page mismatch and section leakage.
        """
        if not retrieved_chunks:
            return {"hallucination_detected": False}

        issues = []

        # Check page mismatch
        # If a chunk retrieves content from very different pages, might indicate issues
        chunk_pages = set(range(chunk.page_start, chunk.page_end + 1))
        for r_chunk in retrieved_chunks:
            if r_chunk.chunk_id == chunk.chunk_id:
                continue
            r_pages = set(range(r_chunk.page_start, r_chunk.page_end + 1))

            # If pages don't overlap and are far apart
            if not chunk_pages & r_pages:
                min_dist = min(abs(p1 - p2) for p1 in chunk_pages for p2 in r_pages)
                if min_dist > 10:
                    issues.append(f"Page mismatch: chunk pages {chunk_pages} vs retrieved {r_pages}")

        # Check section leakage
        # If chunk has a specific section but retrieves from unrelated sections
        if chunk.section_path:
            for r_chunk in retrieved_chunks:
                if r_chunk.chunk_id == chunk.chunk_id:
                    continue
                if r_chunk.section_path:
                    # Check if sections are related
                    if not (r_chunk.section_path.startswith(chunk.section_path.split('.')[0]) or
                            chunk.section_path.startswith(r_chunk.section_path.split('.')[0])):
                        issues.append(
                            f"Section leakage: {chunk.section_path} retrieved {r_chunk.section_path}"
                        )

        return {
            "hallucination_detected": len(issues) > 0,
            "issues": issues,
            "details": "; ".join(issues) if issues else ""
        }

    def _select_sample(
        self,
        chunks: List[AdaptiveChunk],
        sample_size: int
    ) -> List[AdaptiveChunk]:
        """Select a representative sample of chunks."""
        if len(chunks) <= sample_size:
            return chunks

        # Select evenly distributed samples
        step = len(chunks) / sample_size
        indices = [int(i * step) for i in range(sample_size)]
        return [chunks[i] for i in indices]

    def _retrieve_similar(
        self,
        query_chunk: AdaptiveChunk,
        chunks: List[AdaptiveChunk],
        k: int = 5
    ) -> List[AdaptiveChunk]:
        """Retrieve top-k similar chunks."""
        if not query_chunk.embedding:
            return []

        # Compute similarities
        similarities = []
        query_vec = np.array(query_chunk.embedding)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        for chunk in chunks:
            if not chunk.embedding:
                continue

            chunk_vec = np.array(chunk.embedding)
            chunk_norm = np.linalg.norm(chunk_vec)

            if chunk_norm == 0:
                similarities.append((chunk, 0.0))
            else:
                sim = np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm)
                similarities.append((chunk, sim))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top-k
        return [chunk for chunk, _ in similarities[:k]]

    def _compute_avg_similarity(
        self,
        sample_chunks: List[AdaptiveChunk],
        all_chunks: List[AdaptiveChunk]
    ) -> float:
        """Compute average similarity for sample chunks."""
        if not sample_chunks:
            return 0.0

        total_sim = 0.0
        count = 0

        for chunk in sample_chunks:
            if not chunk.embedding:
                continue

            # Get top-3 similar (excluding self)
            retrieved = self._retrieve_similar(chunk, all_chunks, k=4)
            other_chunks = [c for c in retrieved if c.chunk_id != chunk.chunk_id][:3]

            if other_chunks:
                # Compute average similarity to top matches
                query_vec = np.array(chunk.embedding)
                query_norm = np.linalg.norm(query_vec)

                for other in other_chunks:
                    if other.embedding:
                        other_vec = np.array(other.embedding)
                        other_norm = np.linalg.norm(other_vec)
                        if query_norm > 0 and other_norm > 0:
                            sim = np.dot(query_vec, other_vec) / (query_norm * other_norm)
                            total_sim += sim
                            count += 1

        return total_sim / count if count > 0 else 0.0

    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Determine quality level from score."""
        if score >= self.excellent_threshold:
            return QualityLevel.EXCELLENT
        elif score >= self.good_threshold:
            return QualityLevel.GOOD
        elif score >= self.fair_threshold:
            return QualityLevel.FAIR
        else:
            return QualityLevel.POOR

    def _create_empty_metrics(self) -> QualityMetrics:
        """Create empty metrics for documents without embeddings."""
        return QualityMetrics(
            top_k_recall=0.0,
            section_precision=0.0,
            avg_similarity=0.0,
            embedding_dimension=0,
            quality_level=QualityLevel.POOR,
            hallucination_detected=False,
            hallucination_details=[]
        )

    async def generate_quality_report(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk]
    ) -> str:
        """
        Generate a human-readable quality report.
        """
        metrics = await self.evaluate_quality(pdf_id, chunks)

        report_lines = [
            f"=== Embedding Quality Report for {pdf_id} ===",
            f"",
            f"Quality Level: {metrics.quality_level.value.upper()}",
            f"",
            f"Metrics:",
            f"  - Top-K Recall:       {metrics.top_k_recall:.2%}",
            f"  - Section Precision:  {metrics.section_precision:.2%}",
            f"  - Average Similarity: {metrics.avg_similarity:.3f}",
            f"  - Embedding Dimension: {metrics.embedding_dimension}",
            f"",
            f"Hallucination Detection:",
            f"  - Detected: {'Yes' if metrics.hallucination_detected else 'No'}"
        ]

        if metrics.hallucination_details:
            report_lines.append(f"  - Details:")
            for detail in metrics.hallucination_details:
                report_lines.append(f"    * {detail}")

        # Recommendations
        report_lines.append(f"")
        report_lines.append(f"Recommendations:")

        if metrics.top_k_recall < 0.8:
            report_lines.append(f"  - Consider adjusting chunk sizes for better self-retrieval")

        if metrics.section_precision < 0.8:
            report_lines.append(f"  - Section boundaries may need refinement")

        if metrics.avg_similarity < 0.5:
            report_lines.append(f"  - Document may contain very diverse content")

        if metrics.hallucination_detected:
            report_lines.append(f"  - Review chunks with potential hallucination issues")

        if metrics.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD]:
            report_lines.append(f"  - Quality is acceptable, no immediate action needed")

        return "\n".join(report_lines)


# Singleton instance
_evaluator: Optional[AdaptiveQualityEvaluator] = None


def get_adaptive_quality_evaluator() -> AdaptiveQualityEvaluator:
    """Get or create adaptive quality evaluator instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = AdaptiveQualityEvaluator()
    return _evaluator
