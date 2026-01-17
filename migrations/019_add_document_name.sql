-- Migration: 019_add_document_name.sql
-- Description: Add document_name column to pdf_structure_analysis for source tracking
-- Created: 2026-01-17

-- Add document_name column to pdf_structure_analysis
ALTER TABLE pdf_structure_analysis
ADD COLUMN IF NOT EXISTS document_name VARCHAR(500);

-- Add comment
COMMENT ON COLUMN pdf_structure_analysis.document_name IS 'Original document filename for source reference display';

-- Update search_adaptive_chunks function to include document_name
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
    similarity FLOAT,
    document_name VARCHAR
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
        1 - (ac.embedding <=> query_embedding) AS similarity,
        psa.document_name
    FROM adaptive_pdf_chunks ac
    LEFT JOIN pdf_structure_analysis psa ON ac.pdf_id = psa.pdf_id
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

-- Validation
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_name = 'pdf_structure_analysis' AND column_name = 'document_name'
    ) THEN
        RAISE NOTICE 'Migration 019_add_document_name completed successfully';
    ELSE
        RAISE EXCEPTION 'Migration 019_add_document_name failed';
    END IF;
END $$;
