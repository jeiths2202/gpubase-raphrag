-- ============================================================================
-- Migration 008: Add agent_type column to conversations
-- ============================================================================
-- Purpose: Enable per-agent-type workspace persistence
-- Author: Enterprise KMS Team
-- Date: 2026-01-10
-- ============================================================================

-- Add agent_type column to conversations table
-- Values: 'auto', 'rag', 'ims', 'vision', 'code', 'planner'
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS agent_type VARCHAR(20) DEFAULT 'auto';

-- Add constraint for valid agent types
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_agent_type_check'
    ) THEN
        ALTER TABLE conversations
        ADD CONSTRAINT conversations_agent_type_check
        CHECK (agent_type IN ('auto', 'rag', 'ims', 'vision', 'code', 'planner'));
    END IF;
END $$;

-- Create index for efficient filtering by user and agent type
CREATE INDEX IF NOT EXISTS idx_conversations_user_agent_type
    ON conversations(user_id, agent_type, updated_at DESC)
    WHERE is_deleted = FALSE;

-- Add comment for documentation
COMMENT ON COLUMN conversations.agent_type IS 'Agent type: auto, rag, ims, vision, code, planner';

-- ============================================================================
-- END OF MIGRATION
-- ============================================================================
