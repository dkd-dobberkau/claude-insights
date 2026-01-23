# Architecture

Claude Insights has two independent deployment options with different architectures.

## Solo Architecture

Local setup using SQLite for single-user analytics.

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Claude Code    │     │    Processor    │     │     SQLite      │
│  Log Files      │────▶│  (Python)       │────▶│    Database     │
│  ~/.claude/     │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                        ┌────────────────────────────────┼────────────────────────────────┐
                        │                                │                                │
                        ▼                                ▼                                ▼
               ┌─────────────────┐              ┌─────────────────┐              ┌─────────────────┐
               │   Replay UI     │              │    Datasette    │              │   Search/Plans  │
               │   Port 8002     │              │   Port 8001     │              │   Port 8002     │
               └─────────────────┘              └─────────────────┘              └─────────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Processor | Python | Watches logs, parses formats, imports to SQLite |
| Replay UI | Flask | Session playback with timeline navigation |
| Datasette | Datasette | SQL exploration with predefined queries |
| Database | SQLite | Local storage for sessions, messages, tool calls |

### Data Flow

1. Claude Code writes session logs to `~/.claude/`
2. Processor watches for new/changed files
3. Logs are parsed (JSONL, JSON, Markdown formats)
4. Data is normalized and inserted into SQLite
5. UIs query SQLite for display

## Team Architecture

Central server using PostgreSQL for team-wide analytics.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Clients   │────▶│  API :8080  │────▶│  PostgreSQL │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌─────────────┐             │
                    │  Dashboard  │◀────────────┤
                    │    :8081    │             │
                    └─────────────┘             │
                                               │
                    ┌─────────────┐             │
                    │  Exporter   │◀────────────┘
                    │  (Parquet)  │
                    └─────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| API | FastAPI | REST API for session upload and queries |
| Dashboard | Flask | Team statistics and visualizations |
| Exporter | Python | Daily Parquet backups for analytics |
| Database | PostgreSQL | Persistent storage with user management |

### Data Flow

1. Team members upload sessions via API
2. API validates and stores in PostgreSQL
3. Dashboard queries PostgreSQL for team stats
4. Exporter creates daily Parquet snapshots

## Database Schema

### Solo (SQLite)

```sql
sessions          -- Session metadata (project, timestamps, tokens)
messages          -- User/assistant messages with sequence numbers
tool_calls        -- Tool invocations with parameters and results
file_changes      -- Files modified during sessions
session_tags      -- Auto-generated categorization
messages_fts      -- Full-text search virtual table
```

### Team (PostgreSQL)

```sql
users             -- Team members with API keys
sessions          -- Session data with user foreign key
tool_usage        -- Aggregated tool statistics
daily_stats       -- Pre-computed daily metrics
```

## Key Design Decisions

### Why Two Separate Systems?

- **Solo**: Optimized for quick local setup, no network required
- **Team**: Optimized for data aggregation, user management, long-term storage

### Why SQLite for Solo?

- Zero configuration
- Single file database
- Works offline
- Sufficient for single-user workloads

### Why PostgreSQL for Team?

- Concurrent access from multiple users
- Better query performance at scale
- Built-in user management
- Production-ready replication/backup

### Why Parquet Exports?

- Efficient columnar storage for analytics
- Compatible with DuckDB, Pandas, Spark
- Compressed backups
- Easy to share/archive
