-- ============================================================================
-- IMS Issues Additional Columns Migration
-- Version: 006
-- Description: Add IMS-specific columns to ims_issues table
-- Columns: category, product, version, module, customer, issued_date
-- ============================================================================

-- Add new columns for IMS-specific data
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS category VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS product VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS version VARCHAR(100);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS module VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS customer VARCHAR(255);
ALTER TABLE ims_issues ADD COLUMN IF NOT EXISTS issued_date TIMESTAMPTZ;

-- Add indexes for commonly queried columns
CREATE INDEX IF NOT EXISTS idx_ims_issues_category ON ims_issues(category);
CREATE INDEX IF NOT EXISTS idx_ims_issues_product ON ims_issues(product);
CREATE INDEX IF NOT EXISTS idx_ims_issues_customer ON ims_issues(customer);
CREATE INDEX IF NOT EXISTS idx_ims_issues_issued_date ON ims_issues(issued_date);

-- Add comments for documentation
COMMENT ON COLUMN ims_issues.category IS 'Issue category (e.g., Technical Support)';
COMMENT ON COLUMN ims_issues.product IS 'Product name (e.g., OpenFrame Base)';
COMMENT ON COLUMN ims_issues.version IS 'Product version (e.g., 7.3)';
COMMENT ON COLUMN ims_issues.module IS 'Module name (e.g., General)';
COMMENT ON COLUMN ims_issues.customer IS 'Customer name';
COMMENT ON COLUMN ims_issues.issued_date IS 'Issue registration date in IMS';
