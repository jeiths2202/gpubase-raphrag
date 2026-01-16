"""
PDF Adaptive Embedding Service - Main Orchestrator
PDF 적응형 임베딩 서비스 - 메인 오케스트레이터

Orchestrates the complete adaptive embedding pipeline:
1. Structure Analysis
2. Adaptive Chunking
3. Parallel Embedding
4. Coverage Validation
5. Quality Evaluation
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Callable

from ..models.adaptive_chunk import (
    AdaptiveChunk,
    ChunkType,
    ChunkEmbeddingCoverage,
    CoverageReport,
    QualityMetrics,
    QualityLevel,
    PDFStructureAnalysis,
    ProcessingStatus,
    AdaptiveProcessRequest,
    AdaptiveProcessResponse,
)
from ..ports.adaptive_embedding_port import (
    AdaptiveChunkRepositoryPort,
    PDFStructureRepositoryPort,
    CoverageRepositoryPort,
)
from .pdf_structure_analyzer import PDFStructureAnalyzer, get_pdf_structure_analyzer
from .adaptive_chunk_planner import (
    AdaptiveChunkPlanner,
    get_adaptive_chunk_planner,
    create_chunk_from_plan,
)
from .parallel_embedding_executor import (
    ParallelEmbeddingExecutor,
    EmbeddingProgress,
)
from .embedding_coverage_validator import (
    EmbeddingCoverageValidator,
    get_embedding_coverage_validator,
)
from .adaptive_quality_evaluator import (
    AdaptiveQualityEvaluator,
    get_adaptive_quality_evaluator,
)

logger = logging.getLogger(__name__)


class PDFAdaptiveEmbeddingService:
    """
    Main orchestrator for adaptive PDF embedding.
    PDF 구조 보존 임베딩의 메인 오케스트레이터
    """

    def __init__(
        self,
        chunk_repository: AdaptiveChunkRepositoryPort,
        structure_repository: PDFStructureRepositoryPort,
        coverage_repository: CoverageRepositoryPort,
        structure_analyzer: PDFStructureAnalyzer = None,
        chunk_planner: AdaptiveChunkPlanner = None,
        embedding_executor: ParallelEmbeddingExecutor = None,
        coverage_validator: EmbeddingCoverageValidator = None,
        quality_evaluator: AdaptiveQualityEvaluator = None
    ):
        """
        Initialize the orchestrator.

        Args:
            chunk_repository: Repository for storing chunks
            structure_repository: Repository for structure analysis
            coverage_repository: Repository for coverage reports
            structure_analyzer: PDF structure analyzer (optional)
            chunk_planner: Adaptive chunk planner (optional)
            embedding_executor: Parallel embedding executor (optional)
            coverage_validator: Coverage validator (optional)
            quality_evaluator: Quality evaluator (optional)
        """
        self.chunk_repository = chunk_repository
        self.structure_repository = structure_repository
        self.coverage_repository = coverage_repository

        # Use provided services or defaults
        self.structure_analyzer = structure_analyzer or get_pdf_structure_analyzer()
        self.chunk_planner = chunk_planner or get_adaptive_chunk_planner()
        self.embedding_executor = embedding_executor
        self.coverage_validator = coverage_validator or get_embedding_coverage_validator()
        self.quality_evaluator = quality_evaluator or get_adaptive_quality_evaluator()

        # Track processing status
        self._processing_status: Dict[str, Dict[str, Any]] = {}

    async def process_pdf(
        self,
        pdf_content: bytes,
        pdf_id: str,
        options: AdaptiveProcessRequest,
        on_progress: Optional[Callable[[str, float, str], None]] = None
    ) -> AdaptiveProcessResponse:
        """
        Process a PDF with adaptive embedding.

        Args:
            pdf_content: Raw PDF bytes
            pdf_id: Unique document ID
            options: Processing options
            on_progress: Optional progress callback (stage, percentage, message)

        Returns:
            AdaptiveProcessResponse with status and details
        """
        task_id = str(uuid.uuid4())
        self._processing_status[task_id] = {
            "pdf_id": pdf_id,
            "status": ProcessingStatus.ANALYZING,
            "progress": 0.0,
            "message": "Starting processing..."
        }

        try:
            # Check if already processed
            if not options.force_reprocess:
                existing = await self.structure_repository.get_analysis(pdf_id)
                if existing:
                    logger.info(f"Document {pdf_id} already processed, skipping")
                    return AdaptiveProcessResponse(
                        pdf_id=pdf_id,
                        task_id=task_id,
                        status=ProcessingStatus.COMPLETED,
                        message="Document already processed. Use force_reprocess=true to reprocess.",
                        estimated_chunks=0
                    )

            # Step 1: Structure Analysis
            self._update_status(task_id, ProcessingStatus.ANALYZING, 0.1, "Analyzing document structure...")
            if on_progress:
                on_progress("analyzing", 10, "Analyzing document structure...")

            structure = await self.structure_analyzer.analyze(
                pdf_content, pdf_id, options.language
            )
            await self.structure_repository.save_analysis(structure)

            logger.info(
                f"Structure analysis complete for {pdf_id}: "
                f"type={structure.document_type.value}, "
                f"pages={structure.total_pages}, "
                f"sections={len(structure.hierarchy)}"
            )

            # Step 2: Adaptive Chunking
            self._update_status(task_id, ProcessingStatus.CHUNKING, 0.3, "Creating adaptive chunks...")
            if on_progress:
                on_progress("chunking", 30, "Creating adaptive chunks...")

            chunk_options = {
                "max_chunk_size": options.max_chunk_size,
                "min_chunk_size": options.min_chunk_size,
                "overlap_size": options.overlap_size,
                "preserve_tables": options.preserve_tables,
                "preserve_sections": options.preserve_sections,
            }

            plans = await self.chunk_planner.create_chunk_plan(
                pdf_content, structure, chunk_options
            )

            # Create chunks from plans
            chunks = []
            for i, plan in enumerate(plans):
                chunk = create_chunk_from_plan(plan, pdf_id, i)
                chunks.append(chunk)

            # Build chunk relations
            chunks = await self.chunk_planner.build_chunk_relations(chunks)

            logger.info(f"Created {len(chunks)} adaptive chunks for {pdf_id}")

            # Step 3: Parallel Embedding
            self._update_status(task_id, ProcessingStatus.EMBEDDING, 0.5, "Generating embeddings...")
            if on_progress:
                on_progress("embedding", 50, f"Generating embeddings for {len(chunks)} chunks...")

            if self.embedding_executor:
                def embedding_progress_callback(progress: EmbeddingProgress):
                    pct = 50 + (progress.progress_percentage * 0.35)
                    self._update_status(
                        task_id, ProcessingStatus.EMBEDDING, pct / 100,
                        f"Embedding: {progress.completed_chunks}/{progress.total_chunks}"
                    )
                    if on_progress:
                        on_progress("embedding", pct, f"Embedding: {progress.completed_chunks}/{progress.total_chunks}")

                chunks = await self.embedding_executor.embed_chunks(
                    chunks,
                    on_progress=embedding_progress_callback
                )
            else:
                logger.warning("No embedding executor provided, skipping embeddings")

            # Save chunks to repository
            saved_count = await self.chunk_repository.save_chunks_batch(chunks)
            logger.info(f"Saved {saved_count} chunks for {pdf_id}")

            # Step 4: Coverage Validation
            self._update_status(task_id, ProcessingStatus.VALIDATING, 0.9, "Validating coverage...")
            if on_progress:
                on_progress("validating", 90, "Validating embedding coverage...")

            coverage_data = await self.coverage_validator.validate_coverage_with_chunks(pdf_id, chunks)

            # Step 5: Quality Evaluation
            quality_metrics = await self.quality_evaluator.evaluate_quality(pdf_id, chunks)

            # Save coverage and quality
            coverage = ChunkEmbeddingCoverage(
                pdf_id=pdf_id,
                text_coverage=coverage_data["text_coverage"],
                table_coverage=coverage_data["table_coverage"],
                image_coverage=coverage_data["image_coverage"],
                ocr_coverage=coverage_data["ocr_coverage"],
                overall_coverage=coverage_data["overall_coverage"],
                coverage_report=CoverageReport(
                    total_chunks=coverage_data["total_chunks"],
                    embedded_chunks=coverage_data["embedded_chunks"],
                    failed_chunks=coverage_data["failed_chunk_ids"],
                    skipped_chunks=coverage_data["skipped_chunk_ids"],
                    by_type=coverage_data["by_type"]
                ),
                quality_metrics=quality_metrics,
                last_verified_at=datetime.now(timezone.utc)
            )
            await self.coverage_repository.save_coverage(coverage)

            # Complete
            self._update_status(task_id, ProcessingStatus.COMPLETED, 1.0, "Processing complete")
            if on_progress:
                on_progress("completed", 100, "Processing complete")

            return AdaptiveProcessResponse(
                pdf_id=pdf_id,
                task_id=task_id,
                status=ProcessingStatus.COMPLETED,
                message=f"Successfully processed document with {len(chunks)} chunks",
                estimated_chunks=len(chunks)
            )

        except Exception as e:
            logger.error(f"Failed to process PDF {pdf_id}: {e}")
            self._update_status(task_id, ProcessingStatus.FAILED, 0.0, str(e))
            return AdaptiveProcessResponse(
                pdf_id=pdf_id,
                task_id=task_id,
                status=ProcessingStatus.FAILED,
                message=f"Processing failed: {str(e)}",
                estimated_chunks=0
            )

    async def reprocess_changed_pages(
        self,
        pdf_content: bytes,
        pdf_id: str,
        changed_pages: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Incrementally re-embed only changed pages.

        Args:
            pdf_content: Raw PDF bytes
            pdf_id: Document ID
            changed_pages: Specific pages to reprocess (None = auto-detect)

        Returns:
            Dict with reprocessing results
        """
        # Get existing structure
        existing_structure = await self.structure_repository.get_analysis(pdf_id)

        if not existing_structure:
            # No existing analysis, do full processing
            options = AdaptiveProcessRequest()
            result = await self.process_pdf(pdf_content, pdf_id, options)
            return {
                "status": result.status.value,
                "message": "Full processing (no existing structure)",
                "chunks_updated": result.estimated_chunks,
                "chunks_skipped": 0
            }

        # Auto-detect changed pages if not provided
        if changed_pages is None:
            new_structure = await self.structure_analyzer.analyze(
                pdf_content, pdf_id, existing_structure.language
            )
            changed_pages = await self.structure_repository.get_changed_pages(
                pdf_id, new_structure.page_hashes
            )

        if not changed_pages:
            return {
                "status": "completed",
                "message": "No changes detected",
                "chunks_updated": 0,
                "chunks_skipped": 0
            }

        logger.info(f"Reprocessing pages {changed_pages} for {pdf_id}")

        # Get existing chunks for changed pages
        existing_chunks = await self.chunk_repository.get_chunks_by_pdf(pdf_id)
        chunks_to_update = [
            c for c in existing_chunks
            if any(c.page_start <= p <= c.page_end for p in changed_pages)
        ]
        chunks_to_keep = [
            c for c in existing_chunks
            if not any(c.page_start <= p <= c.page_end for p in changed_pages)
        ]

        # Reprocess changed chunks
        if chunks_to_update and self.embedding_executor:
            # Re-embed the changed chunks
            updated_chunks = await self.embedding_executor.embed_chunks(chunks_to_update)

            # Save updated chunks
            for chunk in updated_chunks:
                chunk.chunk_version += 1
                await self.chunk_repository.save_chunk(chunk)

            # Re-validate coverage
            all_chunks = chunks_to_keep + updated_chunks
            coverage_data = await self.coverage_validator.validate_coverage_with_chunks(pdf_id, all_chunks)

            # Update structure with new page hashes
            new_structure = await self.structure_analyzer.analyze(
                pdf_content, pdf_id, existing_structure.language
            )
            await self.structure_repository.save_analysis(new_structure)

            return {
                "status": "completed",
                "message": f"Reprocessed {len(chunks_to_update)} chunks",
                "chunks_updated": len(chunks_to_update),
                "chunks_skipped": len(chunks_to_keep),
                "changed_pages": changed_pages,
                "coverage": coverage_data["overall_coverage"]
            }

        return {
            "status": "completed",
            "message": "No chunks to update",
            "chunks_updated": 0,
            "chunks_skipped": len(chunks_to_keep)
        }

    async def get_chunks(
        self,
        pdf_id: str,
        chunk_type: Optional[ChunkType] = None
    ) -> List[AdaptiveChunk]:
        """Get all chunks for a document."""
        return await self.chunk_repository.get_chunks_by_pdf(pdf_id, chunk_type)

    async def get_coverage(self, pdf_id: str) -> Optional[ChunkEmbeddingCoverage]:
        """Get coverage report for a document."""
        return await self.coverage_repository.get_coverage(pdf_id)

    async def get_quality_metrics(self, pdf_id: str) -> Optional[QualityMetrics]:
        """Get quality metrics for a document."""
        coverage = await self.coverage_repository.get_coverage(pdf_id)
        if coverage:
            return coverage.quality_metrics
        return None

    async def get_structure(self, pdf_id: str) -> Optional[PDFStructureAnalysis]:
        """Get structure analysis for a document."""
        return await self.structure_repository.get_analysis(pdf_id)

    async def search_chunks(
        self,
        query_embedding: List[float],
        limit: int = 5,
        pdf_id: Optional[str] = None,
        chunk_types: Optional[List[ChunkType]] = None,
        section_path_prefix: Optional[str] = None,
        min_similarity: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks."""
        return await self.chunk_repository.search_similar(
            query_embedding=query_embedding,
            limit=limit,
            min_similarity=min_similarity,
            pdf_id=pdf_id,
            chunk_types=chunk_types,
            section_path_prefix=section_path_prefix
        )

    async def delete_document(self, pdf_id: str) -> Dict[str, int]:
        """Delete all data for a document."""
        chunks_deleted = await self.chunk_repository.delete_pdf_chunks(pdf_id)
        structure_deleted = await self.structure_repository.delete_analysis(pdf_id)
        coverage_deleted = await self.coverage_repository.delete_coverage(pdf_id)

        return {
            "chunks_deleted": chunks_deleted,
            "structure_deleted": 1 if structure_deleted else 0,
            "coverage_deleted": 1 if coverage_deleted else 0
        }

    def get_processing_status(self, task_id: str) -> Dict[str, Any]:
        """Get processing status for a task."""
        if task_id in self._processing_status:
            return self._processing_status[task_id]
        return {
            "status": ProcessingStatus.PENDING.value,
            "progress": 0.0,
            "message": "Task not found"
        }

    def _update_status(
        self,
        task_id: str,
        status: ProcessingStatus,
        progress: float,
        message: str
    ):
        """Update processing status."""
        if task_id in self._processing_status:
            self._processing_status[task_id].update({
                "status": status,
                "progress": progress,
                "message": message
            })


# Factory function
def create_pdf_adaptive_embedding_service(
    chunk_repository: AdaptiveChunkRepositoryPort,
    structure_repository: PDFStructureRepositoryPort,
    coverage_repository: CoverageRepositoryPort,
    embedding_executor: ParallelEmbeddingExecutor = None
) -> PDFAdaptiveEmbeddingService:
    """
    Create a PDF Adaptive Embedding Service instance.
    """
    return PDFAdaptiveEmbeddingService(
        chunk_repository=chunk_repository,
        structure_repository=structure_repository,
        coverage_repository=coverage_repository,
        embedding_executor=embedding_executor
    )
