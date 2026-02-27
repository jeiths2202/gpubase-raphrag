-- Migration: Create prompt management tables
-- Version: 002
-- Created: 2026-01-31
-- Feature: System Prompting Admin UI

-- ============================================================================
-- prompt_configs: Active prompt configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS prompt_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identification
    prompt_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'en',

    -- Classification
    category VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Content
    content TEXT NOT NULL,

    -- Protection
    is_readonly BOOLEAN DEFAULT FALSE,

    -- Source tracking
    source_file VARCHAR(255),

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by UUID,

    -- Constraints
    CONSTRAINT unique_prompt_language UNIQUE (prompt_id, language)
);

-- Indexes for prompt_configs
CREATE INDEX IF NOT EXISTS idx_prompt_configs_category ON prompt_configs(category);
CREATE INDEX IF NOT EXISTS idx_prompt_configs_prompt_id ON prompt_configs(prompt_id);
CREATE INDEX IF NOT EXISTS idx_prompt_configs_updated_at ON prompt_configs(updated_at DESC);

-- ============================================================================
-- prompt_history: Version history for prompts
-- ============================================================================
CREATE TABLE IF NOT EXISTS prompt_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Reference
    prompt_id VARCHAR(100) NOT NULL,
    language VARCHAR(10) DEFAULT 'en',
    version_number INTEGER NOT NULL,

    -- Snapshot
    content TEXT NOT NULL,

    -- Audit
    change_reason TEXT,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changed_by UUID,

    -- Constraints
    CONSTRAINT unique_prompt_version UNIQUE (prompt_id, language, version_number)
);

-- Indexes for prompt_history
CREATE INDEX IF NOT EXISTS idx_prompt_history_lookup ON prompt_history(prompt_id, language);
CREATE INDEX IF NOT EXISTS idx_prompt_history_changed_at ON prompt_history(changed_at DESC);

-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE prompt_configs IS 'Active prompt configurations for AI agents';
COMMENT ON TABLE prompt_history IS 'Version history for prompt changes';

COMMENT ON COLUMN prompt_configs.prompt_id IS 'Unique identifier e.g., rag_agent, code_agent';
COMMENT ON COLUMN prompt_configs.category IS 'Category: agent, middleware, system, persona, domain';
COMMENT ON COLUMN prompt_configs.is_readonly IS 'If TRUE, prompt cannot be modified (e.g., master_constraint)';
COMMENT ON COLUMN prompt_configs.source_file IS 'Original file path for sync tracking';
