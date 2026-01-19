-- ============================================================================
-- PostgreSQL External Connector Persistence Migration
--
-- Purpose: Persist external connector resources (connections, documents, chunks)
--          that were previously stored in-memory
--
-- Architecture:
-- - external_connections: OAuth tokens, connection status, sync metadata
-- - external_documents: Document metadata from external sources
-- - external_chunks: Chunked content for vector search (embeddings in Neo4j)
--
-- IMPORTANT: External documents are kept ISOLATED from internal documents
--            to maintain separation between admin-uploaded and user-connected data
-- ============================================================================

-- ============================================================================
-- TABLE: external_connections
-- Purpose: Store user connections to external resources (Notion, GitHub, etc.)
-- Previously: In-memory _connections dict in ExternalDocumentService
-- ============================================================================
CREATE TABLE IF NOT EXISTS external_connections (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'not_connected',
    auth_type VARCHAR(20) DEFAULT 'oauth2',

    -- Encrypted OAuth/API tokens (Fernet AES-128-CBC)
    access_token TEXT,
    refresh_token TEXT,
    api_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,

    -- Sync state
    sync_status VARCHAR(50) DEFAULT 'pending',
    sync_error TEXT,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    next_sync_at TIMESTAMP WITH TIME ZONE,

    -- Statistics
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,

    -- Resource-specific configuration (JSON)
    resource_config JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_external_conn_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT valid_resource_type CHECK (resource_type IN (
        'onenote', 'github', 'google_drive', 'notion', 'confluence'
    )),
    CONSTRAINT valid_conn_status CHECK (status IN (
        'not_connected', 'connecting', 'connected', 'syncing', 'error', 'expired'
    )),
    CONSTRAINT valid_auth_type CHECK (auth_type IN (
        'oauth2', 'api_token', 'personal_access_token'
    )),
    CONSTRAINT valid_sync_status CHECK (sync_status IN (
        'pending', 'in_progress', 'completed', 'failed'
    ))
);

-- Indexes for external_connections
CREATE INDEX IF NOT EXISTS idx_ext_conn_user_id ON external_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_ext_conn_resource_type ON external_connections(resource_type);
CREATE INDEX IF NOT EXISTS idx_ext_conn_status ON external_connections(status);
CREATE INDEX IF NOT EXISTS idx_ext_conn_updated_at ON external_connections(updated_at DESC);

-- Unique constraint: one connection per user per resource type
CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_conn_user_resource
    ON external_connections(user_id, resource_type);


-- ============================================================================
-- TABLE: external_documents
-- Purpose: Store document metadata from external sources
-- Previously: In-memory _documents dict in ExternalDocumentService
-- ============================================================================
CREATE TABLE IF NOT EXISTS external_documents (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID NOT NULL,
    connection_id VARCHAR(50) NOT NULL,

    -- Source identification
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(500),
    external_url TEXT,

    -- Document metadata
    title VARCHAR(500),
    path TEXT,
    mime_type VARCHAR(100),
    file_size INTEGER,

    -- Content (stored for reference, chunked content in external_chunks)
    sections JSONB DEFAULT '[]',
    text_content TEXT,
    content_hash VARCHAR(64),
    metadata JSONB DEFAULT '{}',

    -- Processing status
    status VARCHAR(50) DEFAULT 'discovered',
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,

    -- Sync tracking
    external_modified_at TIMESTAMP WITH TIME ZONE,
    last_synced_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ext_doc_connection FOREIGN KEY (connection_id)
        REFERENCES external_connections(id) ON DELETE CASCADE,
    CONSTRAINT valid_doc_source CHECK (source IN (
        'onenote', 'github', 'google_drive', 'notion', 'confluence'
    )),
    CONSTRAINT valid_doc_status CHECK (status IN (
        'discovered', 'fetching', 'parsing', 'chunking', 'embedding', 'ready', 'error', 'deleted'
    ))
);

-- Indexes for external_documents
CREATE INDEX IF NOT EXISTS idx_ext_doc_user_id ON external_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_ext_doc_connection_id ON external_documents(connection_id);
CREATE INDEX IF NOT EXISTS idx_ext_doc_status ON external_documents(status);
CREATE INDEX IF NOT EXISTS idx_ext_doc_source ON external_documents(source);
CREATE INDEX IF NOT EXISTS idx_ext_doc_updated_at ON external_documents(updated_at DESC);

-- Unique constraint: one document per external_id per connection
CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_doc_conn_external
    ON external_documents(connection_id, external_id);


-- ============================================================================
-- TABLE: external_chunks
-- Purpose: Store chunked content from external documents
-- Previously: In-memory UserVectorStore
-- Note: Actual embeddings are stored in Neo4j :ExternalChunk nodes
-- ============================================================================
CREATE TABLE IF NOT EXISTS external_chunks (
    id VARCHAR(50) PRIMARY KEY,
    user_id UUID NOT NULL,
    document_id VARCHAR(50) NOT NULL,
    connection_id VARCHAR(50) NOT NULL,

    -- Content
    content TEXT NOT NULL,
    chunk_index INTEGER DEFAULT 0,

    -- Source metadata
    source VARCHAR(50),
    source_name VARCHAR(500),
    source_url TEXT,
    section_title VARCHAR(500),
    page_number INTEGER,

    -- Content flags
    is_code BOOLEAN DEFAULT FALSE,
    is_table BOOLEAN DEFAULT FALSE,

    -- Embedding status (actual vectors in Neo4j)
    embedding_stored BOOLEAN DEFAULT FALSE,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_ext_chunk_document FOREIGN KEY (document_id)
        REFERENCES external_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_ext_chunk_connection FOREIGN KEY (connection_id)
        REFERENCES external_connections(id) ON DELETE CASCADE
);

-- Indexes for external_chunks
CREATE INDEX IF NOT EXISTS idx_ext_chunk_user_id ON external_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_ext_chunk_document_id ON external_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_ext_chunk_connection_id ON external_chunks(connection_id);
CREATE INDEX IF NOT EXISTS idx_ext_chunk_embedding ON external_chunks(embedding_stored);


-- ============================================================================
-- TRIGGER: Auto-update updated_at for external_connections
-- ============================================================================
DROP TRIGGER IF EXISTS external_connections_updated_at ON external_connections;
CREATE TRIGGER external_connections_updated_at
    BEFORE UPDATE ON external_connections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- TRIGGER: Auto-update updated_at for external_documents
-- ============================================================================
DROP TRIGGER IF EXISTS external_documents_updated_at ON external_documents;
CREATE TRIGGER external_documents_updated_at
    BEFORE UPDATE ON external_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- COMMENTS for documentation
-- ============================================================================
COMMENT ON TABLE external_connections IS
    'User connections to external resources (Notion, GitHub, Google Drive, OneNote, Confluence). Tokens are Fernet-encrypted.';

COMMENT ON TABLE external_documents IS
    'Document metadata from external sources. Content is chunked separately. Isolated from internal documents.';

COMMENT ON TABLE external_chunks IS
    'Chunked content from external documents. Embeddings are stored in Neo4j ExternalChunk nodes for vector search.';

COMMENT ON COLUMN external_connections.resource_config IS
    'Resource-specific config (workspace_id for Notion, cloud_id for Confluence, etc.)';

COMMENT ON COLUMN external_chunks.embedding_stored IS
    'True if embedding has been generated and stored in Neo4j ExternalChunk node';


-- ============================================================================
-- Success message
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Migration 020_external_connector_persistence completed successfully';
    RAISE NOTICE 'Tables created: external_connections, external_documents, external_chunks';
END $$;
