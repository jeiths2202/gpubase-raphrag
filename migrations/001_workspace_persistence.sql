-- ============================================================================
-- Migration 001: Persistent AI Workspace System
-- ============================================================================
-- Purpose: Implement enterprise-grade state persistence for multi-menu AI workspace
-- Author: Enterprise KMS Team
-- Date: 2025-12-28
-- ============================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. CONVERSATIONS & MESSAGES (RAG Chat History)
-- ============================================================================

-- Conversations: Top-level chat sessions
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Conversation',

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP,

    -- Conversation settings
    model_name TEXT DEFAULT 'nemotron-nano-9b',
    temperature FLOAT DEFAULT 0.7,
    max_tokens INT DEFAULT 2048,

    -- Status tracking
    is_archived BOOLEAN DEFAULT FALSE,
    is_pinned BOOLEAN DEFAULT FALSE,
    message_count INT DEFAULT 0,

    -- Future: Conversation branching support
    parent_conversation_id UUID,
    fork_point_message_id UUID,

    CONSTRAINT fk_parent_conversation
        FOREIGN KEY (parent_conversation_id)
        REFERENCES conversations(id)
        ON DELETE SET NULL
);

-- Messages: Individual chat messages within conversations
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL,

    -- Message content
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- Token tracking for cost management
    token_count INT,
    prompt_tokens INT,
    completion_tokens INT,

    -- RAG context tracking
    context_documents JSONB, -- [{doc_id, title, relevance_score, chunks_used}]
    retrieval_strategy TEXT, -- 'vector' | 'graph' | 'hybrid' | 'code'

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Future: Regenerate & version tracking
    version INT DEFAULT 1,
    parent_message_id UUID,
    is_regenerated BOOLEAN DEFAULT FALSE,
    regeneration_count INT DEFAULT 0,

    -- Metadata for debugging and audit
    metadata JSONB, -- {model_used, latency_ms, error_logs, user_feedback}

    CONSTRAINT fk_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES conversations(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_parent_message
        FOREIGN KEY (parent_message_id)
        REFERENCES messages(id)
        ON DELETE SET NULL
);

-- ============================================================================
-- 2. MENU STATE PERSISTENCE (Multi-Menu Workspace)
-- ============================================================================

-- Menu States: Persist UI and logic state for each menu type
CREATE TABLE IF NOT EXISTS menu_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,

    -- Menu identification
    menu_type TEXT NOT NULL CHECK (menu_type IN (
        'chat',
        'documents',
        'web_sources',
        'notes',
        'ai_content',
        'projects',
        'mindmap',
        'knowledge_graph',
        'knowledge_base'
    )),

    -- Flexible state storage (JSONB for schema-less persistence)
    -- Example for 'chat' menu:
    -- {
    --   "activeConversationId": "uuid",
    --   "selectedDocuments": ["doc_1", "doc_7"],
    --   "lastQuestion": "Explain GPU-based KMS",
    --   "scrollPosition": 420,
    --   "filterSettings": {"archived": false, "dateRange": "7days"},
    --   "viewMode": "list" | "grid"
    -- }
    state JSONB NOT NULL DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Ensure one state per user per menu type
    CONSTRAINT unique_user_menu_state
        UNIQUE (user_id, menu_type)
);

-- ============================================================================
-- 3. GRAPH STATE PERSISTENCE (Mindmap & Knowledge Graph)
-- ============================================================================

-- Graph States: Persist visual graph structures and node positions
CREATE TABLE IF NOT EXISTS graph_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,

    -- Graph identification
    graph_type TEXT NOT NULL CHECK (graph_type IN ('mindmap', 'knowledge_graph')),
    graph_name TEXT NOT NULL,

    -- Graph structure and layout
    -- Example structure:
    -- {
    --   "nodes": [
    --     {"id": "n1", "label": "GPU", "x": 100, "y": 200, "type": "concept"},
    --     {"id": "n2", "label": "RAG", "x": 300, "y": 200, "type": "concept"}
    --   ],
    --   "edges": [
    --     {"source": "n1", "target": "n2", "label": "enables"}
    --   ],
    --   "viewport": {"zoom": 1.0, "centerX": 200, "centerY": 200},
    --   "selectedNodes": ["n1"],
    --   "layout": "force-directed" | "hierarchical" | "manual"
    -- }
    state JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    node_count INT DEFAULT 0,
    edge_count INT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Allow multiple graphs per user per type
    CONSTRAINT unique_user_graph_name
        UNIQUE (user_id, graph_type, graph_name)
);

-- ============================================================================
-- 4. WORKSPACE SESSION TRACKING (Global User State)
-- ============================================================================

-- Workspace Sessions: Track user's overall workspace state
CREATE TABLE IF NOT EXISTS workspace_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE,

    -- Last active context
    last_active_menu TEXT DEFAULT 'chat',
    last_conversation_id UUID,

    -- Global preferences
    preferences JSONB DEFAULT '{}', -- {theme, language, notifications, layout}

    -- Session metadata
    last_login_at TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL DEFAULT NOW(),
    session_count INT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 5. DOCUMENT TRACKING (Documents Menu State)
-- ============================================================================

-- User Documents: Track user's document interactions and organization
CREATE TABLE IF NOT EXISTS user_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,

    -- Document reference (could link to existing documents table)
    document_id TEXT NOT NULL,
    document_title TEXT,
    document_type TEXT, -- 'pdf' | 'docx' | 'txt' | 'url'

    -- User-specific metadata
    is_favorite BOOLEAN DEFAULT FALSE,
    is_archived BOOLEAN DEFAULT FALSE,
    tags JSONB, -- ["machine-learning", "gpu", "research"]
    notes TEXT,

    -- Usage tracking
    last_accessed_at TIMESTAMP,
    access_count INT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_user_document
        UNIQUE (user_id, document_id)
);

-- ============================================================================
-- 6. INDEXES FOR PERFORMANCE
-- ============================================================================

-- Conversations indexes
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_conversations_archived ON conversations(user_id, is_archived);

-- Messages indexes
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at);

-- Menu states indexes
CREATE INDEX idx_menu_states_user_id ON menu_states(user_id);
CREATE INDEX idx_menu_states_menu_type ON menu_states(menu_type);
CREATE INDEX idx_menu_states_updated_at ON menu_states(updated_at DESC);

-- Graph states indexes
CREATE INDEX idx_graph_states_user_id ON graph_states(user_id);
CREATE INDEX idx_graph_states_graph_type ON graph_states(graph_type);
CREATE INDEX idx_graph_states_updated_at ON graph_states(updated_at DESC);

-- User documents indexes
CREATE INDEX idx_user_documents_user_id ON user_documents(user_id);
CREATE INDEX idx_user_documents_accessed ON user_documents(last_accessed_at DESC);
CREATE INDEX idx_user_documents_favorite ON user_documents(user_id, is_favorite);

-- Workspace sessions indexes
CREATE INDEX idx_workspace_sessions_activity ON workspace_sessions(last_activity_at DESC);

-- ============================================================================
-- 7. TRIGGERS FOR AUTOMATIC TIMESTAMP UPDATES
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to all relevant tables
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_menu_states_updated_at
    BEFORE UPDATE ON menu_states
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_graph_states_updated_at
    BEFORE UPDATE ON graph_states
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workspace_sessions_updated_at
    BEFORE UPDATE ON workspace_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_user_documents_updated_at
    BEFORE UPDATE ON user_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 8. SAMPLE DATA FOR TESTING (Optional - Comment out for production)
-- ============================================================================

-- Insert sample workspace session for admin user
-- INSERT INTO workspace_sessions (user_id, last_active_menu, preferences)
-- VALUES (
--     'admin-user-id',
--     'chat',
--     '{"theme": "dark", "language": "en", "notifications": true}'::jsonb
-- );

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
