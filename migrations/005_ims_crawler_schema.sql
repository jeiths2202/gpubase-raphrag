-- ============================================================================
-- IMS Crawler Schema Migration
-- Version: 005
-- Description: Create tables for IMS Crawler integration
-- Features: User credentials, issues, attachments, crawl jobs, vector search
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for semantic search

-- ============================================================================
-- 1. User Credentials Table
-- Stores encrypted IMS credentials per user
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_user_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,  -- FK to users table
    ims_base_url VARCHAR(512) NOT NULL DEFAULT 'https://ims.tmaxsoft.com',

    -- Encrypted credentials (AES-256-GCM)
    encrypted_username BYTEA NOT NULL,
    encrypted_password BYTEA NOT NULL,

    -- Validation status
    is_validated BOOLEAN NOT NULL DEFAULT FALSE,
    last_validated_at TIMESTAMPTZ,
    validation_error TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ims_credentials_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT unique_user_credentials UNIQUE (user_id)
);

CREATE INDEX idx_ims_credentials_user ON ims_user_credentials(user_id);
CREATE INDEX idx_ims_credentials_validation ON ims_user_credentials(is_validated, last_validated_at);

COMMENT ON TABLE ims_user_credentials IS 'Encrypted IMS credentials per user';
COMMENT ON COLUMN ims_user_credentials.encrypted_username IS 'AES-256-GCM encrypted username';
COMMENT ON COLUMN ims_user_credentials.encrypted_password IS 'AES-256-GCM encrypted password';

-- ============================================================================
-- 2. IMS Issues Table
-- Stores crawled IMS issues with metadata
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_issues (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ims_id VARCHAR(128) NOT NULL,  -- IMS system ID (e.g., IMS-12345)
    user_id UUID NOT NULL,  -- User who crawled this issue

    -- Core attributes
    title TEXT NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'open',
    priority VARCHAR(50) NOT NULL DEFAULT 'medium',

    -- Metadata
    reporter VARCHAR(255),
    assignee VARCHAR(255),
    project_key VARCHAR(100),
    issue_type VARCHAR(100) DEFAULT 'Task',

    -- Content
    labels TEXT[],  -- Array of labels
    comments_count INTEGER DEFAULT 0,
    attachments_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Source tracking
    source_url TEXT,

    -- Custom fields (JSON for flexibility)
    custom_fields JSONB DEFAULT '{}',

    -- Constraints
    CONSTRAINT fk_ims_issue_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT unique_ims_id_per_user UNIQUE (user_id, ims_id)
);

-- Indexes for performance
CREATE INDEX idx_ims_issues_user ON ims_issues(user_id);
CREATE INDEX idx_ims_issues_ims_id ON ims_issues(ims_id);
CREATE INDEX idx_ims_issues_status ON ims_issues(status);
CREATE INDEX idx_ims_issues_priority ON ims_issues(priority);
CREATE INDEX idx_ims_issues_project ON ims_issues(project_key);
CREATE INDEX idx_ims_issues_created ON ims_issues(created_at DESC);
CREATE INDEX idx_ims_issues_labels ON ims_issues USING GIN(labels);
CREATE INDEX idx_ims_issues_custom_fields ON ims_issues USING GIN(custom_fields);

-- Full-text search index
CREATE INDEX idx_ims_issues_fulltext ON ims_issues USING GIN(
    to_tsvector('english',
        COALESCE(title, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(ims_id, '')
    )
);

COMMENT ON TABLE ims_issues IS 'Crawled IMS issues with metadata';
COMMENT ON COLUMN ims_issues.ims_id IS 'Original IMS system identifier';
COMMENT ON COLUMN ims_issues.custom_fields IS 'Additional IMS-specific fields';

-- ============================================================================
-- 3. IMS Issue Embeddings Table
-- Vector embeddings for semantic search
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_issue_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    issue_id UUID NOT NULL,

    -- Vector embedding (4096 dimensions for NV-EmbedQA)
    embedding vector(4096) NOT NULL,

    -- Embedding metadata
    embedding_model VARCHAR(100) DEFAULT 'nvidia/nv-embedqa-mistral-7b-v2',
    embedded_text TEXT,  -- Text that was embedded

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ims_embedding_issue FOREIGN KEY (issue_id) REFERENCES ims_issues(id) ON DELETE CASCADE,
    CONSTRAINT unique_issue_embedding UNIQUE (issue_id)
);

-- Vector similarity search index (IVFFlat for start, upgrade to HNSW if needed)
CREATE INDEX idx_ims_embeddings_vector ON ims_issue_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX idx_ims_embeddings_issue ON ims_issue_embeddings(issue_id);

COMMENT ON TABLE ims_issue_embeddings IS 'Vector embeddings for semantic search';
COMMENT ON COLUMN ims_issue_embeddings.embedding IS '4096-dim vector from NV-EmbedQA';

-- ============================================================================
-- 4. IMS Attachments Table
-- File attachments with extracted text
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    issue_id UUID NOT NULL,

    -- File attributes
    filename VARCHAR(512) NOT NULL,
    original_url TEXT,
    file_size BIGINT DEFAULT 0,  -- bytes
    mime_type VARCHAR(255) DEFAULT 'application/octet-stream',
    attachment_type VARCHAR(50) DEFAULT 'other',

    -- Extracted content
    extracted_text TEXT,
    text_length INTEGER DEFAULT 0,

    -- Metadata
    uploaded_by VARCHAR(255),
    uploaded_at TIMESTAMPTZ,

    -- Processing status
    is_processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    processing_error TEXT,

    -- Storage
    storage_path TEXT,  -- Local path or S3 key

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ims_attachment_issue FOREIGN KEY (issue_id) REFERENCES ims_issues(id) ON DELETE CASCADE
);

CREATE INDEX idx_ims_attachments_issue ON ims_attachments(issue_id);
CREATE INDEX idx_ims_attachments_type ON ims_attachments(attachment_type);
CREATE INDEX idx_ims_attachments_processed ON ims_attachments(is_processed);

-- Full-text search on extracted text
CREATE INDEX idx_ims_attachments_fulltext ON ims_attachments USING GIN(
    to_tsvector('english', COALESCE(extracted_text, ''))
);

COMMENT ON TABLE ims_attachments IS 'File attachments with extracted text';
COMMENT ON COLUMN ims_attachments.extracted_text IS 'Text extracted via PyPDF2, OCR, etc.';

-- ============================================================================
-- 5. IMS Crawl Jobs Table
-- Track crawling operations with progress
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_crawl_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,

    -- Query information
    raw_query TEXT NOT NULL,
    parsed_query TEXT,
    search_intent VARCHAR(50),

    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    current_step TEXT DEFAULT 'Initializing...',
    progress_percentage INTEGER DEFAULT 0 CHECK (progress_percentage BETWEEN 0 AND 100),

    -- Results
    issues_found INTEGER DEFAULT 0,
    issues_crawled INTEGER DEFAULT 0,
    attachments_processed INTEGER DEFAULT 0,
    related_issues_crawled INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Configuration
    include_attachments BOOLEAN DEFAULT TRUE,
    include_related_issues BOOLEAN DEFAULT TRUE,
    max_issues INTEGER DEFAULT 100,

    -- Results storage (array of issue IDs)
    result_issue_ids UUID[],

    -- Constraints
    CONSTRAINT fk_ims_crawl_job_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_ims_crawl_jobs_user ON ims_crawl_jobs(user_id);
CREATE INDEX idx_ims_crawl_jobs_status ON ims_crawl_jobs(status);
CREATE INDEX idx_ims_crawl_jobs_created ON ims_crawl_jobs(created_at DESC);

COMMENT ON TABLE ims_crawl_jobs IS 'Crawl job tracking with SSE progress updates';
COMMENT ON COLUMN ims_crawl_jobs.progress_percentage IS 'Real-time progress (0-100)';

-- ============================================================================
-- 6. IMS Related Issues Table
-- Junction table for issue relationships
-- ============================================================================

CREATE TABLE IF NOT EXISTS ims_issue_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_issue_id UUID NOT NULL,
    target_issue_id UUID NOT NULL,
    relation_type VARCHAR(50) NOT NULL,  -- 'blocks', 'relates_to', 'duplicates'

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ims_relation_source FOREIGN KEY (source_issue_id) REFERENCES ims_issues(id) ON DELETE CASCADE,
    CONSTRAINT fk_ims_relation_target FOREIGN KEY (target_issue_id) REFERENCES ims_issues(id) ON DELETE CASCADE,
    CONSTRAINT unique_relation UNIQUE (source_issue_id, target_issue_id, relation_type)
);

CREATE INDEX idx_ims_relations_source ON ims_issue_relations(source_issue_id);
CREATE INDEX idx_ims_relations_target ON ims_issue_relations(target_issue_id);
CREATE INDEX idx_ims_relations_type ON ims_issue_relations(relation_type);

COMMENT ON TABLE ims_issue_relations IS 'Issue-to-issue relationships for graph view';

-- ============================================================================
-- 7. Triggers for automatic timestamp updates
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_ims_credentials_timestamp
    BEFORE UPDATE ON ims_user_credentials
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_ims_issues_timestamp
    BEFORE UPDATE ON ims_issues
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 8. Utility Functions
-- ============================================================================

-- Function: Search issues by vector similarity
CREATE OR REPLACE FUNCTION search_ims_issues_by_vector(
    query_embedding vector(4096),
    user_filter UUID,
    similarity_threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    issue_id UUID,
    ims_id VARCHAR,
    title TEXT,
    similarity_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.id,
        i.ims_id,
        i.title,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM ims_issues i
    INNER JOIN ims_issue_embeddings e ON i.id = e.issue_id
    WHERE i.user_id = user_filter
        AND 1 - (e.embedding <=> query_embedding) > similarity_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION search_ims_issues_by_vector IS 'Vector similarity search for IMS issues';

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Grant permissions (adjust based on your user setup)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO raguser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO raguser;

-- Verification query
SELECT
    'IMS Crawler Schema Migration Complete' AS status,
    COUNT(*) FILTER (WHERE table_name LIKE 'ims_%') AS ims_tables_created
FROM information_schema.tables
WHERE table_schema = 'public';
