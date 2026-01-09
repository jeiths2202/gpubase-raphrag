-- ============================================================================
-- IMS Issues Schema Update
-- Version: 006
-- Description: Add missing columns to ims_issues table
-- ============================================================================

-- Add missing columns to ims_issues table
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS issue_details TEXT;
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS category VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS product VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS version VARCHAR(100);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS module VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS customer VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS issued_date TIMESTAMPTZ;
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS status_raw VARCHAR(100);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS priority_raw VARCHAR(100);

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_ims_issues_category ON ims_issues(category);
CREATE INDEX IF NOT EXISTS idx_ims_issues_product ON ims_issues(product);
CREATE INDEX IF NOT EXISTS idx_ims_issues_customer ON ims_issues(customer);
CREATE INDEX IF NOT EXISTS idx_ims_issues_issued_date ON ims_issues(issued_date DESC);

-- Update full-text search index to include issue_details
DROP INDEX IF EXISTS idx_ims_issues_fulltext;
CREATE INDEX idx_ims_issues_fulltext ON ims_issues USING GIN(
    to_tsvector('english',
        COALESCE(title, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(issue_details, '') || ' ' ||
        COALESCE(ims_id, '')
    )
);

-- Comments
COMMENT ON COLUMN ims_issues.issue_details IS 'Detailed issue content from IMS';
COMMENT ON COLUMN ims_issues.category IS 'Issue category (e.g., Bug, Feature, Question)';
COMMENT ON COLUMN ims_issues.product IS 'Product name (e.g., OpenFrame, ProSort)';
COMMENT ON COLUMN ims_issues.version IS 'Product version';
COMMENT ON COLUMN ims_issues.module IS 'Module within the product';
COMMENT ON COLUMN ims_issues.customer IS 'Customer name';
COMMENT ON COLUMN ims_issues.issued_date IS 'Original issue creation date in IMS';
COMMENT ON COLUMN ims_issues.status_raw IS 'Raw status value from IMS (e.g., Closed_P, Rejected)';
COMMENT ON COLUMN ims_issues.priority_raw IS 'Raw priority value from IMS (e.g., Normal, High, Very high)';

-- Verification
SELECT 'Migration 006 complete: Added columns to ims_issues' AS status;
