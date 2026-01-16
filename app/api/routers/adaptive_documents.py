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
        # Process PDF
        result = await service.process_pdf(content, pdf_id, options)
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
