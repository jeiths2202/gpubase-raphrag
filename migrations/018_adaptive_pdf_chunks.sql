-- Migration: 018_adaptive_pdf_chunks.sql
-- Description: Add tables for adaptive PDF chunking with semantic boundaries
-- Created: 2026-01-16

-- Enable pgvector extension if not exists
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- ADAPTIVE PDF CHUNKS TABLE
-- Stores chunks with semantic boundaries, relationships, and embeddings
-- ============================================================================

CREATE TABLE IF NOT EXISTS adaptive_pdf_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pdf_id VARCHAR(255) NOT NULL,
    chunk_id VARCHAR(255) NOT NULL UNIQUE,

    -- Chunk type classification
    chunk_type VARCHAR(50) NOT NULL DEFAULT 'TEXT_CHUNK',
    -- Types: TEXT_CHUNK, TABLE_CHUNK, IMAGE_CHUNK, OCR_CHUNK

    -- Content
    content TEXT NOT NULL,
    content_length INTEGER GENERATED ALWAYS AS (LENGTH(content)) STORED,

    -- Page information
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,

    -- Section hierarchy
    section_path VARCHAR(100),  -- e.g., "2.3.1"
    section_title VARCHAR(500),
    parent_section_id VARCHAR(255),

    -- Relationships to other chunks
    relations JSONB DEFAULT '{}',
    -- Structure: {
    --   "previous": "chunk_id",
    --   "next": "chunk_id",
    --   "references": ["chunk_id1", "chunk_id2"],
    --   "parent": "chunk_id",
    --   "children": ["chunk_id1", "chunk_id2"]
    -- }

    -- Embedding
    embedding vector(4096),
    embedding_model_version VARCHAR(100) DEFAULT 'nv-embedqa-mistral-7b-v2',
    has_embedding BOOLEAN DEFAULT FALSE,

    -- Versioning and change detection
    chunk_version INTEGER DEFAULT 1,
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 for incremental re-embedding

    -- Security
    acl JSONB DEFAULT '{}',
    -- Structure: {"read": ["user_id1"], "write": ["admin"]}

    -- Metadata
    metadata JSONB DEFAULT '{}',
    -- Structure: {
    --   "source_image_id": "img_xxx",
    --   "source_table_id": "tbl_xxx",
    --   "language": "ja",
    --   "confidence": 0.95,
    --   "ocr_applied": true
    -- }

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PDF STRUCTURE ANALYSIS TABLE
-- Stores document-level structure analysis results
-- ============================================================================

CREATE TABLE IF NOT EXISTS pdf_structure_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pdf_id VARCHAR(255) NOT NULL UNIQUE,

    -- Document classification
    document_type VARCHAR(100) NOT NULL DEFAULT 'unknown',
    -- Types: manual, report, paper, contract, presentation, form, other

    -- Hierarchy structure
    hierarchy JSONB NOT NULL DEFAULT '[]',
    -- Structure: [
    --   {"id": "1", "title": "Introduction", "level": 1, "page_start": 1, "page_end": 5},
    --   {"id": "1.1", "title": "Background", "level": 2, "page_start": 1, "page_end": 2}
    -- ]

    -- Layout analysis
    layout_info JSONB DEFAULT '{}',
    -- Structure: {
    --   "columns": 1,
    --   "has_header": true,
    --   "has_footer": true,
    --   "has_toc": true,
    --   "page_dimensions": {"width": 595, "height": 842}
    -- }

    -- Page hashes for incremental processing
    page_hashes JSONB DEFAULT '{}',
    -- Structure: {"1": "sha256_hash", "2": "sha256_hash"}

    -- Processing info
    total_pages INTEGER DEFAULT 0,
    total_images INTEGER DEFAULT 0,
    total_tables INTEGER DEFAULT 0,
    language VARCHAR(10) DEFAULT 'auto',

    -- Timestamps
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- CHUNK EMBEDDING COVERAGE TABLE
-- Tracks embedding coverage and quality per document
-- ============================================================================

CREATE TABLE IF NOT EXISTS chunk_embedding_coverage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pdf_id VARCHAR(255) NOT NULL UNIQUE,

    -- Coverage percentages (0.0 - 1.0)
    text_coverage FLOAT DEFAULT 0.0,
    table_coverage FLOAT DEFAULT 0.0,
    image_coverage FLOAT DEFAULT 0.0,
    ocr_coverage FLOAT DEFAULT 0.0,
    overall_coverage FLOAT DEFAULT 0.0,

    -- Coverage report details
    coverage_report JSONB DEFAULT '{}',
    -- Structure: {
    --   "total_chunks": 100,
    --   "embedded_chunks": 95,
    --   "failed_chunks": ["chunk_id1", "chunk_id2"],
    --   "skipped_chunks": ["chunk_id3"],
    --   "by_type": {
    --     "TEXT_CHUNK": {"total": 80, "embedded": 78},
    --     "TABLE_CHUNK": {"total": 10, "embedded": 10}
    --   }
    -- }

    -- Quality metrics
    quality_metrics JSONB DEFAULT '{}',
    -- Structure: {
    --   "top_k_recall": 0.85,
    --   "section_precision": 0.92,
    --   "avg_similarity": 0.78,
    --   "embedding_dimension": 4096,
    --   "quality_level": "good"
    -- }

    -- Timestamps
    last_verified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Adaptive PDF Chunks indexes
CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_pdf_id
    ON adaptive_pdf_chunks(pdf_id);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_chunk_type
    ON adaptive_pdf_chunks(chunk_type);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_section_path
    ON adaptive_pdf_chunks(section_path);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_pages
    ON adaptive_pdf_chunks(pdf_id, page_start, page_end);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_content_hash
    ON adaptive_pdf_chunks(content_hash);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_has_embedding
    ON adaptive_pdf_chunks(has_embedding);

CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_parent_section
    ON adaptive_pdf_chunks(parent_section_id);

-- GIN index for JSONB relations
CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_relations
    ON adaptive_pdf_chunks USING gin(relations);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_adaptive_chunks_content_fts
    ON adaptive_pdf_chunks USING gin(to_tsvector('simple', content));

-- PDF Structure Analysis indexes
CREATE INDEX IF NOT EXISTS idx_structure_analysis_document_type
    ON pdf_structure_analysis(document_type);

-- Coverage indexes
CREATE INDEX IF NOT EXISTS idx_coverage_overall
    ON chunk_embedding_coverage(overall_coverage);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to search adaptive chunks by vector similarity
CREATE OR REPLACE FUNCTION search_adaptive_chunks(
    query_embedding vector(4096),
    match_count INTEGER DEFAULT 5,
    min_similarity FLOAT DEFAULT 0.3,
    filter_pdf_id VARCHAR DEFAULT NULL,
    filter_chunk_types VARCHAR[] DEFAULT NULL,
    filter_section_path VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    chunk_id VARCHAR,
    pdf_id VARCHAR,
    chunk_type VARCHAR,
    content TEXT,
    section_path VARCHAR,
    section_title VARCHAR,
    page_start INTEGER,
    page_end INTEGER,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ac.chunk_id,
        ac.pdf_id,
        ac.chunk_type,
        ac.content,
        ac.section_path,
        ac.section_title,
        ac.page_start,
        ac.page_end,
        1 - (ac.embedding <=> query_embedding) AS similarity
    FROM adaptive_pdf_chunks ac
    WHERE
        ac.has_embedding = TRUE
        AND (filter_pdf_id IS NULL OR ac.pdf_id = filter_pdf_id)
        AND (filter_chunk_types IS NULL OR ac.chunk_type = ANY(filter_chunk_types))
        AND (filter_section_path IS NULL OR ac.section_path LIKE filter_section_path || '%')
        AND 1 - (ac.embedding <=> query_embedding) >= min_similarity
    ORDER BY ac.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get chunk hierarchy
CREATE OR REPLACE FUNCTION get_chunk_hierarchy(
    target_pdf_id VARCHAR
)
RETURNS TABLE (
    chunk_id VARCHAR,
    section_path VARCHAR,
    section_title VARCHAR,
    chunk_type VARCHAR,
    page_start INTEGER,
    page_end INTEGER,
    level INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ac.chunk_id,
        ac.section_path,
        ac.section_title,
        ac.chunk_type,
        ac.page_start,
        ac.page_end,
        COALESCE(ARRAY_LENGTH(STRING_TO_ARRAY(ac.section_path, '.'), 1), 0) AS level
    FROM adaptive_pdf_chunks ac
    WHERE ac.pdf_id = target_pdf_id
    ORDER BY ac.section_path NULLS LAST, ac.page_start;
END;
$$ LANGUAGE plpgsql;

-- Function to get related chunks
CREATE OR REPLACE FUNCTION get_related_chunks(
    target_chunk_id VARCHAR
)
RETURNS TABLE (
    chunk_id VARCHAR,
    relation_type VARCHAR,
    content TEXT,
    section_path VARCHAR
) AS $$
DECLARE
    chunk_relations JSONB;
BEGIN
    -- Get relations for the target chunk
    SELECT relations INTO chunk_relations
    FROM adaptive_pdf_chunks
    WHERE chunk_id = target_chunk_id;

    -- Return related chunks
    RETURN QUERY
    SELECT
        ac.chunk_id,
        CASE
            WHEN ac.chunk_id = chunk_relations->>'previous' THEN 'previous'
            WHEN ac.chunk_id = chunk_relations->>'next' THEN 'next'
            WHEN ac.chunk_id = ANY(ARRAY(SELECT jsonb_array_elements_text(chunk_relations->'references'))) THEN 'reference'
            WHEN ac.chunk_id = chunk_relations->>'parent' THEN 'parent'
            WHEN ac.chunk_id = ANY(ARRAY(SELECT jsonb_array_elements_text(chunk_relations->'children'))) THEN 'child'
        END AS relation_type,
        ac.content,
        ac.section_path
    FROM adaptive_pdf_chunks ac
    WHERE ac.chunk_id IN (
        chunk_relations->>'previous',
        chunk_relations->>'next',
        chunk_relations->>'parent'
    )
    OR ac.chunk_id = ANY(ARRAY(SELECT jsonb_array_elements_text(chunk_relations->'references')))
    OR ac.chunk_id = ANY(ARRAY(SELECT jsonb_array_elements_text(chunk_relations->'children')));
END;
$$ LANGUAGE plpgsql;

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_adaptive_chunks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Auto-update timestamps for adaptive_pdf_chunks
DROP TRIGGER IF EXISTS trigger_adaptive_chunks_updated_at ON adaptive_pdf_chunks;
CREATE TRIGGER trigger_adaptive_chunks_updated_at
    BEFORE UPDATE ON adaptive_pdf_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_adaptive_chunks_updated_at();

-- Auto-update timestamps for pdf_structure_analysis
DROP TRIGGER IF EXISTS trigger_structure_analysis_updated_at ON pdf_structure_analysis;
CREATE TRIGGER trigger_structure_analysis_updated_at
    BEFORE UPDATE ON pdf_structure_analysis
    FOR EACH ROW
    EXECUTE FUNCTION update_adaptive_chunks_updated_at();

-- Auto-update timestamps for chunk_embedding_coverage
DROP TRIGGER IF EXISTS trigger_coverage_updated_at ON chunk_embedding_coverage;
CREATE TRIGGER trigger_coverage_updated_at
    BEFORE UPDATE ON chunk_embedding_coverage
    FOR EACH ROW
    EXECUTE FUNCTION update_adaptive_chunks_updated_at();

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE adaptive_pdf_chunks IS 'Stores PDF chunks with semantic boundaries, hierarchical relationships, and vector embeddings';
COMMENT ON COLUMN adaptive_pdf_chunks.chunk_type IS 'Chunk type: TEXT_CHUNK, TABLE_CHUNK, IMAGE_CHUNK, OCR_CHUNK';
COMMENT ON COLUMN adaptive_pdf_chunks.section_path IS 'Hierarchical section path (e.g., 2.3.1)';
COMMENT ON COLUMN adaptive_pdf_chunks.relations IS 'Relationships to other chunks (previous, next, references, parent, children)';
COMMENT ON COLUMN adaptive_pdf_chunks.content_hash IS 'SHA-256 hash for incremental re-embedding detection';

COMMENT ON TABLE pdf_structure_analysis IS 'Stores document-level structure analysis for adaptive chunking';
COMMENT ON COLUMN pdf_structure_analysis.document_type IS 'Document type: manual, report, paper, contract, presentation, form';
COMMENT ON COLUMN pdf_structure_analysis.hierarchy IS 'Document section hierarchy extracted from structure analysis';

COMMENT ON TABLE chunk_embedding_coverage IS 'Tracks embedding coverage and quality metrics per document';
COMMENT ON COLUMN chunk_embedding_coverage.quality_metrics IS 'Quality metrics including top-k recall and section precision';

-- ============================================================================
-- VALIDATION
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'adaptive_pdf_chunks'
    ) AND EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'pdf_structure_analysis'
    ) AND EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'chunk_embedding_coverage'
    ) THEN
        RAISE NOTICE 'Migration 018_adaptive_pdf_chunks completed successfully';
    ELSE
        RAISE EXCEPTION 'Migration 018_adaptive_pdf_chunks failed: not all tables created';
    END IF;
END $$;
