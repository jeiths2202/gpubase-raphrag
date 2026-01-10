-- ============================================================================
-- Artifacts Table Schema
-- Stores extractable artifacts (code, long text) from agent chat messages
-- ============================================================================

-- ============================================
-- artifacts: Stores artifact content and metadata
-- ============================================
CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,

    -- Content
    artifact_type VARCHAR(50) NOT NULL,  -- code, text, markdown, html, json, diff, log
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    language VARCHAR(50),  -- python, javascript, typescript, etc.

    -- Metrics
    line_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,

    -- Version control
    version INTEGER DEFAULT 1,
    parent_artifact_id UUID REFERENCES artifacts(id),
    is_active BOOLEAN DEFAULT TRUE,

    -- Extensible metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_artifact_type CHECK (
        artifact_type IN ('code', 'text', 'markdown', 'html', 'json', 'diff', 'log', 'image')
    )
);

COMMENT ON TABLE artifacts IS 'Stores extractable artifacts (code, long text, etc.) from agent messages';
COMMENT ON COLUMN artifacts.artifact_type IS 'Type: code, text, markdown, html, json, diff, log, image';
COMMENT ON COLUMN artifacts.language IS 'Programming language for code artifacts (python, javascript, etc.)';
COMMENT ON COLUMN artifacts.version IS 'Incremental version number (starts at 1)';
COMMENT ON COLUMN artifacts.parent_artifact_id IS 'Links to previous version for version chain';
COMMENT ON COLUMN artifacts.is_active IS 'Only one version per artifact chain should be active';

-- ============================================
-- Indexes for performance
-- ============================================

-- Primary lookup indexes
CREATE INDEX IF NOT EXISTS idx_artifacts_conversation_id
    ON artifacts(conversation_id);

CREATE INDEX IF NOT EXISTS idx_artifacts_message_id
    ON artifacts(message_id)
    WHERE message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_artifacts_user_id
    ON artifacts(user_id);

-- Active artifacts per conversation (most common query)
CREATE INDEX IF NOT EXISTS idx_artifacts_conversation_active
    ON artifacts(conversation_id, is_active, created_at DESC)
    WHERE is_active = TRUE;

-- Type-based filtering
CREATE INDEX IF NOT EXISTS idx_artifacts_type
    ON artifacts(artifact_type);

-- Version chain lookup
CREATE INDEX IF NOT EXISTS idx_artifacts_parent
    ON artifacts(parent_artifact_id)
    WHERE parent_artifact_id IS NOT NULL;

-- ============================================
-- Triggers for automatic updates
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_artifact_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_artifacts_updated_at ON artifacts;
CREATE TRIGGER tr_artifacts_updated_at
    BEFORE UPDATE ON artifacts
    FOR EACH ROW EXECUTE FUNCTION update_artifact_updated_at();

-- ============================================
-- Helper functions
-- ============================================

-- Get active artifacts for a conversation
CREATE OR REPLACE FUNCTION get_conversation_artifacts(conv_id UUID)
RETURNS TABLE (
    id UUID,
    artifact_type VARCHAR(50),
    title VARCHAR(500),
    language VARCHAR(50),
    line_count INTEGER,
    char_count INTEGER,
    version INTEGER,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.artifact_type,
        a.title,
        a.language,
        a.line_count,
        a.char_count,
        a.version,
        a.created_at
    FROM artifacts a
    WHERE a.conversation_id = conv_id
      AND a.is_active = TRUE
    ORDER BY a.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- Get artifact with full content
CREATE OR REPLACE FUNCTION get_artifact_content(artifact_id UUID)
RETURNS TABLE (
    id UUID,
    artifact_type VARCHAR(50),
    title VARCHAR(500),
    content TEXT,
    language VARCHAR(50),
    line_count INTEGER,
    char_count INTEGER,
    version INTEGER,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.artifact_type,
        a.title,
        a.content,
        a.language,
        a.line_count,
        a.char_count,
        a.version,
        a.metadata,
        a.created_at,
        a.updated_at
    FROM artifacts a
    WHERE a.id = artifact_id;
END;
$$ LANGUAGE plpgsql;

-- Get version history for an artifact chain
CREATE OR REPLACE FUNCTION get_artifact_versions(artifact_id UUID)
RETURNS TABLE (
    id UUID,
    version INTEGER,
    title VARCHAR(500),
    content_preview VARCHAR(200),
    line_count INTEGER,
    char_count INTEGER,
    is_active BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    root_id UUID;
BEGIN
    -- Find the root of the version chain
    SELECT COALESCE(
        (SELECT a.parent_artifact_id FROM artifacts a WHERE a.id = artifact_id AND a.parent_artifact_id IS NOT NULL),
        artifact_id
    ) INTO root_id;

    RETURN QUERY
    WITH RECURSIVE version_chain AS (
        -- Start with root
        SELECT a.id, a.version, a.title, a.content, a.line_count, a.char_count, a.is_active, a.created_at, a.parent_artifact_id
        FROM artifacts a
        WHERE a.id = root_id OR a.parent_artifact_id = root_id

        UNION ALL

        -- Follow children
        SELECT a.id, a.version, a.title, a.content, a.line_count, a.char_count, a.is_active, a.created_at, a.parent_artifact_id
        FROM artifacts a
        JOIN version_chain vc ON a.parent_artifact_id = vc.id
    )
    SELECT
        vc.id,
        vc.version,
        vc.title,
        LEFT(vc.content, 200)::VARCHAR(200) as content_preview,
        vc.line_count,
        vc.char_count,
        vc.is_active,
        vc.created_at
    FROM version_chain vc
    ORDER BY vc.version DESC;
END;
$$ LANGUAGE plpgsql;

-- Create new version of an artifact
CREATE OR REPLACE FUNCTION create_artifact_version(
    p_artifact_id UUID,
    p_new_content TEXT,
    p_new_title VARCHAR(500) DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_current RECORD;
    v_new_id UUID;
BEGIN
    -- Get current artifact
    SELECT * INTO v_current
    FROM artifacts
    WHERE id = p_artifact_id AND is_active = TRUE;

    IF v_current IS NULL THEN
        RAISE EXCEPTION 'Artifact % not found or not active', p_artifact_id;
    END IF;

    -- Deactivate current version
    UPDATE artifacts SET is_active = FALSE WHERE id = p_artifact_id;

    -- Create new version
    INSERT INTO artifacts (
        message_id, conversation_id, user_id,
        artifact_type, title, content, language,
        line_count, char_count, version,
        parent_artifact_id, is_active, metadata
    )
    VALUES (
        v_current.message_id, v_current.conversation_id, v_current.user_id,
        v_current.artifact_type,
        COALESCE(p_new_title, v_current.title),
        p_new_content,
        v_current.language,
        (SELECT COUNT(*)::INTEGER FROM regexp_split_to_table(p_new_content, E'\n')),
        LENGTH(p_new_content),
        v_current.version + 1,
        p_artifact_id,
        TRUE,
        v_current.metadata
    )
    RETURNING id INTO v_new_id;

    RETURN v_new_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Row-Level Security (RLS) Policies
-- ============================================

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;

-- Select: User can see their own artifacts
CREATE POLICY artifacts_select_own ON artifacts
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true));

-- Insert: User can create their own artifacts
CREATE POLICY artifacts_insert_own ON artifacts
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id', true));

-- Update: User can update their own artifacts
CREATE POLICY artifacts_update_own ON artifacts
    FOR UPDATE
    USING (user_id = current_setting('app.current_user_id', true));

-- Delete: User can delete their own artifacts
CREATE POLICY artifacts_delete_own ON artifacts
    FOR DELETE
    USING (user_id = current_setting('app.current_user_id', true));

-- Admin: Full access
CREATE POLICY artifacts_admin_all ON artifacts
    FOR ALL
    USING (current_setting('app.current_user_role', true) IN ('admin', 'super_admin'));
