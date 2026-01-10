-- ============================================================================
-- IMS Issues Schema Update - Action Log Support
-- Version: 007
-- Description: Add action_no and action_log_text columns to ims_issues table
-- ============================================================================

-- Add action_no column (Action Log count/number)
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS action_no VARCHAR(50);

-- Add action_log_text column (Full text of all action logs combined)
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS action_log_text TEXT;

-- Update full-text search index to include action_log_text
DROP INDEX IF EXISTS idx_ims_issues_fulltext;
CREATE INDEX idx_ims_issues_fulltext ON ims_issues USING GIN(
    to_tsvector('english',
        COALESCE(title, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(issue_details, '') || ' ' ||
        COALESCE(action_log_text, '') || ' ' ||
        COALESCE(ims_id, '')
    )
);

-- Comments
COMMENT ON COLUMN ims_issues.action_no IS 'Action Log number/count from IMS';
COMMENT ON COLUMN ims_issues.action_log_text IS 'Full text content of all action logs combined (max 10KB)';

-- Verification
SELECT 'Migration 007 complete: Added action_no and action_log_text to ims_issues' AS status;
