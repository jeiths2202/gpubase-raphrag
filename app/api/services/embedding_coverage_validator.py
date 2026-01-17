"""
Embedding Coverage Validator Service
임베딩 커버리지 검증 서비스

Validates that all content types are properly embedded.
"""
import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..models.adaptive_chunk import (
    AdaptiveChunk,
    ChunkType,
    CoverageReport,
)
from ..ports.adaptive_embedding_port import EmbeddingCoverageValidatorPort
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


class EmbeddingCoverageValidator(EmbeddingCoverageValidatorPort):
    """
    Validates embedding coverage for adaptive chunks.
    적응형 청크의 임베딩 커버리지 검증
    """

    def __init__(
        self,
        min_coverage_threshold: float = None,
        warn_on_low_coverage: bool = None
    ):
        """
        Initialize validator.

        Args:
            min_coverage_threshold: Minimum acceptable coverage 0-1 (uses settings if None)
            warn_on_low_coverage: Log warning if coverage is below threshold (uses settings if None)
        """
        # Only load settings if any parameter needs default value
        needs_settings = min_coverage_threshold is None or warn_on_low_coverage is None

        if needs_settings:
            settings = get_settings()
            adaptive = settings.adaptive_embedding
            self.min_coverage_threshold = (
                min_coverage_threshold
                if min_coverage_threshold is not None
                else adaptive.min_coverage_threshold
            )
            self.warn_on_low_coverage = (
                warn_on_low_coverage
                if warn_on_low_coverage is not None
                else adaptive.warn_on_low_coverage
            )
        else:
            self.min_coverage_threshold = min_coverage_threshold
            self.warn_on_low_coverage = warn_on_low_coverage

    async def validate_coverage(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk]
    ) -> CoverageReport:
        """
        Validate embedding coverage for a document.
        """
        if not chunks:
            logger.warning(f"VALIDATOR_DEBUG: Empty chunks list for {pdf_id}")
            return CoverageReport(
                total_chunks=0,
                embedded_chunks=0,
                failed_chunks=[],
                skipped_chunks=[],
                by_type={}
            )

        # Debug log input
        logger.info(f"VALIDATOR_DEBUG: Received {len(chunks)} chunks for {pdf_id}")

        # Count by type
        by_type: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "embedded": 0})
        failed_chunks = []
        skipped_chunks = []

        for chunk in chunks:
            type_key = chunk.chunk_type.value
            by_type[type_key]["total"] += 1

            if chunk.has_embedding:
                by_type[type_key]["embedded"] += 1
            elif self._should_skip_chunk(chunk):
                skipped_chunks.append(chunk.chunk_id)
            else:
                failed_chunks.append(chunk.chunk_id)

        # Calculate totals
        total_chunks = len(chunks)
        embedded_chunks = sum(1 for c in chunks if c.has_embedding)

        # Debug log counts
        logger.info(f"VALIDATOR_DEBUG: Calculated total={total_chunks}, embedded={embedded_chunks}")
        # Check first 3 chunks
        for i, c in enumerate(chunks[:3]):
            logger.info(f"VALIDATOR_DEBUG: Sample[{i}] has_embedding={c.has_embedding}, embedding={c.embedding is not None}, _db={c._db_has_embedding}")

        # Build report
        report = CoverageReport(
            total_chunks=total_chunks,
            embedded_chunks=embedded_chunks,
            failed_chunks=failed_chunks,
            skipped_chunks=skipped_chunks,
            by_type=dict(by_type)
        )

        # Log warnings
        if self.warn_on_low_coverage and report.overall_coverage < self.min_coverage_threshold:
            logger.warning(
                f"Low embedding coverage for {pdf_id}: "
                f"{report.overall_coverage:.1%} (threshold: {self.min_coverage_threshold:.1%})"
            )
            if failed_chunks:
                logger.warning(f"Failed chunks: {failed_chunks[:5]}...")

        return report

    async def get_coverage_by_type(
        self,
        pdf_id: str,
        chunk_type: ChunkType
    ) -> float:
        """
        Get coverage percentage for a specific chunk type.
        Note: Requires chunks to be passed externally or fetched from repository.
        """
        # This is a simplified version - in practice, would query repository
        logger.warning(
            f"get_coverage_by_type called without chunks for {pdf_id}, "
            "returning 0.0"
        )
        return 0.0

    async def find_missing_embeddings(self, pdf_id: str) -> List[str]:
        """
        Find chunk IDs without embeddings.
        Note: Requires repository access for full implementation.
        """
        logger.warning(
            f"find_missing_embeddings called without repository for {pdf_id}"
        )
        return []

    async def validate_coverage_with_chunks(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk],
        chunk_type: Optional[ChunkType] = None
    ) -> Dict[str, Any]:
        """
        Validate coverage with detailed breakdown.

        Args:
            pdf_id: Document ID
            chunks: All chunks for the document
            chunk_type: Optional filter by chunk type

        Returns:
            Detailed coverage report
        """
        if chunk_type:
            filtered_chunks = [c for c in chunks if c.chunk_type == chunk_type]
        else:
            filtered_chunks = chunks

        report = await self.validate_coverage(pdf_id, filtered_chunks)

        # Calculate type-specific coverages
        text_chunks = [c for c in chunks if c.chunk_type == ChunkType.TEXT_CHUNK]
        table_chunks = [c for c in chunks if c.chunk_type == ChunkType.TABLE_CHUNK]
        image_chunks = [c for c in chunks if c.chunk_type == ChunkType.IMAGE_CHUNK]
        ocr_chunks = [c for c in chunks if c.chunk_type == ChunkType.OCR_CHUNK]

        text_coverage = self._calculate_type_coverage(text_chunks)
        table_coverage = self._calculate_type_coverage(table_chunks)
        image_coverage = self._calculate_type_coverage(image_chunks)
        ocr_coverage = self._calculate_type_coverage(ocr_chunks)

        return {
            "pdf_id": pdf_id,
            "overall_coverage": report.overall_coverage,
            "text_coverage": text_coverage,
            "table_coverage": table_coverage,
            "image_coverage": image_coverage,
            "ocr_coverage": ocr_coverage,
            "total_chunks": report.total_chunks,
            "embedded_chunks": report.embedded_chunks,
            "failed_chunk_ids": report.failed_chunks,
            "skipped_chunk_ids": report.skipped_chunks,
            "by_type": report.by_type,
            "meets_threshold": report.overall_coverage >= self.min_coverage_threshold
        }

    def _calculate_type_coverage(self, chunks: List[AdaptiveChunk]) -> float:
        """Calculate coverage for a list of chunks."""
        if not chunks:
            return 1.0  # No chunks of this type = full coverage
        embedded = sum(1 for c in chunks if c.has_embedding)
        return embedded / len(chunks)

    def _should_skip_chunk(self, chunk: AdaptiveChunk) -> bool:
        """
        Determine if a chunk should be skipped for embedding.
        """
        # Skip very short chunks
        if chunk.content_length < 10:
            return True

        # Skip chunks with only whitespace/punctuation
        content_stripped = ''.join(c for c in chunk.content if c.isalnum())
        if len(content_stripped) < 5:
            return True

        return False

    async def generate_coverage_summary(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk]
    ) -> str:
        """
        Generate a human-readable coverage summary.

        Args:
            pdf_id: Document ID
            chunks: All chunks

        Returns:
            Summary string
        """
        coverage_data = await self.validate_coverage_with_chunks(pdf_id, chunks)

        summary_lines = [
            f"=== Embedding Coverage Report for {pdf_id} ===",
            f"Overall Coverage: {coverage_data['overall_coverage']:.1%}",
            f"",
            f"By Content Type:",
            f"  - Text:  {coverage_data['text_coverage']:.1%}",
            f"  - Table: {coverage_data['table_coverage']:.1%}",
            f"  - Image: {coverage_data['image_coverage']:.1%}",
            f"  - OCR:   {coverage_data['ocr_coverage']:.1%}",
            f"",
            f"Totals:",
            f"  - Total Chunks:    {coverage_data['total_chunks']}",
            f"  - Embedded:        {coverage_data['embedded_chunks']}",
            f"  - Failed:          {len(coverage_data['failed_chunk_ids'])}",
            f"  - Skipped:         {len(coverage_data['skipped_chunk_ids'])}",
            f"",
            f"Status: {'PASS' if coverage_data['meets_threshold'] else 'NEEDS ATTENTION'}"
        ]

        if coverage_data['failed_chunk_ids']:
            summary_lines.append(f"")
            summary_lines.append(f"Failed Chunks (first 5):")
            for cid in coverage_data['failed_chunk_ids'][:5]:
                summary_lines.append(f"  - {cid}")

        return "\n".join(summary_lines)


# Singleton instance
_validator: Optional[EmbeddingCoverageValidator] = None


def get_embedding_coverage_validator(
    min_coverage_threshold: float = None
) -> EmbeddingCoverageValidator:
    """Get or create embedding coverage validator instance."""
    global _validator
    if _validator is None:
        _validator = EmbeddingCoverageValidator(
            min_coverage_threshold=min_coverage_threshold
        )
    return _validator
