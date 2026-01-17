"""
Adaptive Documents API Router
적응형 문서 API 라우터

Endpoints for adaptive PDF chunking and embedding.
"""
import logging
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from ..models.adaptive_chunk import (
    AdaptiveProcessRequest,
    AdaptiveProcessResponse,
    ChunkListItem,
    ChunkDetailResponse,
    CoverageResponse,
    QualityResponse,
    StructureAnalysisResponse,
    ReprocessRequest,
    ReprocessResponse,
    SearchAdaptiveChunksRequest,
    SearchAdaptiveChunksResponse,
    SearchResultItem,
    ChunkType,
    ProcessingStatus,
    QualityLevel,
)
from ..core.deps import (
    get_adaptive_embedding_service,
    get_embedding_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/documents/adaptive",
    tags=["Adaptive Documents"]
)


@router.get("/list")
async def list_adaptive_documents(
    service=Depends(get_adaptive_embedding_service),
):
    """
    List all adaptive documents with their status.
    적응형 문서 목록 조회
    """
    try:
        # Get all documents from structure repository
        documents = await service.structure_repository.get_all_analyses()

        result = []
        for doc in documents:
            # Get chunk count for this document
            chunks = await service.chunk_repository.get_chunks_by_pdf(doc.pdf_id)

            result.append({
                "pdf_id": doc.pdf_id,
                "document_name": doc.document_name,  # 문서명 추가
                "document_type": doc.document_type.value if hasattr(doc.document_type, 'value') else str(doc.document_type),
                "total_pages": doc.total_pages,
                "total_sections": len(doc.hierarchy) if doc.hierarchy else 0,
                "language": doc.language,
                "chunks_count": len(chunks),
                "status": "completed",
                "created_at": doc.analyzed_at.isoformat() if doc.analyzed_at else None,
            })

        return result
    except Exception as e:
        logger.error(f"Error listing adaptive documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=AdaptiveProcessResponse)
async def process_pdf_adaptive(
    file: UploadFile = File(..., description="PDF file to process"),
    language: str = Query(default="auto", description="Document language (auto, en, ja, ko)"),
    max_chunk_size: int = Query(default=1500, ge=200, le=4000, description="Maximum chunk size"),
    min_chunk_size: int = Query(default=100, ge=50, le=500, description="Minimum chunk size"),
    preserve_tables: bool = Query(default=True, description="Keep tables as single chunks"),
    preserve_sections: bool = Query(default=True, description="Respect section boundaries"),
    force_reprocess: bool = Query(default=False, description="Force re-processing"),
    background_tasks: BackgroundTasks = None,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Process a PDF with adaptive embedding.

    Uses semantic boundaries for chunking rather than fixed sizes.
    Supports incremental re-embedding for efficiency.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Generate PDF ID from filename
    pdf_id = f"pdf_{uuid.uuid4().hex[:12]}"

    # Create processing options
    options = AdaptiveProcessRequest(
        language=language,
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size,
        preserve_tables=preserve_tables,
        preserve_sections=preserve_sections,
        force_reprocess=force_reprocess
    )

    try:
        # Process PDF with original filename
        result = await service.process_pdf(
            content, pdf_id, options,
            document_name=file.filename  # 원본 파일명 전달
        )
        return result

    except Exception as e:
        logger.error(f"Failed to process PDF: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.get("/{pdf_id}/chunks", response_model=List[ChunkListItem])
async def get_document_chunks(
    pdf_id: str,
    chunk_type: Optional[ChunkType] = Query(default=None, description="Filter by chunk type"),
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get all adaptive chunks for a document.
    """
    try:
        chunks = await service.get_chunks(pdf_id, chunk_type)

        if not chunks:
            raise HTTPException(status_code=404, detail=f"No chunks found for document {pdf_id}")

        return [
            ChunkListItem(
                chunk_id=c.chunk_id,
                chunk_type=c.chunk_type,
                content_preview=c.content[:200] + "..." if len(c.content) > 200 else c.content,
                content_length=c.content_length,
                page_start=c.page_start,
                page_end=c.page_end,
                section_path=c.section_path,
                section_title=c.section_title,
                has_embedding=c.has_embedding
            )
            for c in chunks
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_id}/chunks/{chunk_id}", response_model=ChunkDetailResponse)
async def get_chunk_detail(
    pdf_id: str,
    chunk_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get detailed information for a specific chunk.
    """
    try:
        chunks = await service.get_chunks(pdf_id)
        chunk = next((c for c in chunks if c.chunk_id == chunk_id), None)

        if not chunk:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found")

        return ChunkDetailResponse(
            chunk_id=chunk.chunk_id,
            pdf_id=chunk.pdf_id,
            chunk_type=chunk.chunk_type,
            content=chunk.content,
            content_length=chunk.content_length,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=chunk.section_path,
            section_title=chunk.section_title,
            relations=chunk.relations.to_dict(),
            has_embedding=chunk.has_embedding,
            embedding_model_version=chunk.embedding_model_version,
            chunk_version=chunk.chunk_version,
            metadata=chunk.metadata,
            created_at=chunk.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunk detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pdf_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_document(
    pdf_id: str,
    request: ReprocessRequest,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Incrementally re-embed changed pages.

    Detects changes automatically or accepts specific page numbers.
    """
    try:
        # This endpoint requires the original PDF content
        # In a real implementation, you'd retrieve it from storage
        raise HTTPException(
            status_code=501,
            detail="Reprocessing requires original PDF content. Upload via /process with force_reprocess=true"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_id}/coverage", response_model=CoverageResponse)
async def get_coverage_report(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get embedding coverage report for a document.
    """
    try:
        coverage = await service.get_coverage(pdf_id)

        if not coverage:
            raise HTTPException(status_code=404, detail=f"No coverage data for document {pdf_id}")

        return CoverageResponse(
            pdf_id=coverage.pdf_id,
            text_coverage=coverage.text_coverage,
            table_coverage=coverage.table_coverage,
            image_coverage=coverage.image_coverage,
            ocr_coverage=coverage.ocr_coverage,
            overall_coverage=coverage.overall_coverage,
            total_chunks=coverage.coverage_report.total_chunks,
            embedded_chunks=coverage.coverage_report.embedded_chunks,
            quality_level=coverage.quality_metrics.quality_level,
            last_verified_at=coverage.last_verified_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_id}/quality", response_model=QualityResponse)
async def get_quality_metrics(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get quality evaluation metrics for a document.
    """
    try:
        metrics = await service.get_quality_metrics(pdf_id)

        if not metrics:
            raise HTTPException(status_code=404, detail=f"No quality data for document {pdf_id}")

        # Generate recommendations based on metrics
        issues = []
        recommendations = []

        if metrics.top_k_recall < 0.8:
            issues.append("Low top-k recall")
            recommendations.append("Consider adjusting chunk sizes")

        if metrics.section_precision < 0.8:
            issues.append("Low section precision")
            recommendations.append("Section boundaries may need refinement")

        if metrics.hallucination_detected:
            issues.append("Potential hallucination detected")
            recommendations.append("Review flagged chunks for accuracy")

        if metrics.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD]:
            recommendations.append("Quality is acceptable")

        return QualityResponse(
            pdf_id=pdf_id,
            top_k_recall=metrics.top_k_recall,
            section_precision=metrics.section_precision,
            avg_similarity=metrics.avg_similarity,
            quality_level=metrics.quality_level,
            hallucination_detected=metrics.hallucination_detected,
            issues=issues,
            recommendations=recommendations
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get quality metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pdf_id}/refresh-quality", response_model=QualityResponse)
async def refresh_quality_metrics(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Recalculate and refresh quality metrics for a document.
    Loads actual embeddings from DB for accurate quality evaluation.
    """
    try:
        # Load chunks WITH embeddings for quality calculation
        chunks = await service.chunk_repository.get_chunks_with_embeddings(pdf_id, limit=200)

        if not chunks:
            raise HTTPException(status_code=404, detail=f"No embedded chunks found for document {pdf_id}")

        logger.info(f"REFRESH_QUALITY: Loaded {len(chunks)} chunks with embeddings for {pdf_id}")

        # Verify embeddings are loaded
        with_embeddings = sum(1 for c in chunks if c.embedding and len(c.embedding) > 0)
        logger.info(f"REFRESH_QUALITY: {with_embeddings}/{len(chunks)} have actual embeddings")

        # Recalculate quality metrics
        quality_metrics = await service.quality_evaluator.evaluate_quality(pdf_id, chunks)
        logger.info(f"REFRESH_QUALITY: Calculated metrics - recall={quality_metrics.top_k_recall:.2%}, precision={quality_metrics.section_precision:.2%}")

        # Update coverage with new quality metrics
        coverage = await service.coverage_repository.get_coverage(pdf_id)
        if coverage:
            coverage.quality_metrics = quality_metrics
            await service.coverage_repository.save_coverage(coverage)
            logger.info(f"Quality metrics refreshed for {pdf_id}")

        # Generate recommendations
        issues = []
        recommendations = []

        if quality_metrics.top_k_recall < 0.8:
            issues.append("Low top-k recall")
            recommendations.append("Consider adjusting chunk sizes")

        if quality_metrics.section_precision < 0.8:
            issues.append("Low section precision")
            recommendations.append("Section boundaries may need refinement")

        if quality_metrics.hallucination_detected:
            issues.append("Potential hallucination detected")
            recommendations.append("Review flagged chunks for accuracy")

        if quality_metrics.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD]:
            recommendations.append("Quality is acceptable")

        return QualityResponse(
            pdf_id=pdf_id,
            top_k_recall=quality_metrics.top_k_recall,
            section_precision=quality_metrics.section_precision,
            avg_similarity=quality_metrics.avg_similarity,
            quality_level=quality_metrics.quality_level,
            hallucination_detected=quality_metrics.hallucination_detected,
            issues=issues,
            recommendations=recommendations
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh quality metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pdf_id}/structure", response_model=StructureAnalysisResponse)
async def get_structure_analysis(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get structure analysis for a document.
    """
    try:
        structure = await service.get_structure(pdf_id)

        if not structure:
            raise HTTPException(status_code=404, detail=f"No structure data for document {pdf_id}")

        return StructureAnalysisResponse(
            pdf_id=structure.pdf_id,
            document_name=structure.document_name,  # 문서명 추가
            document_type=structure.document_type,
            total_pages=structure.total_pages,
            total_sections=len(structure.hierarchy),
            total_images=structure.total_images,
            total_tables=structure.total_tables,
            language=structure.language,
            hierarchy=[s.to_dict() for s in structure.hierarchy],
            layout_info=structure.layout_info.to_dict(),
            analyzed_at=structure.analyzed_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchAdaptiveChunksResponse)
async def search_adaptive_chunks(
    request: SearchAdaptiveChunksRequest,
    service = Depends(get_adaptive_embedding_service),
    embedding_service = Depends(get_embedding_service)
):
    """
    Search for similar chunks using semantic search.
    """
    try:
        # Generate query embedding using NIM API
        query_embedding = await embedding_service.embed_text(request.query, input_type="query")

        # Convert chunk types if provided
        chunk_types = None
        if request.chunk_types:
            chunk_types = request.chunk_types

        # Search
        results = await service.search_chunks(
            query_embedding=query_embedding,
            limit=request.limit,
            pdf_id=request.pdf_id,
            chunk_types=chunk_types,
            section_path_prefix=request.section_path_prefix,
            min_similarity=request.min_similarity
        )

        # Build response
        search_results = []
        for r in results:
            # Get related chunk IDs from relations
            relations = r.get("relations", {})
            related = []
            if isinstance(relations, dict):
                if relations.get("previous"):
                    related.append(relations["previous"])
                if relations.get("next"):
                    related.append(relations["next"])

            search_results.append(SearchResultItem(
                chunk_id=r["chunk_id"],
                pdf_id=r["pdf_id"],
                chunk_type=ChunkType(r["chunk_type"]),
                content=r["content"],
                section_path=r.get("section_path"),
                section_title=r.get("section_title"),
                page_start=r["page_start"],
                page_end=r["page_end"],
                similarity=r["similarity"],
                related_chunks=related
            ))

        return SearchAdaptiveChunksResponse(
            query=request.query,
            total_results=len(search_results),
            results=search_results
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{pdf_id}")
async def delete_document(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Delete all data for a document.
    모든 문서 데이터 삭제 (청크, 구조, 커버리지, 임베딩)
    """
    try:
        result = await service.delete_document(pdf_id)
        return JSONResponse(content={
            "status": "deleted",
            "pdf_id": pdf_id,
            "details": result
        })

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-delete")
async def batch_delete_documents(
    pdf_ids: List[str],
    service = Depends(get_adaptive_embedding_service)
):
    """
    Delete multiple documents at once.
    여러 문서 일괄 삭제 (청크, 구조, 커버리지, 임베딩 모두 삭제)
    """
    results = {
        "success": [],
        "failed": []
    }

    for pdf_id in pdf_ids:
        try:
            await service.delete_document(pdf_id)
            results["success"].append(pdf_id)
            logger.info(f"Deleted document {pdf_id}")
        except Exception as e:
            results["failed"].append({"pdf_id": pdf_id, "error": str(e)})
            logger.error(f"Failed to delete document {pdf_id}: {e}")

    return JSONResponse(content={
        "status": "completed",
        "total_requested": len(pdf_ids),
        "deleted": len(results["success"]),
        "failed": len(results["failed"]),
        "results": results
    })


@router.get("/status/{task_id}")
async def get_processing_status(
    task_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Get processing status for a task.
    """
    try:
        status = service.get_processing_status(task_id)
        return JSONResponse(content=status)

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reset-service")
async def reset_service():
    """
    Reset adaptive embedding service singleton.
    Forces re-initialization with current configuration.
    Admin endpoint for troubleshooting.
    """
    try:
        from ..core.deps import reset_adaptive_embedding_service
        reset_adaptive_embedding_service()
        return JSONResponse(content={
            "status": "reset",
            "message": "Adaptive embedding service will be re-initialized on next request"
        })
    except Exception as e:
        logger.error(f"Failed to reset service: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pdf_id}/refresh-coverage", response_model=CoverageResponse)
async def refresh_coverage(
    pdf_id: str,
    service = Depends(get_adaptive_embedding_service)
):
    """
    Recalculate and refresh coverage for a document.
    Useful when coverage data is out of sync with actual chunks.
    """
    try:
        from datetime import datetime, timezone
        from ..models.adaptive_chunk import (
            ChunkEmbeddingCoverage,
            CoverageReport,
            QualityMetrics,
            QualityLevel,
        )
        from ..services.embedding_coverage_validator import get_embedding_coverage_validator
        from ..services.adaptive_quality_evaluator import get_adaptive_quality_evaluator

        # Get chunks from repository
        chunks = await service.get_chunks(pdf_id)
        if not chunks:
            raise HTTPException(status_code=404, detail=f"No chunks found for document {pdf_id}")

        # Log chunk status for debugging
        total = len(chunks)
        embedded = sum(1 for c in chunks if c.has_embedding)
        logger.info(f"Refresh coverage for {pdf_id}: {embedded}/{total} chunks embedded")

        # Calculate coverage by type
        from collections import defaultdict
        by_type = defaultdict(lambda: {"total": 0, "embedded": 0})
        for chunk in chunks:
            type_key = chunk.chunk_type.value
            by_type[type_key]["total"] += 1
            if chunk.has_embedding:
                by_type[type_key]["embedded"] += 1

        # Calculate type-specific coverages
        def calc_type_coverage(chunks_list, chunk_type_value):
            type_chunks = [c for c in chunks_list if c.chunk_type.value == chunk_type_value]
            if not type_chunks:
                return 1.0
            return sum(1 for c in type_chunks if c.has_embedding) / len(type_chunks)

        text_coverage = calc_type_coverage(chunks, "TEXT_CHUNK")
        table_coverage = calc_type_coverage(chunks, "TABLE_CHUNK")
        image_coverage = calc_type_coverage(chunks, "IMAGE_CHUNK")
        ocr_coverage = calc_type_coverage(chunks, "OCR_CHUNK")
        overall_coverage = embedded / total if total > 0 else 0.0

        # Determine quality level
        if overall_coverage >= 0.95:
            quality_level = QualityLevel.EXCELLENT
        elif overall_coverage >= 0.85:
            quality_level = QualityLevel.GOOD
        elif overall_coverage >= 0.70:
            quality_level = QualityLevel.FAIR
        else:
            quality_level = QualityLevel.POOR

        # Create and save updated coverage
        coverage = ChunkEmbeddingCoverage(
            pdf_id=pdf_id,
            text_coverage=text_coverage,
            table_coverage=table_coverage,
            image_coverage=image_coverage,
            ocr_coverage=ocr_coverage,
            overall_coverage=overall_coverage,
            coverage_report=CoverageReport(
                total_chunks=total,
                embedded_chunks=embedded,
                failed_chunks=[],
                skipped_chunks=[],
                by_type=dict(by_type)
            ),
            quality_metrics=QualityMetrics(
                top_k_recall=overall_coverage,
                section_precision=1.0,
                avg_similarity=0.0,
                embedding_dimension=4096,
                quality_level=quality_level,
                hallucination_detected=False
            ),
            last_verified_at=datetime.now(timezone.utc)
        )

        await service.coverage_repository.save_coverage(coverage)
        logger.info(f"Coverage refreshed for {pdf_id}: {embedded}/{total} ({overall_coverage*100:.1f}%)")

        return CoverageResponse(
            pdf_id=pdf_id,
            text_coverage=text_coverage,
            table_coverage=table_coverage,
            image_coverage=image_coverage,
            ocr_coverage=ocr_coverage,
            overall_coverage=overall_coverage,
            total_chunks=total,
            embedded_chunks=embedded,
            quality_level=quality_level,
            last_verified_at=coverage.last_verified_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Image Endpoints
# =============================================================================

@router.get("/{pdf_id}/images")
async def get_document_images(
    pdf_id: str,
    page: Optional[int] = Query(default=None, description="Filter by page number"),
):
    """
    Get all images extracted from a PDF document.
    PDF 문서에서 추출된 모든 이미지 조회
    """
    try:
        from ..core.deps import get_postgres_pool
        from ..infrastructure.postgres.image_repository import PostgresImageRepository

        pool = await get_postgres_pool()
        repo = PostgresImageRepository(pool)

        if page:
            images = await repo.get_images_by_document(pdf_id, page_number=page)
        else:
            images = await repo.get_images_by_document(pdf_id)

        # Remove binary data from response, only return metadata
        return {
            "pdf_id": pdf_id,
            "total_images": len(images),
            "images": [
                {
                    "image_id": img["image_id"],
                    "page_number": img["page_number"],
                    "width": img["width"],
                    "height": img["height"],
                    "mime_type": img["mime_type"],
                    "file_size": img["file_size"],
                    "description": img.get("description"),
                    "figure_caption": img.get("figure_caption"),
                    "url": f"/api/v1/documents/adaptive/images/{img['image_id']}/raw"
                }
                for img in images
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get document images: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/images/{image_id}/raw")
async def get_image_raw(image_id: str):
    """
    Get raw image binary data.
    원본 이미지 바이너리 데이터 조회
    """
    try:
        from fastapi.responses import Response
        from ..core.deps import get_postgres_pool
        from ..infrastructure.postgres.image_repository import PostgresImageRepository

        pool = await get_postgres_pool()
        repo = PostgresImageRepository(pool)

        image = await repo.get_image(image_id)

        if not image:
            raise HTTPException(status_code=404, detail="Image not found")

        return Response(
            content=image["image_data"],
            media_type=image["mime_type"],
            headers={
                "Content-Disposition": f'inline; filename="{image_id}.png"',
                "Cache-Control": "public, max-age=86400",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{pdf_id}/extract-images")
async def extract_and_store_images(
    pdf_id: str,
    file: UploadFile = File(..., description="PDF file to extract images from"),
):
    """
    Extract and store images from an uploaded PDF for an existing document.
    기존 문서에 대해 업로드된 PDF에서 이미지를 추출하고 저장

    This endpoint extracts images without re-processing chunks.
    Use when you want to add images to an already processed PDF.
    """
    try:
        from ..core.deps import get_postgres_pool
        from ..infrastructure.postgres.image_repository import PostgresImageRepository
        from ..services.pdf_structure_analyzer import get_pdf_structure_analyzer

        # Read PDF content
        content = await file.read()

        # Get structure analyzer and extract images
        analyzer = get_pdf_structure_analyzer()
        extracted_images = await analyzer.extract_images(content, pdf_id, min_size=50, max_images=100)

        if not extracted_images:
            return JSONResponse(content={
                "status": "no_images",
                "pdf_id": pdf_id,
                "message": "No images found in PDF or all images were too small",
                "images_extracted": 0
            })

        # Store images
        pool = await get_postgres_pool()
        repo = PostgresImageRepository(pool)
        saved_count = await repo.save_images(extracted_images)

        logger.info(f"Extracted and saved {saved_count} images for {pdf_id}")

        return JSONResponse(content={
            "status": "success",
            "pdf_id": pdf_id,
            "images_extracted": len(extracted_images),
            "images_saved": saved_count,
            "image_ids": [img["image_id"] for img in extracted_images[:10]]
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to extract images: {e}")
        raise HTTPException(status_code=500, detail=str(e))
