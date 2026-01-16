-- Migration: 016_fix_text_chunks_dimension.sql
-- Description: Fix text_chunks embedding dimension from 768 to 4096
-- Issue: text_chunk_repository.py was creating table with vector(768)
--        but NIM embedding model (nvidia/nv-embedqa-mistral-7b-v2) generates 4096-dim vectors
-- Created: 2026-01-15

-- ============================================================================
-- STEP 1: Check if text_chunks table exists with wrong dimension
-- ============================================================================

DO $$
DECLARE
    current_dimension INTEGER;
    column_exists BOOLEAN;
BEGIN
    -- Check if table and column exist
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'text_chunks' AND column_name = 'embedding'
    ) INTO column_exists;

    IF NOT column_exists THEN
        RAISE NOTICE 'text_chunks table does not exist or has no embedding column. Skipping migration.';
        RETURN;
    END IF;

    -- Get current vector dimension
    -- pgvector stores dimension info in the column type
    SELECT atttypmod INTO current_dimension
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    WHERE c.relname = 'text_chunks' AND a.attname = 'embedding';

    IF current_dimension = 768 THEN
        RAISE NOTICE 'text_chunks.embedding has dimension 768, needs migration to 4096';

        -- Step 1: Create temporary table with correct schema
        CREATE TABLE IF NOT EXISTS text_chunks_new (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_length INTEGER DEFAULT 0,
            chunk_type TEXT DEFAULT 'text',
            page_number INTEGER,
            embedding vector(4096),  -- Correct dimension for NIM embeddings
            has_embedding BOOLEAN DEFAULT FALSE,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- Step 2: Copy existing data (embeddings will be NULL, need re-embedding)
        INSERT INTO text_chunks_new (
            id, document_id, chunk_index, content, content_length,
            chunk_type, page_number, has_embedding, metadata,
            created_at, updated_at
        )
        SELECT
            id, document_id, chunk_index, content, content_length,
            chunk_type, page_number, FALSE,  -- Mark as needs re-embedding
            metadata, created_at, updated_at
        FROM text_chunks
        ON CONFLICT (id) DO NOTHING;

        -- Step 3: Drop old table
        DROP TABLE text_chunks;

        -- Step 4: Rename new table
        ALTER TABLE text_chunks_new RENAME TO text_chunks;

        -- Step 5: Recreate indexes
        CREATE INDEX IF NOT EXISTS idx_text_chunks_document_id
            ON text_chunks(document_id);
        CREATE INDEX IF NOT EXISTS idx_text_chunks_has_embedding
            ON text_chunks(has_embedding);
        CREATE INDEX IF NOT EXISTS idx_text_chunks_chunk_type
            ON text_chunks(chunk_type);

        RAISE NOTICE 'Migration completed: text_chunks.embedding changed to vector(4096)';
        RAISE NOTICE 'NOTE: All existing embeddings have been cleared. Documents need to be re-embedded.';

    ELSIF current_dimension = 4096 THEN
        RAISE NOTICE 'text_chunks.embedding already has correct dimension 4096. No migration needed.';
    ELSE
        RAISE NOTICE 'text_chunks.embedding has unexpected dimension %. Manual review needed.', current_dimension;
    END IF;

END $$;

-- ============================================================================
-- STEP 2: Ensure text_chunks table exists with correct schema (for fresh installs)
-- ============================================================================

CREATE TABLE IF NOT EXISTS text_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_length INTEGER DEFAULT 0,
    chunk_type TEXT DEFAULT 'text',
    page_number INTEGER,
    embedding vector(4096),  -- NIM embedding dimension (nvidia/nv-embedqa-mistral-7b-v2)
    has_embedding BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- STEP 3: Ensure indexes exist
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_text_chunks_document_id
    ON text_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_text_chunks_has_embedding
    ON text_chunks(has_embedding);
CREATE INDEX IF NOT EXISTS idx_text_chunks_chunk_type
    ON text_chunks(chunk_type);

-- ============================================================================
-- DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE text_chunks IS 'Stores text chunks from documents with vector embeddings for RAG search';
COMMENT ON COLUMN text_chunks.embedding IS 'Vector embedding from NIM nvidia/nv-embedqa-mistral-7b-v2 (4096 dimensions)';
COMMENT ON COLUMN text_chunks.has_embedding IS 'TRUE when embedding vector is populated and valid';

-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    final_dimension INTEGER;
BEGIN
    SELECT atttypmod INTO final_dimension
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    WHERE c.relname = 'text_chunks' AND a.attname = 'embedding';

    IF final_dimension = 4096 THEN
        RAISE NOTICE 'Migration 016_fix_text_chunks_dimension completed successfully. Dimension: 4096';
    ELSE
        RAISE WARNING 'Migration may have failed. Current dimension: %', final_dimension;
    END IF;
END $$;
