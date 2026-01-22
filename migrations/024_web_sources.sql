-- Migration 024: Web Sources Persistence
-- Stores web page knowledge sources for RAG with chunking and embedding

-- Create web_sources table
CREATE TABLE IF NOT EXISTS web_sources (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID,
    url TEXT NOT NULL,
    display_name VARCHAR(500),
    domain VARCHAR(255),
    extractor VARCHAR(50) DEFAULT 'trafilatura',
    include_images BOOLEAN DEFAULT FALSE,
    include_links BOOLEAN DEFAULT FALSE,
    status VARCHAR(50) DEFAULT 'pending',
    http_status_code INTEGER,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    extracted_text TEXT,
    extracted_links JSONB DEFAULT '[]',
    extracted_images JSONB DEFAULT '[]',
    content_hash VARCHAR(64),
    metadata JSONB DEFAULT '{}',
    word_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    link_count INTEGER DEFAULT 0,
    image_count INTEGER DEFAULT 0,
    fetch_time_ms INTEGER DEFAULT 0,
    extraction_time_ms INTEGER DEFAULT 0,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    fetched_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ws_user_id ON web_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_ws_status ON web_sources(status);
CREATE INDEX IF NOT EXISTS idx_ws_domain ON web_sources(domain);
CREATE INDEX IF NOT EXISTS idx_ws_created_at ON web_sources(created_at DESC);

-- Unique constraint on URL per user (allow same URL for different users)
CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_url_user ON web_sources(url, user_id);

-- Index for tag searches
CREATE INDEX IF NOT EXISTS idx_ws_tags ON web_sources USING GIN(tags);

-- Full-text search index on extracted_text
CREATE INDEX IF NOT EXISTS idx_ws_extracted_text_fts
    ON web_sources USING GIN(to_tsvector('simple', COALESCE(extracted_text, '')));

COMMENT ON TABLE web_sources IS 'Web page sources for RAG knowledge base';
COMMENT ON COLUMN web_sources.id IS 'Unique identifier (ws_xxxxxxxxxxxx format)';
COMMENT ON COLUMN web_sources.user_id IS 'Owner user UUID';
COMMENT ON COLUMN web_sources.url IS 'Source URL';
COMMENT ON COLUMN web_sources.display_name IS 'Display name (defaults to page title)';
COMMENT ON COLUMN web_sources.domain IS 'Domain extracted from URL';
COMMENT ON COLUMN web_sources.extractor IS 'Content extractor used (trafilatura, beautifulsoup)';
COMMENT ON COLUMN web_sources.status IS 'Processing status (pending, fetching, extracting, chunking, embedding, ready, error)';
COMMENT ON COLUMN web_sources.extracted_text IS 'Extracted plain text content';
COMMENT ON COLUMN web_sources.extracted_links IS 'JSON array of extracted links';
COMMENT ON COLUMN web_sources.extracted_images IS 'JSON array of extracted images';
COMMENT ON COLUMN web_sources.content_hash IS 'SHA256 hash of content for change detection';
COMMENT ON COLUMN web_sources.metadata IS 'Page metadata (title, description, author, etc.)';
COMMENT ON COLUMN web_sources.chunk_count IS 'Number of chunks created in vector index';
COMMENT ON COLUMN web_sources.tags IS 'User-defined tags array';
