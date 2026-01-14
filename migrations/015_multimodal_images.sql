-- Migration: 015_multimodal_images.sql
-- Description: Add tables for multimodal RAG image storage and embeddings
-- Created: 2025-01-13

-- Enable pgvector extension if not exists
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- IMAGE EMBEDDINGS TABLE
-- Stores extracted images from documents with their embeddings
-- ============================================================================

CREATE TABLE IF NOT EXISTS image_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR(255) NOT NULL,
    image_id VARCHAR(255) NOT NULL UNIQUE,
    page_number INTEGER,

    -- Image data stored as BYTEA (binary)
    image_data BYTEA NOT NULL,
    mime_type VARCHAR(50) NOT NULL DEFAULT 'image/png',
    width INTEGER,
    height INTEGER,
    file_size INTEGER,

    -- Position in document (JSON: {x, y, width, height})
    position JSONB,

    -- VLM-generated description
    description TEXT,
    alt_text TEXT,

    -- Embedding vector (bakllava: 4096 dimensions)
    embedding vector(4096),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Index for document lookup
CREATE INDEX IF NOT EXISTS idx_image_embeddings_document_id
    ON image_embeddings(document_id);

-- Index for image_id lookup
CREATE INDEX IF NOT EXISTS idx_image_embeddings_image_id
    ON image_embeddings(image_id);

-- Index for page number queries
CREATE INDEX IF NOT EXISTS idx_image_embeddings_page_number
    ON image_embeddings(document_id, page_number);

-- Vector similarity index
-- NOTE: pgvector HNSW/IVFFlat indexes are limited to 2000 dimensions.
-- bakllava embeddings are 4096 dimensions, so we cannot use vector indexes.
-- Similarity search will use sequential scan (acceptable for <100k images).
-- For larger datasets, consider:
--   1. Dimensionality reduction (PCA to 2000 dims)
--   2. External vector DB (Milvus, Qdrant, Pinecone)
--   3. Different embedding model with <=2000 dimensions
--
-- Uncomment below if using <=2000 dimension embeddings:
-- CREATE INDEX IF NOT EXISTS idx_image_embeddings_vector
--     ON image_embeddings
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- DOCUMENT-IMAGE RELATIONSHIP (optional: if documents table exists)
-- ============================================================================

-- Add foreign key if documents table exists (wrapped in DO block for safety)
DO $$
BEGIN
    -- Check if documents table exists and add foreign key
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'documents'
    ) THEN
        -- Only add if constraint doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_image_embeddings_document'
        ) THEN
            ALTER TABLE image_embeddings
            ADD CONSTRAINT fk_image_embeddings_document
            FOREIGN KEY (document_id)
            REFERENCES documents(id)
            ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to search images by vector similarity
CREATE OR REPLACE FUNCTION search_similar_images(
    query_embedding vector(4096),
    match_count INTEGER DEFAULT 5,
    min_similarity FLOAT DEFAULT 0.5,
    filter_document_id VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id VARCHAR,
    image_id VARCHAR,
    page_number INTEGER,
    description TEXT,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ie.id,
        ie.document_id,
        ie.image_id,
        ie.page_number,
        ie.description,
        1 - (ie.embedding <=> query_embedding) AS similarity
    FROM image_embeddings ie
    WHERE
        (filter_document_id IS NULL OR ie.document_id = filter_document_id)
        AND ie.embedding IS NOT NULL
        AND 1 - (ie.embedding <=> query_embedding) >= min_similarity
    ORDER BY ie.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get images by document
CREATE OR REPLACE FUNCTION get_document_images(
    doc_id VARCHAR
)
RETURNS TABLE (
    id UUID,
    image_id VARCHAR,
    page_number INTEGER,
    description TEXT,
    alt_text TEXT,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ie.id,
        ie.image_id,
        ie.page_number,
        ie.description,
        ie.alt_text,
        ie.width,
        ie.height,
        ie.created_at
    FROM image_embeddings ie
    WHERE ie.document_id = doc_id
    ORDER BY ie.page_number, ie.created_at;
END;
$$ LANGUAGE plpgsql;

-- Function to update timestamp on update
CREATE OR REPLACE FUNCTION update_image_embeddings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS trigger_image_embeddings_updated_at ON image_embeddings;
CREATE TRIGGER trigger_image_embeddings_updated_at
    BEFORE UPDATE ON image_embeddings
    FOR EACH ROW
    EXECUTE FUNCTION update_image_embeddings_updated_at();

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE image_embeddings IS 'Stores extracted images from documents with their vector embeddings for multimodal RAG';
COMMENT ON COLUMN image_embeddings.embedding IS 'Vector embedding from Ollama bakllava model (4096 dimensions)';
COMMENT ON COLUMN image_embeddings.description IS 'VLM-generated description of the image content';
COMMENT ON COLUMN image_embeddings.position IS 'Position of image in document page as JSON {x, y, width, height}';

-- ============================================================================
-- SAMPLE DATA VALIDATION (optional)
-- ============================================================================

-- Verify table was created
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = 'image_embeddings'
    ) THEN
        RAISE NOTICE 'Migration 015_multimodal_images completed successfully';
    ELSE
        RAISE EXCEPTION 'Migration 015_multimodal_images failed: table not created';
    END IF;
END $$;
