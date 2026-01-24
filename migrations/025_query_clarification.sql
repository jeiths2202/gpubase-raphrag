-- Migration 025: Query Clarification System
-- Handles ambiguous term detection and user preference learning
-- for improved search accuracy

-- ============================================================================
-- Table: ambiguous_terms
-- ============================================================================
-- Stores admin-defined ambiguous terms that need clarification before search
-- Example: "MFS" can mean JEUS MFS, Tmax MFS, or OpenFrame MFS

CREATE TABLE IF NOT EXISTS ambiguous_terms (
    id SERIAL PRIMARY KEY,
    term VARCHAR(100) NOT NULL,
    term_normalized VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    possible_entities JSONB NOT NULL,
    match_patterns TEXT[] DEFAULT '{}',
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint on normalized term
CREATE UNIQUE INDEX IF NOT EXISTS idx_at_term_normalized
    ON ambiguous_terms(term_normalized);

-- Index for active terms lookup
CREATE INDEX IF NOT EXISTS idx_at_active
    ON ambiguous_terms(is_active, priority DESC);

-- Index for category filtering
CREATE INDEX IF NOT EXISTS idx_at_category
    ON ambiguous_terms(category) WHERE category IS NOT NULL;

-- Full-text search index for term matching
CREATE INDEX IF NOT EXISTS idx_at_term_fts
    ON ambiguous_terms USING GIN(to_tsvector('simple', term));

-- Comments
COMMENT ON TABLE ambiguous_terms IS 'Admin-defined ambiguous terms requiring clarification';
COMMENT ON COLUMN ambiguous_terms.term IS 'Original term text (case preserved)';
COMMENT ON COLUMN ambiguous_terms.term_normalized IS 'Normalized form for matching (lowercase, trimmed)';
COMMENT ON COLUMN ambiguous_terms.category IS 'Category for grouping (e.g., product_feature, technology)';
COMMENT ON COLUMN ambiguous_terms.possible_entities IS 'JSON array of possible meanings: [{id, name, description, keywords}]';
COMMENT ON COLUMN ambiguous_terms.match_patterns IS 'Additional patterns to match this term (regex or keywords)';
COMMENT ON COLUMN ambiguous_terms.priority IS 'Priority for conflict resolution (higher = more important)';
COMMENT ON COLUMN ambiguous_terms.is_active IS 'Whether this term is active for matching';


-- ============================================================================
-- Table: user_term_preferences
-- ============================================================================
-- Stores user-specific term preferences learned from clarification dialogs
-- Enables "remember my choice" functionality

CREATE TABLE IF NOT EXISTS user_term_preferences (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    term_normalized VARCHAR(100) NOT NULL,
    selected_entity_id VARCHAR(100) NOT NULL,
    selected_entity_name VARCHAR(200) NOT NULL,
    is_permanent BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint on user + term combination
CREATE UNIQUE INDEX IF NOT EXISTS idx_utp_user_term
    ON user_term_preferences(user_id, term_normalized);

-- Index for user lookup
CREATE INDEX IF NOT EXISTS idx_utp_user_id
    ON user_term_preferences(user_id);

-- Index for frequently used preferences
CREATE INDEX IF NOT EXISTS idx_utp_usage
    ON user_term_preferences(usage_count DESC);

-- Comments
COMMENT ON TABLE user_term_preferences IS 'User-specific term clarification preferences';
COMMENT ON COLUMN user_term_preferences.user_id IS 'User who made the selection';
COMMENT ON COLUMN user_term_preferences.term_normalized IS 'Normalized term that was clarified';
COMMENT ON COLUMN user_term_preferences.selected_entity_id IS 'ID of the selected entity from possible_entities';
COMMENT ON COLUMN user_term_preferences.selected_entity_name IS 'Name of the selected entity (denormalized for display)';
COMMENT ON COLUMN user_term_preferences.is_permanent IS 'Whether to always apply this preference (remember choice)';
COMMENT ON COLUMN user_term_preferences.usage_count IS 'Number of times this preference was applied';


-- ============================================================================
-- Function: Update timestamp trigger
-- ============================================================================
CREATE OR REPLACE FUNCTION update_clarification_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for automatic timestamp update
DROP TRIGGER IF EXISTS trg_at_updated_at ON ambiguous_terms;
CREATE TRIGGER trg_at_updated_at
    BEFORE UPDATE ON ambiguous_terms
    FOR EACH ROW EXECUTE FUNCTION update_clarification_timestamp();

DROP TRIGGER IF EXISTS trg_utp_updated_at ON user_term_preferences;
CREATE TRIGGER trg_utp_updated_at
    BEFORE UPDATE ON user_term_preferences
    FOR EACH ROW EXECUTE FUNCTION update_clarification_timestamp();


-- ============================================================================
-- Initial test data
-- ============================================================================
-- Insert sample ambiguous terms for testing
INSERT INTO ambiguous_terms (term, term_normalized, category, possible_entities, match_patterns, priority)
VALUES
    ('MFS', 'mfs', 'product_feature', '[
        {"id": "jeus_mfs", "name": "JEUS MFS", "description": "JEUS Message File System - WAS message handling", "keywords": ["jeus", "was", "message", "websocket"]},
        {"id": "tmax_mfs", "name": "Tmax MFS", "description": "Tmax distributed file system", "keywords": ["tmax", "distributed", "file", "tp-monitor"]},
        {"id": "openframe_mfs", "name": "OpenFrame MFS", "description": "Mainframe file system emulation", "keywords": ["openframe", "mainframe", "cobol", "jcl"]}
    ]'::jsonb, ARRAY['MFS', 'mfs', 'M.F.S'], 100),

    ('WebAdmin', 'webadmin', 'product_component', '[
        {"id": "jeus_webadmin", "name": "JEUS WebAdmin", "description": "JEUS web-based administration console", "keywords": ["jeus", "admin", "console", "was"]},
        {"id": "tmax_webadmin", "name": "Tmax WebAdmin", "description": "Tmax web administration tool", "keywords": ["tmax", "admin", "tp-monitor"]},
        {"id": "tibero_webadmin", "name": "Tibero WebAdmin", "description": "Tibero database web admin", "keywords": ["tibero", "database", "sql"]}
    ]'::jsonb, ARRAY['WebAdmin', 'webadmin', 'web-admin', 'Web Admin'], 90),

    ('TP', 'tp', 'technology', '[
        {"id": "tmax_tp", "name": "Tmax TP Monitor", "description": "Tmax transaction processing monitor", "keywords": ["tmax", "transaction", "monitor", "tp-monitor"]},
        {"id": "tp_general", "name": "Transaction Processing", "description": "General transaction processing concepts", "keywords": ["transaction", "processing", "acid"]}
    ]'::jsonb, ARRAY['TP', 'tp', 'T/P', 'T.P'], 80),

    ('Manager', 'manager', 'product_component', '[
        {"id": "jeus_manager", "name": "JEUS Manager", "description": "JEUS domain manager (DAS)", "keywords": ["jeus", "das", "domain", "admin"]},
        {"id": "tmax_manager", "name": "Tmax Manager", "description": "Tmax system manager process", "keywords": ["tmax", "system", "process"]},
        {"id": "node_manager", "name": "Node Manager", "description": "Node management component", "keywords": ["node", "cluster", "management"]}
    ]'::jsonb, ARRAY['Manager', 'manager', 'MGR'], 70)
ON CONFLICT (term_normalized) DO NOTHING;
