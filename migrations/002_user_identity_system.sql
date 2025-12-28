-- ============================================================================
-- PostgreSQL User Identity System Migration
--
-- Purpose: Separate Authentication from Internal User Management
--
-- Design Principles:
-- 1. Authentication (Google/SSO) and Internal Identity are SEPARATED
-- 2. PostgreSQL is the SINGLE SOURCE OF TRUTH for user identity
-- 3. Workspace ownership is based on internal user_id, NOT provider IDs
-- 4. Multiple authentication methods can map to single internal user
-- ============================================================================

-- Drop tables if they exist (for clean re-run)
DROP TABLE IF EXISTS auth_identities CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================================================
-- TABLE: users (Internal User Registry)
-- Purpose: Single source of truth for ALL users in the system
-- Owner of: RAG workspaces, conversation histories, documents, notes
-- ============================================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User identification
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,

    -- Local authentication (NULL for SSO-only users)
    password_hash TEXT,  -- bcrypt/argon2 hash, NULL if using only SSO/OAuth

    -- Authorization
    role TEXT NOT NULL DEFAULT 'user',  -- admin / leader / senior / user / guest
    status TEXT NOT NULL DEFAULT 'active',  -- active / inactive / suspended

    -- Metadata
    department TEXT,
    language TEXT DEFAULT 'ko',  -- User's preferred language (ko/en/ja)

    -- Audit trail
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_role CHECK (role IN ('admin', 'leader', 'senior', 'user', 'guest')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'suspended')),
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);

-- Indexes for performance
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_created_at ON users(created_at DESC);

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- TABLE: auth_identities (External Authentication Mapping)
-- Purpose: Map external authentication providers to internal users
-- Design: One internal user can have MULTIPLE auth methods (Google + SSO + local)
-- ============================================================================
CREATE TABLE auth_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to internal user
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- External authentication provider
    provider TEXT NOT NULL,  -- 'google' / 'sso' / 'local'
    provider_user_id TEXT NOT NULL,  -- Google's sub / SSO user ID / email

    -- Provider metadata
    email TEXT,  -- Email from provider (may differ from users.email)
    provider_metadata JSONB,  -- Additional provider-specific data

    -- Audit trail
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP,

    -- Constraints
    CONSTRAINT valid_provider CHECK (provider IN ('google', 'sso', 'local', 'microsoft', 'github')),
    CONSTRAINT unique_provider_identity UNIQUE (provider, provider_user_id)
);

-- Indexes for performance
CREATE INDEX idx_auth_identities_user_id ON auth_identities(user_id);
CREATE INDEX idx_auth_identities_provider ON auth_identities(provider);
CREATE INDEX idx_auth_identities_email ON auth_identities(email);


-- ============================================================================
-- INITIAL DATA: System Admin Account
-- Purpose: Bootstrap admin user for system administration
--
-- SECURITY NOTE:
-- - Password MUST be changed at application startup via environment variable
-- - This is just a placeholder to ensure table structure is valid
-- - Actual admin creation happens via bootstrap logic
-- ============================================================================

-- NOTE: This placeholder will be REPLACED by bootstrap logic at startup
-- The application will check for admin existence and create with secure password
-- from ADMIN_INITIAL_PASSWORD environment variable

-- Placeholder comment only - actual admin creation is in application bootstrap


-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function: Get or create user from external authentication
CREATE OR REPLACE FUNCTION get_or_create_user_from_auth(
    p_provider TEXT,
    p_provider_user_id TEXT,
    p_email TEXT,
    p_display_name TEXT DEFAULT NULL,
    p_provider_metadata JSONB DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
    v_auth_id UUID;
BEGIN
    -- Step 1: Check if auth_identity exists
    SELECT user_id INTO v_user_id
    FROM auth_identities
    WHERE provider = p_provider AND provider_user_id = p_provider_user_id;

    -- Step 2: If exists, update last_used_at and return user_id
    IF v_user_id IS NOT NULL THEN
        UPDATE auth_identities
        SET last_used_at = NOW()
        WHERE provider = p_provider AND provider_user_id = p_provider_user_id;

        -- Update user's last_login_at
        UPDATE users
        SET last_login_at = NOW()
        WHERE id = v_user_id;

        RETURN v_user_id;
    END IF;

    -- Step 3: Create new user
    INSERT INTO users (email, display_name, role, status)
    VALUES (
        p_email,
        COALESCE(p_display_name, split_part(p_email, '@', 1)),
        'user',  -- Default role for new users
        'active'
    )
    RETURNING id INTO v_user_id;

    -- Step 4: Create auth_identity mapping
    INSERT INTO auth_identities (user_id, provider, provider_user_id, email, provider_metadata)
    VALUES (v_user_id, p_provider, p_provider_user_id, p_email, p_provider_metadata);

    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- AUDIT VIEWS (for monitoring and compliance)
-- ============================================================================

-- View: User authentication methods summary
CREATE OR REPLACE VIEW v_user_auth_methods AS
SELECT
    u.id AS user_id,
    u.email,
    u.display_name,
    u.role,
    u.status,
    ARRAY_AGG(DISTINCT ai.provider) AS auth_methods,
    COUNT(DISTINCT ai.provider) AS auth_method_count,
    u.created_at,
    u.last_login_at
FROM users u
LEFT JOIN auth_identities ai ON u.id = ai.user_id
GROUP BY u.id, u.email, u.display_name, u.role, u.status, u.created_at, u.last_login_at;

-- View: Recent authentication activity
CREATE OR REPLACE VIEW v_recent_auth_activity AS
SELECT
    u.id AS user_id,
    u.email,
    ai.provider,
    ai.last_used_at,
    u.last_login_at
FROM users u
JOIN auth_identities ai ON u.id = ai.user_id
WHERE ai.last_used_at IS NOT NULL
ORDER BY ai.last_used_at DESC
LIMIT 100;


-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE users IS 'Internal user registry - single source of truth for all users. Owner of workspaces, conversations, documents.';
COMMENT ON TABLE auth_identities IS 'External authentication provider mappings. Multiple auth methods can map to one internal user.';

COMMENT ON COLUMN users.id IS 'Internal UUID - used as workspace/document owner ID. NEVER expose provider IDs externally.';
COMMENT ON COLUMN users.email IS 'Primary email address - unique identifier for user account.';
COMMENT ON COLUMN users.password_hash IS 'bcrypt/argon2 password hash. NULL for SSO-only users.';
COMMENT ON COLUMN users.role IS 'Authorization level: admin (full access), leader (review+manage), senior (review), user (register), guest (read-only)';
COMMENT ON COLUMN users.status IS 'Account status: active (normal), inactive (disabled), suspended (temporary ban)';

COMMENT ON COLUMN auth_identities.provider IS 'Authentication provider: google, sso, local, microsoft, github';
COMMENT ON COLUMN auth_identities.provider_user_id IS 'External provider user ID (Google sub, SSO ID, etc.). Never used as workspace owner.';
COMMENT ON COLUMN auth_identities.email IS 'Email from provider (may differ from users.email for account linking)';

COMMENT ON FUNCTION get_or_create_user_from_auth IS 'Get existing user or create new user from external authentication. Returns internal user_id for JWT sub claim.';


-- ============================================================================
-- GRANTS (Security)
-- ============================================================================

-- Grant appropriate permissions to application user
-- GRANT SELECT, INSERT, UPDATE ON users TO kms_app_user;
-- GRANT SELECT, INSERT, UPDATE ON auth_identities TO kms_app_user;
-- GRANT USAGE ON SCHEMA public TO kms_app_user;

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

-- Verification query (run after migration)
-- SELECT
--     (SELECT COUNT(*) FROM users) AS total_users,
--     (SELECT COUNT(*) FROM auth_identities) AS total_auth_identities,
--     (SELECT COUNT(*) FROM users WHERE role = 'admin') AS admin_users;
