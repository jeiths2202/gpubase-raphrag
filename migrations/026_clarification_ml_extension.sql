-- Migration 026: Clarification ML Extension
-- Extends the query clarification system with:
-- 1. Entity embeddings for ML-based recommendations
-- 2. Term candidates table for auto-extracted terms from documents
--
-- Part of Phase 2: Extended Clarification - ML Recommendations & Auto Term Extraction

-- ============================================================================
-- 1. Add entity_embeddings column to ambiguous_terms
-- ============================================================================
-- Stores embedding vectors for each possible entity to enable
-- context-aware ML recommendations based on query similarity

ALTER TABLE ambiguous_terms
    ADD COLUMN IF NOT EXISTS entity_embeddings JSONB;

COMMENT ON COLUMN ambiguous_terms.entity_embeddings IS
    'Entity embedding vectors: {"entity_id": [0.1, 0.2, ...], ...} for ML recommendations';


-- ============================================================================
-- 2. Table: term_candidates
-- ============================================================================
-- Stores auto-extracted term candidates from uploaded documents
-- Requires admin review before becoming active ambiguous_terms

CREATE TABLE IF NOT EXISTS term_candidates (
    id SERIAL PRIMARY KEY,

    -- Term information
    term VARCHAR(100) NOT NULL,
    term_normalized VARCHAR(100) NOT NULL,

    -- Source document information
    source_document_id VARCHAR(100),
    source_document_name VARCHAR(500),
    extraction_context TEXT,               -- 추출된 문맥 (앞뒤 100자)

    -- Extraction metadata
    extraction_method VARCHAR(50) NOT NULL DEFAULT 'pattern',  -- pattern, ner, frequency
    confidence_score FLOAT DEFAULT 0.5,    -- 0.0 ~ 1.0
    suggested_category VARCHAR(50),
    occurrence_count INTEGER DEFAULT 1,

    -- Review workflow
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, approved, rejected, merged
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    approved_term_id INTEGER REFERENCES ambiguous_terms(id) ON DELETE SET NULL,
    rejection_reason TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for status-based filtering (most common query)
CREATE INDEX IF NOT EXISTS idx_tc_status ON term_candidates(status);

-- Index for finding duplicates by normalized term
CREATE INDEX IF NOT EXISTS idx_tc_term_normalized ON term_candidates(term_normalized);

-- Index for source document lookup
CREATE INDEX IF NOT EXISTS idx_tc_source_doc ON term_candidates(source_document_id);

-- Index for high-confidence candidates
CREATE INDEX IF NOT EXISTS idx_tc_confidence ON term_candidates(confidence_score DESC)
    WHERE status = 'pending';

-- Index for extraction method analytics
CREATE INDEX IF NOT EXISTS idx_tc_method ON term_candidates(extraction_method);

-- Composite index for common admin query
CREATE INDEX IF NOT EXISTS idx_tc_status_confidence ON term_candidates(status, confidence_score DESC);


-- ============================================================================
-- Table Comments
-- ============================================================================
COMMENT ON TABLE term_candidates IS
    'Auto-extracted term candidates from documents awaiting admin review';

COMMENT ON COLUMN term_candidates.term IS
    'Original term text as extracted from document (case preserved)';

COMMENT ON COLUMN term_candidates.term_normalized IS
    'Normalized form for deduplication (lowercase, trimmed)';

COMMENT ON COLUMN term_candidates.source_document_id IS
    'ID of the document this term was extracted from';

COMMENT ON COLUMN term_candidates.source_document_name IS
    'Name of the source document for display';

COMMENT ON COLUMN term_candidates.extraction_context IS
    'Surrounding text context where the term was found (~100 chars before/after)';

COMMENT ON COLUMN term_candidates.extraction_method IS
    'How the term was detected: pattern (regex), ner (named entity), frequency (statistical)';

COMMENT ON COLUMN term_candidates.confidence_score IS
    'ML confidence score (0.0-1.0) that this term needs clarification';

COMMENT ON COLUMN term_candidates.suggested_category IS
    'Auto-suggested category based on extraction context';

COMMENT ON COLUMN term_candidates.occurrence_count IS
    'Number of times this term appeared in source document';

COMMENT ON COLUMN term_candidates.status IS
    'Review status: pending, approved (→ ambiguous_terms), rejected, merged (into existing)';

COMMENT ON COLUMN term_candidates.reviewed_by IS
    'Admin user who reviewed this candidate';

COMMENT ON COLUMN term_candidates.reviewed_at IS
    'When the candidate was reviewed';

COMMENT ON COLUMN term_candidates.approved_term_id IS
    'Links to created/merged ambiguous_term after approval';

COMMENT ON COLUMN term_candidates.rejection_reason IS
    'Reason for rejection (for audit trail)';


-- ============================================================================
-- Trigger: Auto-update timestamp
-- ============================================================================
DROP TRIGGER IF EXISTS trg_tc_updated_at ON term_candidates;
CREATE TRIGGER trg_tc_updated_at
    BEFORE UPDATE ON term_candidates
    FOR EACH ROW EXECUTE FUNCTION update_clarification_timestamp();


-- ============================================================================
-- Helper Function: Merge occurrence counts for duplicate candidates
-- ============================================================================
CREATE OR REPLACE FUNCTION merge_term_candidate(
    p_term VARCHAR(100),
    p_source_document_id VARCHAR(100),
    p_source_document_name VARCHAR(500),
    p_extraction_context TEXT,
    p_extraction_method VARCHAR(50),
    p_confidence_score FLOAT,
    p_suggested_category VARCHAR(50)
) RETURNS INTEGER AS $$
DECLARE
    v_existing_id INTEGER;
    v_new_id INTEGER;
BEGIN
    -- Check for existing pending candidate with same normalized term
    SELECT id INTO v_existing_id
    FROM term_candidates
    WHERE term_normalized = LOWER(TRIM(p_term))
      AND status = 'pending'
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        -- Increment occurrence count and update confidence if higher
        UPDATE term_candidates
        SET occurrence_count = occurrence_count + 1,
            confidence_score = GREATEST(confidence_score, p_confidence_score),
            updated_at = NOW()
        WHERE id = v_existing_id;

        RETURN v_existing_id;
    ELSE
        -- Insert new candidate
        INSERT INTO term_candidates (
            term, term_normalized, source_document_id, source_document_name,
            extraction_context, extraction_method, confidence_score, suggested_category
        ) VALUES (
            p_term, LOWER(TRIM(p_term)), p_source_document_id, p_source_document_name,
            p_extraction_context, p_extraction_method, p_confidence_score, p_suggested_category
        )
        RETURNING id INTO v_new_id;

        RETURN v_new_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION merge_term_candidate IS
    'Insert or merge a term candidate, incrementing occurrence_count for duplicates';


-- ============================================================================
-- View: Pending candidates with context
-- ============================================================================
CREATE OR REPLACE VIEW v_pending_term_candidates AS
SELECT
    tc.id,
    tc.term,
    tc.term_normalized,
    tc.source_document_name,
    tc.extraction_context,
    tc.extraction_method,
    tc.confidence_score,
    tc.suggested_category,
    tc.occurrence_count,
    tc.created_at,
    -- Check if similar term already exists in ambiguous_terms
    CASE
        WHEN at.id IS NOT NULL THEN 'similar_exists'
        ELSE 'new'
    END AS match_status,
    at.id AS similar_term_id,
    at.term AS similar_term
FROM term_candidates tc
LEFT JOIN ambiguous_terms at
    ON at.term_normalized = tc.term_normalized
    OR at.term_normalized LIKE '%' || tc.term_normalized || '%'
    OR tc.term_normalized LIKE '%' || at.term_normalized || '%'
WHERE tc.status = 'pending'
ORDER BY tc.confidence_score DESC, tc.occurrence_count DESC;

COMMENT ON VIEW v_pending_term_candidates IS
    'Pending candidates with similarity check against existing ambiguous_terms';


-- ============================================================================
-- Rollback Instructions
-- ============================================================================
-- To rollback this migration:
--
-- DROP VIEW IF EXISTS v_pending_term_candidates;
-- DROP FUNCTION IF EXISTS merge_term_candidate;
-- DROP TRIGGER IF EXISTS trg_tc_updated_at ON term_candidates;
-- DROP TABLE IF EXISTS term_candidates;
-- ALTER TABLE ambiguous_terms DROP COLUMN IF EXISTS entity_embeddings;
