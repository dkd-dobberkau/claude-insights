# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Insights is a self-hosted analytics and replay system for Claude Code sessions. It monitors Claude Code logs, imports session data into SQLite, and provides:
- **Replay UI** (Flask): Step-through session playback with syntax highlighting
- **Datasette**: SQL-based data exploration with predefined queries

## Commands

```bash
# Start all services
docker compose up -d

# Stop services
docker compose down

# View logs
docker compose logs processor    # Log processor output
docker compose logs replay-ui    # Flask UI logs
docker compose logs datasette    # Datasette logs

# Rebuild after code changes
docker compose build processor   # Rebuild processor
docker compose build replay-ui   # Rebuild UI
docker compose up -d             # Restart with new builds

# Check database
sqlite3 data/sessions.db ".tables"
sqlite3 data/sessions.db "SELECT COUNT(*) FROM sessions"
```

## Architecture

```
~/.claude/ ──► processor/process_logs.py ──► data/sessions.db
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              Datasette:8001   Replay UI:8002   API endpoints
```

**Three Docker services:**
1. `processor` - Watches logs, parses multiple formats (JSON, JSONL, Markdown), imports to SQLite
2. `datasette` - Read-only SQL interface with predefined queries
3. `replay-ui` - Flask app for interactive session playback

## Key Files

| File | Purpose |
|------|---------|
| `processor/process_logs.py` | Log parser/importer with `LogProcessor` class |
| `ui/app.py` | Flask routes and embedded HTML templates |
| `datasette/metadata.yml` | Predefined SQL queries and Datasette config |

## Database Schema

- `sessions` - Session metadata (project path, timestamps, token usage)
- `messages` - User/assistant messages with sequence numbers
- `tool_calls` - Tool invocations with parameters and results
- `file_changes` - Files modified during sessions
- `session_tags` - Auto-generated categorization
- `messages_fts` - Full-text search virtual table

## Extending

**Add custom tags** in `processor/process_logs.py` `_generate_tags` method:
```python
patterns = {
    'debugging': ['error', 'bug', 'fix'],
    'custom_tag': ['keyword1', 'keyword2'],
}
```

**Add log format support** by implementing `_normalize_*` methods in `LogProcessor`.

## Configuration

Environment variables in `.env` (copy from `.env.example`):
- `CLAUDE_LOGS_PATH` - Log directory (default: `~/.claude`)
- `WATCH_INTERVAL` - Polling interval in seconds (default: 30)
- `DATASETTE_PORT` - Datasette port (default: 8001)
- `UI_PORT` - Replay UI port (default: 8002)

## Code Patterns

- Python: snake_case, type hints, docstrings on key functions
- Database: Parameterized queries, transaction wrapping, MD5 change detection
- Frontend: Embedded HTML templates in Flask, dark theme, keyboard navigation
