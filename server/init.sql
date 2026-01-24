-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL,
    email VARCHAR(255),
    share_level VARCHAR(20) DEFAULT 'metadata' CHECK (share_level IN ('none', 'metadata', 'full')),
    show_in_leaderboard BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    project_name VARCHAR(100),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (ended_at - started_at))::INTEGER) STORED,
    total_messages INTEGER DEFAULT 0,
    total_tokens_in INTEGER DEFAULT 0,
    total_tokens_out INTEGER DEFAULT 0,
    model VARCHAR(50),
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages table (only populated for share_level='full')
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    timestamp TIMESTAMPTZ,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    content_hash VARCHAR(64),
    UNIQUE(session_id, sequence)
);

-- Tool usage (always populated)
CREATE TABLE IF NOT EXISTS tool_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    call_count INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0
);

-- Session tags
CREATE TABLE IF NOT EXISTS session_tags (
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    auto_generated BOOLEAN DEFAULT true,
    PRIMARY KEY (session_id, tag)
);

-- Daily aggregated stats for fast dashboard queries
CREATE TABLE IF NOT EXISTS daily_stats (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    stat_date DATE NOT NULL,
    session_count INTEGER DEFAULT 0,
    total_tokens_in BIGINT DEFAULT 0,
    total_tokens_out BIGINT DEFAULT 0,
    total_duration_seconds INTEGER DEFAULT 0,
    top_tools JSONB,
    UNIQUE(user_id, stat_date)
);

-- Token usage (per-message/per-model tracking)
CREATE TABLE IF NOT EXISTS token_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    message_sequence INTEGER,
    timestamp TIMESTAMPTZ,
    model VARCHAR(100),
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0
);

-- Tool calls (detailed per-call records)
CREATE TABLE IF NOT EXISTS tool_calls (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    sequence INTEGER,
    tool_name VARCHAR(100) NOT NULL,
    tool_input TEXT,
    tool_output TEXT,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT true
);

-- Implementation plans
CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    title VARCHAR(500),
    content TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_usage_name ON tool_usage(tool_name);
CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(stat_date);
CREATE INDEX IF NOT EXISTS idx_daily_stats_user ON daily_stats(user_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_usage_model ON token_usage(model);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_message ON tool_calls(message_id);
CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id);

-- Full-text search on messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_messages_search ON messages USING GIN(search_vector);

-- Trigger to auto-update search_vector
CREATE OR REPLACE FUNCTION messages_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('german', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS messages_search_trigger ON messages;
CREATE TRIGGER messages_search_trigger
    BEFORE INSERT OR UPDATE ON messages
    FOR EACH ROW
    EXECUTE FUNCTION messages_search_vector_update();
