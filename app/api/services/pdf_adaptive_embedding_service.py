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
import asyncio
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
        on_progress: Optional[Callable[[str, float, str], None]] = None,
        document_name: Optional[str] = None
    ) -> AdaptiveProcessResponse:
        """
        Process a PDF with adaptive embedding.

        Args:
            pdf_content: Raw PDF bytes
            pdf_id: Unique document ID
            options: Processing options
            on_progress: Optional progress callback (stage, percentage, message)
            document_name: Original filename for source reference display

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

        logger.warning(f"SERVICE_DEBUG: process_pdf called, pdf_id={pdf_id}, on_progress={on_progress is not None}")

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
                pdf_content, pdf_id, options.language, document_name=document_name
            )
            await self.structure_repository.save_analysis(structure)

            logger.info(
                f"Structure analysis complete for {pdf_id}: "
                f"type={structure.document_type.value}, "
                f"pages={structure.total_pages}, "
                f"sections={len(structure.hierarchy)}"
            )

            # Step 1.5: Extract and store images
            if structure.total_images > 0:
                self._update_status(task_id, ProcessingStatus.ANALYZING, 0.2, "Extracting images...")
                if on_progress:
                    on_progress("extracting_images", 20, f"Extracting {structure.total_images} images...")

                try:
                    extracted_images = await self.structure_analyzer.extract_images(
                        pdf_content, pdf_id, min_size=50, max_images=100
                    )
                    if extracted_images:
                        from ..core.deps import get_postgres_pool
                        from ..infrastructure.postgres.image_repository import PostgresImageRepository

                        pool = await get_postgres_pool()
                        image_repo = PostgresImageRepository(pool)
                        saved_images = await image_repo.save_images(extracted_images)
                        logger.info(f"Saved {saved_images} images for {pdf_id}")

                        # Generate CLIP embeddings for saved images
                        if on_progress:
                            on_progress("clip_embedding", 22, f"Generating CLIP embeddings for {saved_images} images...")

                        try:
                            from .clip_embedding_service import get_clip_embedding_service
                            clip_service = get_clip_embedding_service()

                            clip_success = 0
                            for img in extracted_images:
                                try:
                                    image_data = img.get("image_data")
                                    if image_data:
                                        clip_embedding = await clip_service.embed_image(image_data)
                                        # Check if embedding is valid
                                        if clip_embedding and sum(1 for v in clip_embedding if v != 0.0) > 0:
                                            await image_repo.update_clip_embedding(img["image_id"], clip_embedding)
                                            clip_success += 1
                                except Exception as clip_img_err:
                                    logger.debug(f"CLIP embedding failed for {img.get('image_id')}: {clip_img_err}")

                            logger.info(f"Generated CLIP embeddings for {clip_success}/{len(extracted_images)} images")
                        except Exception as clip_err:
                            logger.warning(f"CLIP embedding generation failed, continuing: {clip_err}")

                except Exception as img_error:
                    logger.warning(f"Image extraction failed, continuing: {img_error}")

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
                "filename": document_name or pdf_id,  # Pass filename for error doc detection
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

            logger.info(f"EMBED_PIPELINE: embedding_executor={self.embedding_executor is not None}, chunks={len(chunks)}")
            if self.embedding_executor:
                def embedding_progress_callback(progress: EmbeddingProgress):
                    pct = 50 + (progress.progress_percentage * 0.35)
                    self._update_status(
                        task_id, ProcessingStatus.EMBEDDING, pct / 100,
                        f"Embedding: {progress.completed_chunks}/{progress.total_chunks}"
                    )
                    if on_progress:
                        on_progress("embedding", pct, f"Embedding: {progress.completed_chunks}/{progress.total_chunks}")

                logger.warning(f"EMBED_PIPELINE: Calling embedding_executor.embed_chunks for {len(chunks)} chunks...")
                chunks = await self.embedding_executor.embed_chunks(
                    chunks,
                    on_progress=embedding_progress_callback
                )
                logger.warning(f"EMBED_PIPELINE: embed_chunks returned, yielding to event loop...")
                # Yield control to event loop after long operation
                await asyncio.sleep(0)
                logger.warning(f"EMBED_PIPELINE: counting embedded chunks...")
                embedded_count = sum(1 for c in chunks if c.has_embedding)
                logger.info(f"EMBED_PIPELINE: After embedding, {embedded_count}/{len(chunks)} chunks have embeddings")
            else:
                logger.warning("No embedding executor provided, skipping embeddings")

            # Save chunks to repository (this can take a while for large documents)
            self._update_status(task_id, ProcessingStatus.EMBEDDING, 0.87, "Saving chunks to database...")
            if on_progress:
                on_progress("saving", 87, f"Saving {len(chunks)} chunks to database...")

            # Yield control before long save operation
            await asyncio.sleep(0)
            logger.warning(f"EMBED_PIPELINE: Starting save_chunks_batch for {len(chunks)} chunks...")
            saved_count = await self.chunk_repository.save_chunks_batch(chunks)
            logger.warning(f"EMBED_PIPELINE: Saved {saved_count} chunks for {pdf_id}")

            # Yield control after long save operation
            await asyncio.sleep(0)

            # Step 4: Coverage Validation
            self._update_status(task_id, ProcessingStatus.VALIDATING, 0.9, "Validating coverage...")
            if on_progress:
                on_progress("validating", 90, "Validating embedding coverage...")

            logger.warning(f"EMBED_PIPELINE: Starting coverage validation for {len(chunks)} chunks...")
            # Debug: Log chunk embedding status before validation
            pre_validation_count = sum(1 for c in chunks if c.has_embedding)
            logger.warning(f"COVERAGE_DEBUG: Before validation - {pre_validation_count}/{len(chunks)} chunks have embeddings")
            # Sample first few chunks (skip for large docs)
            if len(chunks) < 100:
                for i, chunk in enumerate(chunks[:3]):
                    logger.warning(f"COVERAGE_DEBUG: Chunk[{i}] id={chunk.chunk_id}, has_embedding={chunk.has_embedding}")

            coverage_data = await self.coverage_validator.validate_coverage_with_chunks(pdf_id, chunks)

            # Debug: Log coverage data
            logger.warning(f"COVERAGE_DEBUG: After validation - total={coverage_data['total_chunks']}, embedded={coverage_data['embedded_chunks']}, overall={coverage_data['overall_coverage']:.2%}")

            # Note: Quality evaluation is now a separate on-demand operation
            # Call evaluate_quality_for_pdf() separately when needed
            # This speeds up the embedding pipeline significantly
            quality_metrics = None

            # Save coverage (quality_metrics will be updated later if user requests evaluation)
            logger.warning(f"EMBED_PIPELINE: Saving coverage data to database...")
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
            logger.warning(f"EMBED_PIPELINE: Coverage saved to database")

            # Complete
            self._update_status(task_id, ProcessingStatus.COMPLETED, 1.0, "Processing complete")
            logger.warning(f"EMBED_PIPELINE: ✓ Processing complete for {pdf_id}!")
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

    async def evaluate_quality_for_pdf(self, pdf_id: str) -> Dict[str, Any]:
        """
        Run quality evaluation for a document on-demand.

        This is a separate operation from embedding to allow faster embedding completion.
        Quality evaluation can be slow for large documents (O(n²) complexity).

        Args:
            pdf_id: Document ID to evaluate

        Returns:
            Dict with quality metrics or error
        """
        try:
            # Get chunks from repository
            chunks = await self.chunk_repository.get_chunks_by_pdf(pdf_id)

            if not chunks:
                return {
                    "status": "error",
                    "message": f"No chunks found for pdf_id={pdf_id}"
                }

            # Check if document is too large
            if len(chunks) > 10000:
                return {
                    "status": "skipped",
                    "message": f"Document too large for quality evaluation ({len(chunks)} chunks > 10000)",
                    "chunks_count": len(chunks)
                }

            logger.info(f"Starting quality evaluation for {pdf_id} with {len(chunks)} chunks")

            # Run quality evaluation
            quality_metrics = await self.quality_evaluator.evaluate_quality(pdf_id, chunks)

            # Update coverage record with quality metrics
            coverage = await self.coverage_repository.get_coverage(pdf_id)
            if coverage:
                coverage.quality_metrics = quality_metrics
                await self.coverage_repository.save_coverage(coverage)
                logger.info(f"Quality evaluation complete for {pdf_id}")

            return {
                "status": "completed",
                "message": "Quality evaluation complete",
                "pdf_id": pdf_id,
                "chunks_evaluated": len(chunks),
                "quality_metrics": quality_metrics.to_dict() if quality_metrics else None
            }

        except Exception as e:
            logger.error(f"Quality evaluation failed for {pdf_id}: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

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
        min_similarity: float = 0.3,
        keyword_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks with optional keyword filtering.

        Args:
            query_embedding: Query vector for semantic similarity
            limit: Maximum number of results
            pdf_id: Optional PDF ID filter
            chunk_types: Optional chunk type filter
            section_path_prefix: Optional section path filter
            min_similarity: Minimum similarity threshold
            keyword_filter: Optional keyword for exact content matching (e.g., error codes)

        Returns:
            List of matching chunks with similarity scores
        """
        return await self.chunk_repository.search_similar(
            query_embedding=query_embedding,
            limit=limit,
            min_similarity=min_similarity,
            pdf_id=pdf_id,
            chunk_types=chunk_types,
            section_path_prefix=section_path_prefix,
            keyword_filter=keyword_filter
        )

    async def search_chunks_hybrid(
        self,
        query_embedding: List[float],
        query_text: str,
        limit: int = 5,
        pdf_id: Optional[str] = None,
        min_similarity: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity with keyword boosting.

        This method improves search accuracy by:
        1. Detecting "what is" query intent (이란, とは, what is)
        2. Boosting results with keyword matches in title/content
        3. Prioritizing introduction/overview sections for definitional queries
        4. Re-ranking with combined score (60% vector + 40% keyword)

        Args:
            query_embedding: Query vector for semantic similarity
            query_text: Original query text for keyword matching and intent detection
            limit: Maximum number of results
            pdf_id: Optional PDF ID filter
            min_similarity: Minimum vector similarity threshold

        Returns:
            List of matching chunks with combined similarity scores
        """
        return await self.chunk_repository.search_hybrid(
            query_embedding=query_embedding,
            query_text=query_text,
            limit=limit,
            min_similarity=min_similarity,
            pdf_id=pdf_id,
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
    embedding_executor: ParallelEmbeddingExecutor = None,
    structure_analyzer: PDFStructureAnalyzer = None,
    chunk_planner: AdaptiveChunkPlanner = None,
    coverage_validator: EmbeddingCoverageValidator = None,
    quality_evaluator: AdaptiveQualityEvaluator = None
) -> PDFAdaptiveEmbeddingService:
    """
    Create a PDF Adaptive Embedding Service instance.

    All service dependencies should be explicitly provided to avoid
    calling get_settings() at initialization time.
    """
    return PDFAdaptiveEmbeddingService(
        chunk_repository=chunk_repository,
        structure_repository=structure_repository,
        coverage_repository=coverage_repository,
        embedding_executor=embedding_executor,
        structure_analyzer=structure_analyzer,
        chunk_planner=chunk_planner,
        coverage_validator=coverage_validator,
        quality_evaluator=quality_evaluator
    )
