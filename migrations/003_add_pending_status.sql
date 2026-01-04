-- Migration: Add 'pending' status to users table
-- Purpose: Support email verification workflow
-- Date: 2025-12-28

-- Drop existing constraint
ALTER TABLE users DROP CONSTRAINT IF EXISTS valid_status;

-- Add new constraint with 'pending' status
ALTER TABLE users ADD CONSTRAINT valid_status
    CHECK (status IN ('pending', 'active', 'inactive', 'suspended'));

-- Comment for documentation
COMMENT ON CONSTRAINT valid_status ON users IS 'Valid user status values: pending (email verification), active, inactive, suspended';
