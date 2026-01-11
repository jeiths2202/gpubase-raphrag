-- Migration: 010_api_keys.sql
-- Description: API Keys for public/anonymous RAG access
-- Created: 2025-01-11

-- API Keys table for public access without login
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Key identification
    name VARCHAR(255) NOT NULL,
    description TEXT,
    key_prefix VARCHAR(8) NOT NULL,  -- First 8 chars for display (e.g., "kms_abc1...")
    key_hash VARCHAR(64) NOT NULL,   -- SHA256 hash of full key

    -- Owner (optional - can be system-generated)
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Access control
    allowed_endpoints TEXT[] DEFAULT ARRAY['query', 'agents'],  -- Allowed endpoint prefixes
    allowed_agent_types TEXT[] DEFAULT ARRAY['auto', 'rag'],    -- Allowed agent types

    -- Rate limiting
    rate_limit_per_minute INT DEFAULT 10,
    rate_limit_per_hour INT DEFAULT 100,
    rate_limit_per_day INT DEFAULT 1000,

    -- Usage tracking
    total_requests BIGINT DEFAULT 0,
    total_tokens_used BIGINT DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,

    -- Lifecycle
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_key_hash UNIQUE (key_hash)
);

-- Index for fast key lookup
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_api_keys_owner ON api_keys(owner_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

-- API Key usage log for analytics
CREATE TABLE IF NOT EXISTS api_key_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,

    -- Request details
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    agent_type VARCHAR(50),

    -- Performance metrics
    tokens_used INT DEFAULT 0,
    response_time_ms INT,

    -- Client info
    client_ip VARCHAR(45),
    user_agent TEXT,

    -- Status
    status_code INT,
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for usage analytics
CREATE INDEX IF NOT EXISTS idx_api_key_usage_key ON api_key_usage_log(api_key_id);
CREATE INDEX IF NOT EXISTS idx_api_key_usage_time ON api_key_usage_log(created_at);

-- Rate limiting cache table (for distributed rate limiting)
CREATE TABLE IF NOT EXISTS api_key_rate_limits (
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    window_type VARCHAR(10) NOT NULL,  -- 'minute', 'hour', 'day'
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    request_count INT DEFAULT 1,

    PRIMARY KEY (api_key_id, window_type, window_start)
);

-- Auto-cleanup old rate limit entries (keep last 24 hours)
CREATE INDEX IF NOT EXISTS idx_rate_limits_cleanup ON api_key_rate_limits(window_start);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_api_keys_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_api_keys_updated_at ON api_keys;
CREATE TRIGGER trigger_api_keys_updated_at
    BEFORE UPDATE ON api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_api_keys_updated_at();

-- Comments
COMMENT ON TABLE api_keys IS 'API keys for public/anonymous RAG access without login';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 8 characters of the key for display purposes';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA256 hash of the full API key';
COMMENT ON COLUMN api_keys.allowed_endpoints IS 'Array of allowed endpoint prefixes (e.g., query, agents)';
COMMENT ON COLUMN api_keys.allowed_agent_types IS 'Array of allowed agent types (e.g., auto, rag, ims)';
