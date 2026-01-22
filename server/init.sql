-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL,
    email VARCHAR(255),
    share_level VARCHAR(20) DEFAULT 'metadata' CHECK (share_level IN ('none', 'metadata', 'full')),
    show_in_leaderboard BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- Sessions table
CREATE TABLE sessions (
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
CREATE TABLE messages (
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
CREATE TABLE tool_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    call_count INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0
);

-- Session tags
CREATE TABLE session_tags (
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    auto_generated BOOLEAN DEFAULT true,
    PRIMARY KEY (session_id, tag)
);

-- Daily aggregated stats for fast dashboard queries
CREATE TABLE daily_stats (
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

-- Indexes
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_started ON sessions(started_at);
CREATE INDEX idx_tool_usage_session ON tool_usage(session_id);
CREATE INDEX idx_tool_usage_name ON tool_usage(tool_name);
CREATE INDEX idx_daily_stats_date ON daily_stats(stat_date);
CREATE INDEX idx_daily_stats_user ON daily_stats(user_id);
