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

    async def save_chunks_batch(self, chunks: List[AdaptiveChunk], batch_size: int = 50) -> int:
        """
        Save multiple chunks at once using batch processing.
        Uses concurrent batch inserts for better performance.

        Args:
            chunks: List of chunks to save
            batch_size: Number of chunks per batch (default 50)

        Returns:
            Number of successfully saved chunks
        """
        if not chunks:
            return 0

        await self._ensure_table()
        saved = 0
        total = len(chunks)

        # Process in batches for better performance
        for i in range(0, total, batch_size):
            batch = chunks[i:i + batch_size]
            batch_saved = 0

            async with self._pool.acquire() as conn:
                # Use transaction for batch
                async with conn.transaction():
                    for chunk in batch:
                        try:
                            has_embedding = chunk.has_embedding
                            relations_json = json.dumps(chunk.relations.to_dict())
                            acl_json = json.dumps(chunk.acl)
                            metadata_json = json.dumps(chunk.metadata)

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
                                        embedding = EXCLUDED.embedding,
                                        has_embedding = EXCLUDED.has_embedding,
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
                                        updated_at = NOW()
                                """, chunk.pdf_id, chunk.chunk_id, chunk.chunk_type.value,
                                    chunk.content, chunk.page_start, chunk.page_end,
                                    chunk.section_path, chunk.section_title, chunk.parent_section_id,
                                    relations_json, chunk.embedding_model_version,
                                    has_embedding, chunk.chunk_version, chunk.content_hash,
                                    acl_json, metadata_json)

                            batch_saved += 1
                        except Exception as e:
                            logger.error(f"Failed to save chunk {chunk.chunk_id}: {e}")

            saved += batch_saved

            # Log progress every 500 chunks for large batches
            if total > 100 and saved % 500 < batch_size:
                logger.warning(f"SAVE_DEBUG: Saved {saved}/{total} chunks ({saved * 100 // total}%)")

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

    async def get_chunks_with_embeddings(
        self,
        pdf_id: str,
        limit: int = 100
    ) -> List[AdaptiveChunk]:
        """
        Get chunks for a PDF WITH their embedding vectors loaded.
        Use sparingly - embeddings are large (4096 floats each).

        Args:
            pdf_id: Document ID
            limit: Maximum chunks to load (default 100 to prevent memory issues)
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT pdf_id, chunk_id, chunk_type, content, page_start, page_end,
                       section_path, section_title, parent_section_id, relations,
                       embedding::text as embedding_text, embedding_model_version,
                       has_embedding, chunk_version, content_hash, acl, metadata,
                       created_at, updated_at
                FROM adaptive_pdf_chunks
                WHERE pdf_id = $1 AND has_embedding = TRUE
                ORDER BY page_start, section_path
                LIMIT $2
            """, pdf_id, limit)

            return [self._row_to_chunk_with_embedding(row) for row in rows]

    def _row_to_chunk_with_embedding(self, row) -> AdaptiveChunk:
        """Convert database row to AdaptiveChunk WITH embedding loaded."""
        relations_data = row["relations"] if isinstance(row["relations"], dict) else {}
        acl_data = row["acl"] if isinstance(row["acl"], dict) else {}
        metadata_data = row["metadata"] if isinstance(row["metadata"], dict) else {}

        # Parse embedding from text format "[0.1,0.2,...]"
        embedding = None
        if row.get("embedding_text"):
            try:
                emb_str = row["embedding_text"].strip("[]")
                if emb_str:
                    embedding = [float(x) for x in emb_str.split(",")]
            except Exception as e:
                logger.warning(f"Failed to parse embedding for {row['chunk_id']}: {e}")

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
            embedding=embedding,
            embedding_model_version=row["embedding_model_version"],
            chunk_version=row["chunk_version"],
            content_hash=row["content_hash"],
            acl=acl_data,
            metadata=metadata_data,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            _db_has_embedding=row["has_embedding"]
        )

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.3,
        pdf_id: Optional[str] = None,
        chunk_types: Optional[List[ChunkType]] = None,
        section_path_prefix: Optional[str] = None,
        keyword_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks by embedding with optional keyword filter."""
        await self._ensure_table()

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Build query with filters
        conditions = ["ac.has_embedding = TRUE", f"1 - (ac.embedding <=> $1::vector) >= {min_similarity}"]
        params = [embedding_str]
        param_idx = 2

        if pdf_id:
            conditions.append(f"ac.pdf_id = ${param_idx}")
            params.append(pdf_id)
            param_idx += 1

        if chunk_types:
            type_values = [ct.value for ct in chunk_types]
            conditions.append(f"ac.chunk_type = ANY(${param_idx})")
            params.append(type_values)
            param_idx += 1

        if section_path_prefix:
            conditions.append(f"ac.section_path LIKE ${param_idx}")
            params.append(f"{section_path_prefix}%")
            param_idx += 1

        # Keyword filter for exact matches (e.g., error codes like -5212)
        # Also search in section_title which often contains error code identifiers
        if keyword_filter:
            conditions.append(f"(ac.content ILIKE ${param_idx} OR ac.section_title ILIKE ${param_idx})")
            params.append(f"%{keyword_filter}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT ac.chunk_id, ac.pdf_id, ac.chunk_type, ac.content, ac.section_path,
                   ac.section_title, ac.page_start, ac.page_end, ac.relations,
                   1 - (ac.embedding <=> $1::vector) as similarity,
                   psa.document_name
            FROM adaptive_pdf_chunks ac
            LEFT JOIN pdf_structure_analysis psa ON ac.pdf_id = psa.pdf_id
            WHERE {where_clause}
            ORDER BY ac.embedding <=> $1::vector
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
                    "similarity": float(row["similarity"]),
                    "document_name": row.get("document_name")
                })

            return results

    async def search_hybrid(
        self,
        query_embedding: List[float],
        query_text: str,
        limit: int = 5,
        min_similarity: float = 0.2,
        pdf_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity with keyword boosting and synonym expansion.

        Improvements over basic search:
        1. Lower initial similarity threshold (0.2) to get more candidates
        2. Boost scores for keyword matches in title/content
        3. Detect "what is" intent and boost introduction/overview sections
        4. Synonym expansion for better keyword matching
        5. Re-rank results based on combined score
        6. Dynamic weight adjustment based on query type
        """
        await self._ensure_table()

        import re
        import logging
        logger = logging.getLogger(__name__)

        # Import synonym dictionary
        from ...services.synonym_dictionary import get_synonym_dictionary
        synonym_dict = get_synonym_dictionary()

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # =========================================================================
        # RECIPROCAL RANK FUSION (RRF) HYBRID SEARCH
        # =========================================================================
        # RRF combines vector search and keyword search using rank-based fusion:
        #   RRF_score(d) = 1/(k + vector_rank) + 1/(k + keyword_rank)
        # This approach is more robust than weighted score combination.
        # =========================================================================

        RRF_K = 60  # Standard RRF constant (higher = more weight to lower ranks)
        candidate_limit = limit * 5  # Fetch more candidates for fusion

        # Tokenize query for CJK languages (Japanese/Korean/Chinese don't have spaces)
        # Split on common particles and delimiters
        import re as re_module
        tokens = re_module.split(r'[のをはがでにと、。\s]+', query_text)
        tokens = [t for t in tokens if len(t) >= 2][:10]
        # Build OR-joined tsquery: 'token1' | 'token2' | ...
        ts_query_str = " | ".join(f"'{t}'" for t in tokens) if tokens else f"'{query_text}'"

        print(f"[HybridSearch] Keyword tokens: {tokens}", flush=True)

        # Build WHERE clause
        conditions = ["ac.has_embedding = TRUE"]
        params = [embedding_str]
        param_idx = 2

        if pdf_id:
            conditions.append(f"ac.pdf_id = ${param_idx}")
            params.append(pdf_id)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # RRF Query: Get both vector and keyword rankings, then fuse
        query = f"""
            WITH
            -- Step 1: Vector search results with ranking
            vector_results AS (
                SELECT
                    ac.chunk_id,
                    ac.pdf_id,
                    ac.chunk_type,
                    ac.content,
                    ac.section_path,
                    ac.section_title,
                    ac.page_start,
                    ac.page_end,
                    ac.relations,
                    psa.document_name,
                    1 - (ac.embedding <=> $1::vector) as vector_similarity,
                    ROW_NUMBER() OVER (ORDER BY ac.embedding <=> $1::vector) as vector_rank
                FROM adaptive_pdf_chunks ac
                LEFT JOIN pdf_structure_analysis psa ON ac.pdf_id = psa.pdf_id
                WHERE {where_clause}
                ORDER BY ac.embedding <=> $1::vector
                LIMIT {candidate_limit}
            ),
            -- Step 2: Keyword search results with ranking
            -- Uses ts_rank + exact substring match bonus
            keyword_results AS (
                SELECT
                    ac.chunk_id,
                    ts_rank(
                        to_tsvector('simple', ac.content),
                        to_tsquery('simple', $${ts_query_str}$$)
                    ) +
                    -- Exact substring match bonus: if content contains significant part of query
                    CASE WHEN ac.content LIKE '%' || $2 || '%' THEN 0.5 ELSE 0.0 END as keyword_score,
                    ROW_NUMBER() OVER (
                        ORDER BY (
                            ts_rank(
                                to_tsvector('simple', ac.content),
                                to_tsquery('simple', $${ts_query_str}$$)
                            ) +
                            CASE WHEN ac.content LIKE '%' || $2 || '%' THEN 0.5 ELSE 0.0 END
                        ) DESC
                    ) as keyword_rank
                FROM adaptive_pdf_chunks ac
                WHERE {where_clause}
                AND (
                    to_tsvector('simple', ac.content) @@ to_tsquery('simple', $${ts_query_str}$$)
                    OR ac.content LIKE '%' || $2 || '%'
                )
                ORDER BY keyword_score DESC
                LIMIT {candidate_limit}
            ),
            -- Step 3: RRF Fusion
            fused_results AS (
                SELECT
                    v.*,
                    COALESCE(k.keyword_score, 0) as keyword_score,
                    COALESCE(k.keyword_rank, {candidate_limit + 1}) as keyword_rank,
                    -- RRF Score: 1/(k + vector_rank) + 1/(k + keyword_rank)
                    (1.0 / ({RRF_K} + v.vector_rank)) +
                    (1.0 / ({RRF_K} + COALESCE(k.keyword_rank, {candidate_limit + 1}))) as rrf_score
                FROM vector_results v
                LEFT JOIN keyword_results k ON v.chunk_id = k.chunk_id
            )
            SELECT *
            FROM fused_results
            ORDER BY rrf_score DESC
            LIMIT {limit}
        """

        # Add query_text for exact substring matching ($2)
        params.append(query_text)

        print(f"[HybridSearch] Using RRF fusion (k={RRF_K})", flush=True)

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
                    "similarity": float(row["rrf_score"]),
                    "vector_similarity": float(row["vector_similarity"]),
                    "vector_rank": int(row["vector_rank"]),
                    "keyword_score": float(row["keyword_score"]),
                    "keyword_rank": int(row["keyword_rank"]),
                    "document_name": row.get("document_name"),
                })

            if results:
                top = results[0]
                logger.info(f"[HybridSearch-RRF] '{query_text[:50]}...' -> {len(results)} results, "
                           f"top: rrf={top['similarity']:.4f} (vec_rank={top['vector_rank']}, kw_rank={top['keyword_rank']})")
                print(f"[HybridSearch] RRF Results: {len(results)}, top: page {top['page_start']}-{top['page_end']} "
                      f"(vec_rank={top['vector_rank']}, kw_rank={top['keyword_rank']}, rrf={top['similarity']:.4f})", flush=True)
            else:
                logger.warning(f"[HybridSearch-RRF] No results for: '{query_text[:50]}...'")
                print(f"[HybridSearch] No RRF results", flush=True)

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
            updated_at=row["updated_at"],
            _db_has_embedding=row["has_embedding"]  # DB의 has_embedding 상태를 보존
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
                 total_pages, total_images, total_tables, language, analyzed_at, document_name)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7, $8, $9, $10, $11)
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
                    document_name = EXCLUDED.document_name,
                    updated_at = NOW()
            """, analysis.pdf_id, analysis.document_type.value, hierarchy_json,
                layout_json, page_hashes_json, analysis.total_pages,
                analysis.total_images, analysis.total_tables, analysis.language,
                analysis.analyzed_at or datetime.now(timezone.utc),
                analysis.document_name)

        return analysis.pdf_id

    async def get_analysis(self, pdf_id: str) -> Optional[PDFStructureAnalysis]:
        """Get structure analysis for a PDF."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pdf_id, document_type, hierarchy, layout_info, page_hashes,
                       total_pages, total_images, total_tables, language, analyzed_at,
                       document_name
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

    async def get_all_analyses(self) -> List[PDFStructureAnalysis]:
        """Get all structure analyses."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT pdf_id, document_type, hierarchy, layout_info, page_hashes,
                       total_pages, total_images, total_tables, language, analyzed_at,
                       document_name
                FROM pdf_structure_analysis
                ORDER BY analyzed_at DESC
            """)

            return [self._row_to_analysis(row) for row in rows]

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
        # Handle both list/dict and JSON string from DB (asyncpg may return str for JSONB)
        hierarchy_raw = row["hierarchy"]
        if isinstance(hierarchy_raw, str):
            try:
                hierarchy_data = json.loads(hierarchy_raw)
            except (json.JSONDecodeError, TypeError):
                hierarchy_data = []
        elif isinstance(hierarchy_raw, list):
            hierarchy_data = hierarchy_raw
        else:
            hierarchy_data = []

        layout_raw = row["layout_info"]
        if isinstance(layout_raw, str):
            try:
                layout_data = json.loads(layout_raw)
            except (json.JSONDecodeError, TypeError):
                layout_data = {}
        elif isinstance(layout_raw, dict):
            layout_data = layout_raw
        else:
            layout_data = {}

        page_hashes_raw = row["page_hashes"]
        if isinstance(page_hashes_raw, str):
            try:
                page_hashes = json.loads(page_hashes_raw)
            except (json.JSONDecodeError, TypeError):
                page_hashes = {}
        elif isinstance(page_hashes_raw, dict):
            page_hashes = page_hashes_raw
        else:
            page_hashes = {}

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
            analyzed_at=row["analyzed_at"],
            document_name=row.get("document_name")
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
        # Handle None quality_metrics (quality evaluation is now on-demand)
        quality_metrics_json = json.dumps(coverage.quality_metrics.to_dict()) if coverage.quality_metrics else None

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
        # Handle both dict and JSON string from DB (asyncpg may return str for JSONB)
        coverage_raw = row["coverage_report"]
        if isinstance(coverage_raw, str):
            try:
                coverage_data = json.loads(coverage_raw)
            except (json.JSONDecodeError, TypeError):
                coverage_data = {}
        elif isinstance(coverage_raw, dict):
            coverage_data = coverage_raw
        else:
            coverage_data = {}

        metrics_raw = row["quality_metrics"]
        if isinstance(metrics_raw, str):
            try:
                metrics_data = json.loads(metrics_raw)
            except (json.JSONDecodeError, TypeError):
                metrics_data = {}
        elif isinstance(metrics_raw, dict):
            metrics_data = metrics_raw
        else:
            metrics_data = {}

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
