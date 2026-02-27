-- Migration: 007_chunk_metadata_indexes.sql
-- Description: Add metadata search indexes for text_chunks table
-- Feature: chunking-embedding-analysis (H3)
-- Created: 2026-01-30

-- ============================================================================
-- 1. GIN Index for JSONB metadata search
-- ============================================================================
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_metadata_gin
ON text_chunks USING GIN (metadata jsonb_path_ops);

-- ============================================================================
-- 2. Add Generated Columns for frequently queried metadata fields
-- ============================================================================

-- section_path: extracted from metadata->>'section_path'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'text_chunks' AND column_name = 'section_path'
    ) THEN
        ALTER TABLE text_chunks
        ADD COLUMN section_path TEXT GENERATED ALWAYS AS (metadata->>'section_path') STORED;
    END IF;
END $$;

-- ============================================================================
-- 3. Individual B-tree Indexes for common queries
-- ============================================================================

-- Index on section_path for section-based filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_section_path
ON text_chunks(section_path)
WHERE section_path IS NOT NULL;

-- Index on page_number for page range queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_page_number
ON text_chunks(page_number)
WHERE page_number IS NOT NULL;

-- Index on chunk_type for type filtering
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_chunk_type
ON text_chunks(chunk_type);

-- ============================================================================
-- 4. Composite Indexes for common query patterns
-- ============================================================================

-- Document + section path (for "get chunks in section X of document Y")
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_doc_section
ON text_chunks(document_id, section_path)
WHERE section_path IS NOT NULL;

-- Document + page number (for "get chunks on pages X-Y of document Z")
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_doc_page
ON text_chunks(document_id, page_number)
WHERE page_number IS NOT NULL;

-- Document + chunk index (for ordered chunk retrieval)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_doc_index
ON text_chunks(document_id, chunk_index);

-- ============================================================================
-- 5. Partial Indexes for specific chunk types
-- ============================================================================

-- Error code chunks (frequently queried)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_error_code_type
ON text_chunks(document_id, chunk_index)
WHERE chunk_type = 'error_code';

-- Table chunks
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_table_type
ON text_chunks(document_id, chunk_index)
WHERE chunk_type = 'table';

-- ============================================================================
-- 6. Vector Index optimization (IVFFlat for faster ANN search)
-- ============================================================================

-- Drop old hnsw index if exists and create ivfflat for better performance
-- Note: Run this only if you have many chunks (>10K)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_text_chunks_embedding_ivfflat
-- ON text_chunks USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100)
-- WHERE has_embedding = TRUE;

-- ============================================================================
-- Verification queries (run manually to verify indexes)
-- ============================================================================
-- \di text_chunks*
-- EXPLAIN ANALYZE SELECT * FROM text_chunks WHERE section_path = '2.3.1';
-- EXPLAIN ANALYZE SELECT * FROM text_chunks WHERE page_number BETWEEN 10 AND 20;
-- EXPLAIN ANALYZE SELECT * FROM text_chunks WHERE metadata @> '{"chunk_type": "error_code"}';
