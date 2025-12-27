-- ============================================================================
-- Conversation History System Schema
-- ChatGPT-equivalent conversation management for enterprise RAG
-- ============================================================================

-- ============================================
-- conversations: Core conversation metadata
-- ============================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    project_id VARCHAR(100),
    session_id VARCHAR(100),
    title VARCHAR(500),

    -- Stats (updated via trigger)
    message_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,

    -- Status flags
    is_archived BOOLEAN DEFAULT FALSE,
    is_starred BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    deleted_by VARCHAR(100),

    -- RAG configuration
    strategy VARCHAR(50) DEFAULT 'auto',
    language VARCHAR(10) DEFAULT 'auto',

    -- Extensible metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE conversations IS 'Stores conversation metadata with soft-delete support';
COMMENT ON COLUMN conversations.strategy IS 'RAG strategy: auto, vector, graph, hybrid, code';
COMMENT ON COLUMN conversations.language IS 'Response language: auto, ko, ja, en';

-- ============================================
-- messages: Individual messages with branching support
-- ============================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,

    -- Parent message for fork/regenerate tree
    parent_message_id UUID REFERENCES messages(id),

    -- Core content
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- Token tracking
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,

    -- Model info
    model VARCHAR(100),

    -- RAG sources (for assistant messages)
    sources JSONB DEFAULT '[]',
    rag_context JSONB DEFAULT '{}',

    -- Feedback
    feedback_score INTEGER CHECK (feedback_score >= 1 AND feedback_score <= 5),
    feedback_text TEXT,

    -- Regeneration tracking
    is_regenerated BOOLEAN DEFAULT FALSE,
    regeneration_count INTEGER DEFAULT 0,
    original_message_id UUID REFERENCES messages(id),

    -- Branch tracking for fork support
    branch_root_id UUID REFERENCES messages(id),
    branch_depth INTEGER DEFAULT 0,
    is_active_branch BOOLEAN DEFAULT TRUE,

    -- Soft delete
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE messages IS 'Stores individual messages with branching for regenerate/fork';
COMMENT ON COLUMN messages.parent_message_id IS 'Links to parent message for conversation tree';
COMMENT ON COLUMN messages.is_active_branch IS 'TRUE for currently visible branch, FALSE for regenerated alternatives';
COMMENT ON COLUMN messages.branch_root_id IS 'Root message of this branch (for fork tracking)';

-- ============================================
-- conversation_summaries: Rolling summarization for context management
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,

    -- Summary content
    summary_text TEXT NOT NULL,
    summary_type VARCHAR(50) DEFAULT 'rolling' CHECK (summary_type IN ('rolling', 'checkpoint', 'final')),

    -- Coverage tracking
    covers_from_message_id UUID REFERENCES messages(id),
    covers_to_message_id UUID REFERENCES messages(id),
    message_count_covered INTEGER DEFAULT 0,

    -- Token metrics
    tokens_before_summary INTEGER DEFAULT 0,
    tokens_after_summary INTEGER DEFAULT 0,
    compression_ratio FLOAT,

    -- Quality metrics
    confidence_score FLOAT,
    key_topics JSONB DEFAULT '[]',
    key_entities JSONB DEFAULT '[]',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE conversation_summaries IS 'Stores rolling summaries for context window management';
COMMENT ON COLUMN conversation_summaries.summary_type IS 'rolling=auto-generated, checkpoint=user-triggered, final=conversation-end';
COMMENT ON COLUMN conversation_summaries.compression_ratio IS 'tokens_after / tokens_before';

-- ============================================
-- Indexes for performance
-- ============================================

-- Conversation indexes
CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON conversations(user_id);

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
    ON conversations(user_id, updated_at DESC)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_conversations_project
    ON conversations(project_id)
    WHERE project_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_session
    ON conversations(session_id)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_starred
    ON conversations(user_id, is_starred)
    WHERE is_starred = TRUE AND is_deleted = FALSE;

-- Message indexes
CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_messages_parent
    ON messages(parent_message_id)
    WHERE parent_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_messages_branch_root
    ON messages(branch_root_id)
    WHERE branch_root_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_messages_active_branch
    ON messages(conversation_id, is_active_branch, created_at)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_messages_original
    ON messages(original_message_id)
    WHERE original_message_id IS NOT NULL;

-- Full-text search on message content (multi-language support)
CREATE INDEX IF NOT EXISTS idx_messages_content_fts_english
    ON messages USING GIN(to_tsvector('english', content))
    WHERE is_deleted = FALSE;

-- Summary indexes
CREATE INDEX IF NOT EXISTS idx_summaries_conversation
    ON conversation_summaries(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_summaries_type
    ON conversation_summaries(conversation_id, summary_type);

-- ============================================
-- Triggers for automatic updates
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER tr_messages_updated_at
    BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Update conversation stats on message changes
CREATE OR REPLACE FUNCTION update_conversation_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE conversations SET
            message_count = message_count + 1,
            total_tokens = total_tokens + COALESCE(NEW.total_tokens, 0),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = NEW.conversation_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE conversations SET
            message_count = GREATEST(message_count - 1, 0),
            total_tokens = GREATEST(total_tokens - COALESCE(OLD.total_tokens, 0), 0),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = OLD.conversation_id;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' AND OLD.is_deleted = FALSE AND NEW.is_deleted = TRUE THEN
        -- Soft delete: decrement stats
        UPDATE conversations SET
            message_count = GREATEST(message_count - 1, 0),
            total_tokens = GREATEST(total_tokens - COALESCE(OLD.total_tokens, 0), 0),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = NEW.conversation_id;
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tr_messages_stats
    AFTER INSERT OR DELETE OR UPDATE OF is_deleted ON messages
    FOR EACH ROW EXECUTE FUNCTION update_conversation_stats();

-- ============================================
-- Row-Level Security (RLS) Policies
-- ============================================

-- Enable RLS on all tables
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;

-- Conversation policies: owner access only
CREATE POLICY conversations_select_own ON conversations
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true));

CREATE POLICY conversations_insert_own ON conversations
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id', true));

CREATE POLICY conversations_update_own ON conversations
    FOR UPDATE
    USING (user_id = current_setting('app.current_user_id', true));

CREATE POLICY conversations_delete_own ON conversations
    FOR DELETE
    USING (user_id = current_setting('app.current_user_id', true));

-- Admin bypass policy for conversations
CREATE POLICY conversations_admin_all ON conversations
    FOR ALL
    USING (current_setting('app.current_user_role', true) IN ('admin', 'super_admin'));

-- Message policies: inherit from conversation ownership
CREATE POLICY messages_select_via_conversation ON messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
            AND (
                c.user_id = current_setting('app.current_user_id', true)
                OR current_setting('app.current_user_role', true) IN ('admin', 'super_admin')
            )
        )
    );

CREATE POLICY messages_insert_via_conversation ON messages
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
            AND c.user_id = current_setting('app.current_user_id', true)
        )
    );

CREATE POLICY messages_update_via_conversation ON messages
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
            AND c.user_id = current_setting('app.current_user_id', true)
        )
    );

CREATE POLICY messages_delete_via_conversation ON messages
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
            AND (
                c.user_id = current_setting('app.current_user_id', true)
                OR current_setting('app.current_user_role', true) IN ('admin', 'super_admin')
            )
        )
    );

-- Summary policies: inherit from conversation ownership
CREATE POLICY summaries_select_via_conversation ON conversation_summaries
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = conversation_summaries.conversation_id
            AND (
                c.user_id = current_setting('app.current_user_id', true)
                OR current_setting('app.current_user_role', true) IN ('admin', 'super_admin')
            )
        )
    );

CREATE POLICY summaries_insert_via_conversation ON conversation_summaries
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = conversation_summaries.conversation_id
            AND c.user_id = current_setting('app.current_user_id', true)
        )
    );

-- ============================================
-- Helper functions
-- ============================================

-- Get active message chain for a conversation
CREATE OR REPLACE FUNCTION get_active_messages(conv_id UUID)
RETURNS TABLE (
    id UUID,
    role VARCHAR(20),
    content TEXT,
    total_tokens INTEGER,
    sources JSONB,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.role, m.content, m.total_tokens, m.sources, m.created_at
    FROM messages m
    WHERE m.conversation_id = conv_id
      AND m.is_deleted = FALSE
      AND m.is_active_branch = TRUE
    ORDER BY m.created_at;
END;
$$ LANGUAGE plpgsql;

-- Get context window messages (most recent fitting in token budget)
CREATE OR REPLACE FUNCTION get_context_window_messages(
    conv_id UUID,
    max_tokens INTEGER DEFAULT 4000
)
RETURNS TABLE (
    id UUID,
    role VARCHAR(20),
    content TEXT,
    total_tokens INTEGER,
    cumulative_tokens INTEGER
) AS $$
BEGIN
    RETURN QUERY
    WITH ordered_messages AS (
        SELECT
            m.id,
            m.role,
            m.content,
            m.total_tokens,
            SUM(m.total_tokens) OVER (ORDER BY m.created_at DESC) as running_total
        FROM messages m
        WHERE m.conversation_id = conv_id
          AND m.is_deleted = FALSE
          AND m.is_active_branch = TRUE
        ORDER BY m.created_at DESC
    )
    SELECT
        om.id,
        om.role,
        om.content,
        om.total_tokens,
        om.running_total::INTEGER as cumulative_tokens
    FROM ordered_messages om
    WHERE om.running_total <= max_tokens
    ORDER BY om.running_total DESC;  -- Reverse to chronological order
END;
$$ LANGUAGE plpgsql;

-- Count conversation tokens
CREATE OR REPLACE FUNCTION get_conversation_token_count(conv_id UUID)
RETURNS INTEGER AS $$
DECLARE
    token_count INTEGER;
BEGIN
    SELECT COALESCE(SUM(total_tokens), 0)
    INTO token_count
    FROM messages
    WHERE conversation_id = conv_id
      AND is_deleted = FALSE
      AND is_active_branch = TRUE;

    RETURN token_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Audit trigger for conversation operations
-- ============================================

CREATE TABLE IF NOT EXISTS conversation_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID,
    message_id UUID,
    user_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_conversation
    ON conversation_audit_log(conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_user
    ON conversation_audit_log(user_id, created_at DESC);

COMMENT ON TABLE conversation_audit_log IS 'Audit trail for conversation operations';

-- ============================================
-- Sample data for testing (optional)
-- ============================================

-- Uncomment to insert test data:
/*
INSERT INTO conversations (user_id, title, strategy, language) VALUES
    ('user_test_001', 'Test Conversation 1', 'auto', 'ko'),
    ('user_test_001', 'Test Conversation 2', 'hybrid', 'en');

INSERT INTO messages (conversation_id, role, content, total_tokens)
SELECT
    c.id,
    'user',
    'Hello, this is a test message.',
    10
FROM conversations c
WHERE c.title = 'Test Conversation 1'
LIMIT 1;
*/
