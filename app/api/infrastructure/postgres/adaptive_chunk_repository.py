"""
PostgreSQL Adaptive Chunk Repository
적응형 청크 저장소 (PostgreSQL + pgvector)

Stores adaptive chunks with embeddings for structure-preserving RAG.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from ...models.adaptive_chunk import (
    AdaptiveChunk,
    ChunkType,
    ChunkRelations,
    PDFStructureAnalysis,
    ChunkEmbeddingCoverage,
    CoverageReport,
    QualityMetrics,
    QualityLevel,
    DocumentType,
    SectionInfo,
    LayoutInfo,
)
from ...ports.adaptive_embedding_port import (
    AdaptiveChunkRepositoryPort,
    PDFStructureRepositoryPort,
    CoverageRepositoryPort,
)

logger = logging.getLogger(__name__)


class PostgresAdaptiveChunkRepository(AdaptiveChunkRepositoryPort):
    """
    Repository for storing and searching adaptive chunks with embeddings.
    Uses PostgreSQL with pgvector extension.
    """

    def __init__(self, pool):
        """Initialize with asyncpg connection pool."""
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        """Ensure tables exist (migration should handle this)."""
        if self._initialized:
            return
        self._initialized = True

    async def save_chunk(self, chunk: AdaptiveChunk) -> str:
        """Save a single adaptive chunk."""
        await self._ensure_table()

        has_embedding = chunk.has_embedding
        relations_json = json.dumps(chunk.relations.to_dict())
        acl_json = json.dumps(chunk.acl)
        metadata_json = json.dumps(chunk.metadata)

        async with self._pool.acquire() as conn:
            if has_embedding and chunk.embedding:
                embedding_str = "[" + ",".join(str(v) for v in chunk.embedding) + "]"
                await conn.execute("""
                    INSERT INTO adaptive_pdf_chunks
                    (pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                     section_path, section_title, parent_section_id, relations,
                     embedding, embedding_model_version, has_embedding,
                     chunk_version, content_hash, acl, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
                            $11::vector, $12, $13, $14, $15, $16::jsonb, $17::jsonb)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        page_start = EXCLUDED.page_start,
                        page_end = EXCLUDED.page_end,
                        section_path = EXCLUDED.section_path,
                        section_title = EXCLUDED.section_title,
                        parent_section_id = EXCLUDED.parent_section_id,
                        relations = EXCLUDED.relations,
                        embedding = EXCLUDED.embedding,
                        embedding_model_version = EXCLUDED.embedding_model_version,
                        has_embedding = EXCLUDED.has_embedding,
                        chunk_version = adaptive_pdf_chunks.chunk_version + 1,
                        content_hash = EXCLUDED.content_hash,
                        acl = EXCLUDED.acl,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, chunk.pdf_id, chunk.chunk_id, chunk.chunk_type.value,
                    chunk.content, chunk.page_start, chunk.page_end,
                    chunk.section_path, chunk.section_title, chunk.parent_section_id,
                    relations_json, embedding_str, chunk.embedding_model_version,
                    has_embedding, chunk.chunk_version, chunk.content_hash,
                    acl_json, metadata_json)
            else:
                await conn.execute("""
                    INSERT INTO adaptive_pdf_chunks
                    (pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                     section_path, section_title, parent_section_id, relations,
                     embedding_model_version, has_embedding,
                     chunk_version, content_hash, acl, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb,
                            $11, $12, $13, $14, $15::jsonb, $16::jsonb)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        page_start = EXCLUDED.page_start,
                        page_end = EXCLUDED.page_end,
                        section_path = EXCLUDED.section_path,
                        section_title = EXCLUDED.section_title,
                        parent_section_id = EXCLUDED.parent_section_id,
                        relations = EXCLUDED.relations,
                        embedding_model_version = EXCLUDED.embedding_model_version,
                        chunk_version = adaptive_pdf_chunks.chunk_version + 1,
                        content_hash = EXCLUDED.content_hash,
                        acl = EXCLUDED.acl,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, chunk.pdf_id, chunk.chunk_id, chunk.chunk_type.value,
                    chunk.content, chunk.page_start, chunk.page_end,
                    chunk.section_path, chunk.section_title, chunk.parent_section_id,
                    relations_json, chunk.embedding_model_version,
                    has_embedding, chunk.chunk_version, chunk.content_hash,
                    acl_json, metadata_json)

        return chunk.chunk_id

    async def save_chunks_batch(self, chunks: List[AdaptiveChunk]) -> int:
        """Save multiple chunks at once."""
        saved = 0
        for chunk in chunks:
            try:
                await self.save_chunk(chunk)
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save chunk {chunk.chunk_id}: {e}")
        return saved

    async def get_chunk(self, chunk_id: str) -> Optional[AdaptiveChunk]:
        """Get a chunk by ID."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                       section_path, section_title, parent_section_id, relations,
                       embedding_model_version, has_embedding, chunk_version,
                       content_hash, acl, metadata, created_at, updated_at
                FROM adaptive_pdf_chunks
                WHERE chunk_id = $1
            """, chunk_id)

            if not row:
                return None

            return self._row_to_chunk(row)

    async def get_chunks_by_pdf(
        self,
        pdf_id: str,
        chunk_type: Optional[ChunkType] = None
    ) -> List[AdaptiveChunk]:
        """Get all chunks for a PDF, optionally filtered by type."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if chunk_type:
                rows = await conn.fetch("""
                    SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                           section_path, section_title, parent_section_id, relations,
                           embedding_model_version, has_embedding, chunk_version,
                           content_hash, acl, metadata, created_at, updated_at
                    FROM adaptive_pdf_chunks
                    WHERE pdf_id = $1 AND chunk_type = $2
                    ORDER BY page_start, section_path
                """, pdf_id, chunk_type.value)
            else:
                rows = await conn.fetch("""
                    SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                           section_path, section_title, parent_section_id, relations,
                           embedding_model_version, has_embedding, chunk_version,
                           content_hash, acl, metadata, created_at, updated_at
                    FROM adaptive_pdf_chunks
                    WHERE pdf_id = $1
                    ORDER BY page_start, section_path
                """, pdf_id)

            return [self._row_to_chunk(row) for row in rows]

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.3,
        pdf_id: Optional[str] = None,
        chunk_types: Optional[List[ChunkType]] = None,
        section_path_prefix: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks by embedding."""
        await self._ensure_table()

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Build query with filters
        conditions = ["has_embedding = TRUE", f"1 - (embedding <=> $1::vector) >= {min_similarity}"]
        params = [embedding_str]
        param_idx = 2

        if pdf_id:
            conditions.append(f"pdf_id = ${param_idx}")
            params.append(pdf_id)
            param_idx += 1

        if chunk_types:
            type_values = [ct.value for ct in chunk_types]
            conditions.append(f"chunk_type = ANY(${param_idx})")
            params.append(type_values)
            param_idx += 1

        if section_path_prefix:
            conditions.append(f"section_path LIKE ${param_idx}")
            params.append(f"{section_path_prefix}%")
            param_idx += 1

        conditions.append(f"1 - (embedding <=> $1::vector) >= {min_similarity}")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT chunk_id, pdf_id, chunk_type, content, section_path,
                   section_title, page_start, page_end, relations,
                   1 - (embedding <=> $1::vector) as similarity
            FROM adaptive_pdf_chunks
            WHERE {where_clause}
            ORDER BY embedding <=> $1::vector
            LIMIT {limit}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

            results = []
            for row in rows:
                results.append({
                    "chunk_id": row["chunk_id"],
                    "pdf_id": row["pdf_id"],
                    "chunk_type": row["chunk_type"],
                    "content": row["content"],
                    "section_path": row["section_path"],
                    "section_title": row["section_title"],
                    "page_start": row["page_start"],
                    "page_end": row["page_end"],
                    "relations": row["relations"],
                    "similarity": float(row["similarity"])
                })

            return results

    async def update_embedding(
        self,
        chunk_id: str,
        embedding: List[float],
        model_version: str
    ) -> bool:
        """Update embedding for a chunk."""
        await self._ensure_table()

        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE adaptive_pdf_chunks
                SET embedding = $1::vector,
                    embedding_model_version = $2,
                    has_embedding = TRUE,
                    updated_at = NOW()
                WHERE chunk_id = $3
            """, embedding_str, model_version, chunk_id)

            return "UPDATE 1" in result

    async def delete_pdf_chunks(self, pdf_id: str) -> int:
        """Delete all chunks for a PDF."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM adaptive_pdf_chunks WHERE pdf_id = $1
            """, pdf_id)
            count = int(result.split()[-1])
            return count

    async def get_chunks_by_hash(self, content_hash: str) -> List[AdaptiveChunk]:
        """Get chunks by content hash."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                       section_path, section_title, parent_section_id, relations,
                       embedding_model_version, has_embedding, chunk_version,
                       content_hash, acl, metadata, created_at, updated_at
                FROM adaptive_pdf_chunks
                WHERE content_hash = $1
            """, content_hash)

            return [self._row_to_chunk(row) for row in rows]

    async def get_chunks_needing_embedding(self, pdf_id: str) -> List[AdaptiveChunk]:
        """Get chunks that don't have embeddings yet."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                       section_path, section_title, parent_section_id, relations,
                       embedding_model_version, has_embedding, chunk_version,
                       content_hash, acl, metadata, created_at, updated_at
                FROM adaptive_pdf_chunks
                WHERE pdf_id = $1 AND has_embedding = FALSE
                ORDER BY page_start, section_path
            """, pdf_id)

            return [self._row_to_chunk(row) for row in rows]

    def _row_to_chunk(self, row) -> AdaptiveChunk:
        """Convert database row to AdaptiveChunk."""
        relations_data = row["relations"] if isinstance(row["relations"], dict) else {}
        acl_data = row["acl"] if isinstance(row["acl"], dict) else {}
        metadata_data = row["metadata"] if isinstance(row["metadata"], dict) else {}

        return AdaptiveChunk(
            pdf_id=row["pdf_id"],
            chunk_id=row["chunk_id"],
            chunk_type=ChunkType(row["chunk_type"]),
            content=row["content"],
            page_start=row["page_start"],
            page_end=row["page_end"],
            section_path=row["section_path"],
            section_title=row["section_title"],
            parent_section_id=row["parent_section_id"],
            relations=ChunkRelations.from_dict(relations_data),
            embedding=None,  # Don't load embedding by default (large)
            embedding_model_version=row["embedding_model_version"],
            chunk_version=row["chunk_version"],
            content_hash=row["content_hash"],
            acl=acl_data,
            metadata=metadata_data,
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_chunks,
                    COUNT(*) FILTER (WHERE has_embedding = TRUE) as embedded_chunks,
                    COUNT(DISTINCT pdf_id) as total_documents,
                    COUNT(*) FILTER (WHERE chunk_type = 'TEXT_CHUNK') as text_chunks,
                    COUNT(*) FILTER (WHERE chunk_type = 'TABLE_CHUNK') as table_chunks,
                    COUNT(*) FILTER (WHERE chunk_type = 'IMAGE_CHUNK') as image_chunks,
                    COUNT(*) FILTER (WHERE chunk_type = 'OCR_CHUNK') as ocr_chunks
                FROM adaptive_pdf_chunks
            """)

            return {
                "total_chunks": row["total_chunks"],
                "embedded_chunks": row["embedded_chunks"],
                "total_documents": row["total_documents"],
                "by_type": {
                    "TEXT_CHUNK": row["text_chunks"],
                    "TABLE_CHUNK": row["table_chunks"],
                    "IMAGE_CHUNK": row["image_chunks"],
                    "OCR_CHUNK": row["ocr_chunks"]
                }
            }


class PostgresPDFStructureRepository(PDFStructureRepositoryPort):
    """Repository for PDF structure analysis persistence."""

    def __init__(self, pool):
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        if self._initialized:
            return
        self._initialized = True

    async def save_analysis(self, analysis: PDFStructureAnalysis) -> str:
        """Save structure analysis."""
        await self._ensure_table()

        hierarchy_json = json.dumps([s.to_dict() for s in analysis.hierarchy])
        layout_json = json.dumps(analysis.layout_info.to_dict())
        page_hashes_json = json.dumps(analysis.page_hashes)

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pdf_structure_analysis
                (pdf_id, document_type, hierarchy, layout_info, page_hashes,
                 total_pages, total_images, total_tables, language, analyzed_at)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10)
                ON CONFLICT (pdf_id) DO UPDATE SET
                    document_type = EXCLUDED.document_type,
                    hierarchy = EXCLUDED.hierarchy,
                    layout_info = EXCLUDED.layout_info,
                    page_hashes = EXCLUDED.page_hashes,
                    total_pages = EXCLUDED.total_pages,
                    total_images = EXCLUDED.total_images,
                    total_tables = EXCLUDED.total_tables,
                    language = EXCLUDED.language,
                    analyzed_at = EXCLUDED.analyzed_at,
                    updated_at = NOW()
            """, analysis.pdf_id, analysis.document_type.value, hierarchy_json,
                layout_json, page_hashes_json, analysis.total_pages,
                analysis.total_images, analysis.total_tables, analysis.language,
                analysis.analyzed_at or datetime.now(timezone.utc))

        return analysis.pdf_id

    async def get_analysis(self, pdf_id: str) -> Optional[PDFStructureAnalysis]:
        """Get structure analysis for a PDF."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pdf_id, document_type, hierarchy, layout_info, page_hashes,
                       total_pages, total_images, total_tables, language, analyzed_at
                FROM pdf_structure_analysis
                WHERE pdf_id = $1
            """, pdf_id)

            if not row:
                return None

            return self._row_to_analysis(row)

    async def delete_analysis(self, pdf_id: str) -> bool:
        """Delete structure analysis."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM pdf_structure_analysis WHERE pdf_id = $1
            """, pdf_id)
            return "DELETE 1" in result

    async def get_changed_pages(
        self,
        pdf_id: str,
        new_page_hashes: Dict[str, str]
    ) -> List[int]:
        """Compare page hashes and return changed page numbers."""
        analysis = await self.get_analysis(pdf_id)
        if not analysis:
            return list(range(1, len(new_page_hashes) + 1))

        changed = []
        old_hashes = analysis.page_hashes

        for page_str, new_hash in new_page_hashes.items():
            page_num = int(page_str)
            old_hash = old_hashes.get(page_str)
            if old_hash != new_hash:
                changed.append(page_num)

        # Also include deleted pages
        for page_str in old_hashes:
            if page_str not in new_page_hashes:
                changed.append(int(page_str))

        return sorted(set(changed))

    def _row_to_analysis(self, row) -> PDFStructureAnalysis:
        """Convert database row to PDFStructureAnalysis."""
        hierarchy_data = row["hierarchy"] if isinstance(row["hierarchy"], list) else []
        layout_data = row["layout_info"] if isinstance(row["layout_info"], dict) else {}
        page_hashes = row["page_hashes"] if isinstance(row["page_hashes"], dict) else {}

        sections = []
        for s in hierarchy_data:
            sections.append(SectionInfo(
                id=s.get("id", ""),
                title=s.get("title", ""),
                level=s.get("level", 0),
                page_start=s.get("page_start", 1),
                page_end=s.get("page_end", 1),
                parent_id=s.get("parent_id"),
                children=s.get("children", [])
            ))

        layout = LayoutInfo(
            columns=layout_data.get("columns", 1),
            has_header=layout_data.get("has_header", False),
            has_footer=layout_data.get("has_footer", False),
            has_toc=layout_data.get("has_toc", False),
            page_dimensions=layout_data.get("page_dimensions", {"width": 595, "height": 842})
        )

        return PDFStructureAnalysis(
            pdf_id=row["pdf_id"],
            document_type=DocumentType(row["document_type"]),
            hierarchy=sections,
            layout_info=layout,
            page_hashes=page_hashes,
            total_pages=row["total_pages"],
            total_images=row["total_images"],
            total_tables=row["total_tables"],
            language=row["language"],
            analyzed_at=row["analyzed_at"]
        )


class PostgresCoverageRepository(CoverageRepositoryPort):
    """Repository for embedding coverage persistence."""

    def __init__(self, pool):
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        if self._initialized:
            return
        self._initialized = True

    async def save_coverage(self, coverage: ChunkEmbeddingCoverage) -> str:
        """Save coverage report."""
        await self._ensure_table()

        coverage_report_json = json.dumps(coverage.coverage_report.to_dict())
        quality_metrics_json = json.dumps(coverage.quality_metrics.to_dict())

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chunk_embedding_coverage
                (pdf_id, text_coverage, table_coverage, image_coverage, ocr_coverage,
                 overall_coverage, coverage_report, quality_metrics, last_verified_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
                ON CONFLICT (pdf_id) DO UPDATE SET
                    text_coverage = EXCLUDED.text_coverage,
                    table_coverage = EXCLUDED.table_coverage,
                    image_coverage = EXCLUDED.image_coverage,
                    ocr_coverage = EXCLUDED.ocr_coverage,
                    overall_coverage = EXCLUDED.overall_coverage,
                    coverage_report = EXCLUDED.coverage_report,
                    quality_metrics = EXCLUDED.quality_metrics,
                    last_verified_at = EXCLUDED.last_verified_at,
                    updated_at = NOW()
            """, coverage.pdf_id, coverage.text_coverage, coverage.table_coverage,
                coverage.image_coverage, coverage.ocr_coverage, coverage.overall_coverage,
                coverage_report_json, quality_metrics_json,
                coverage.last_verified_at or datetime.now(timezone.utc))

        return coverage.pdf_id

    async def get_coverage(self, pdf_id: str) -> Optional[ChunkEmbeddingCoverage]:
        """Get coverage report for a PDF."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pdf_id, text_coverage, table_coverage, image_coverage,
                       ocr_coverage, overall_coverage, coverage_report,
                       quality_metrics, last_verified_at
                FROM chunk_embedding_coverage
                WHERE pdf_id = $1
            """, pdf_id)

            if not row:
                return None

            return self._row_to_coverage(row)

    async def update_quality_metrics(
        self,
        pdf_id: str,
        metrics: QualityMetrics
    ) -> bool:
        """Update quality metrics for a document."""
        await self._ensure_table()

        metrics_json = json.dumps(metrics.to_dict())

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE chunk_embedding_coverage
                SET quality_metrics = $1::jsonb,
                    last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE pdf_id = $2
            """, metrics_json, pdf_id)

            return "UPDATE 1" in result

    async def delete_coverage(self, pdf_id: str) -> bool:
        """Delete coverage report."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM chunk_embedding_coverage WHERE pdf_id = $1
            """, pdf_id)
            return "DELETE 1" in result

    def _row_to_coverage(self, row) -> ChunkEmbeddingCoverage:
        """Convert database row to ChunkEmbeddingCoverage."""
        coverage_data = row["coverage_report"] if isinstance(row["coverage_report"], dict) else {}
        metrics_data = row["quality_metrics"] if isinstance(row["quality_metrics"], dict) else {}

        coverage_report = CoverageReport(
            total_chunks=coverage_data.get("total_chunks", 0),
            embedded_chunks=coverage_data.get("embedded_chunks", 0),
            failed_chunks=coverage_data.get("failed_chunks", []),
            skipped_chunks=coverage_data.get("skipped_chunks", []),
            by_type=coverage_data.get("by_type", {})
        )

        quality_level_str = metrics_data.get("quality_level", "poor")
        try:
            quality_level = QualityLevel(quality_level_str)
        except ValueError:
            quality_level = QualityLevel.POOR

        quality_metrics = QualityMetrics(
            top_k_recall=metrics_data.get("top_k_recall", 0.0),
            section_precision=metrics_data.get("section_precision", 0.0),
            avg_similarity=metrics_data.get("avg_similarity", 0.0),
            embedding_dimension=metrics_data.get("embedding_dimension", 4096),
            quality_level=quality_level,
            hallucination_detected=metrics_data.get("hallucination_detected", False),
            hallucination_details=metrics_data.get("hallucination_details", [])
        )

        return ChunkEmbeddingCoverage(
            pdf_id=row["pdf_id"],
            text_coverage=row["text_coverage"],
            table_coverage=row["table_coverage"],
            image_coverage=row["image_coverage"],
            ocr_coverage=row["ocr_coverage"],
            overall_coverage=row["overall_coverage"],
            coverage_report=coverage_report,
            quality_metrics=quality_metrics,
            last_verified_at=row["last_verified_at"]
        )
