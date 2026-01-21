# Claude Code Insights

Analytics and replay tool for Claude Code sessions. Imports Claude Code logs into SQLite for exploration and provides a web UI for session replay.

## Features

- **Log Processing**: Automatically imports Claude Code session logs (JSONL format)
- **Session Replay**: Step through conversations message by message
- **Tool Call Tracking**: See which tools were used (Bash, Read, Edit, etc.)
- **Full-Text Search**: Search across all prompts and sessions
- **Plan Viewer**: Browse implementation plans
- **Datasette Integration**: SQL exploration with Datasette

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-username/claude-insights.git
cd claude-insights

# Configure environment (optional)
cp .env.example .env
# Edit .env to set CLAUDE_LOGS_PATH if different from ~/.claude

# Start services
docker compose up -d

# Access the UIs
# Replay UI: http://localhost:8002
# Datasette: http://localhost:8001
```

## Architecture

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

## Services

| Service | Port | Description |
|---------|------|-------------|
| processor | - | Watches log files and imports to SQLite |
| replay-ui | 8002 | Flask app for session replay and search |
| datasette | 8001 | SQL exploration interface |

## Configuration

Environment variables (via `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_LOGS_PATH` | `~/.claude` | Path to Claude Code logs |
| `WATCH_INTERVAL` | `30` | Seconds between log scans |
| `DATASETTE_PORT` | `8001` | Datasette port |
| `UI_PORT` | `8002` | Replay UI port |

## Data Imported

- **Sessions**: Individual Claude Code conversations
- **Messages**: User and assistant messages with content
- **Tool Calls**: All tool invocations (Bash, Read, Edit, etc.)
- **Prompt History**: Historical prompts from `history.jsonl`
- **Plans**: Implementation plans from the plans directory
- **Todos**: Session todos and task lists

## Replay Features

- **Timeline Navigation**: Click any message in the sidebar
- **Keyboard Shortcuts**: `←`/`→` for prev/next, `Space` for play/pause
- **Auto-Play**: Adjustable playback speed
- **Syntax Highlighting**: Automatic for code blocks
- **Tool Visualization**: Shows tool calls with parameters

## Datasette Queries

Pre-defined queries at http://localhost:8001:

| Query | Description |
|-------|-------------|
| `recent_sessions` | Last 20 sessions |
| `tool_usage_stats` | Tool usage frequency |
| `sessions_by_tag` | Sessions grouped by tags |
| `daily_activity` | Daily activity overview |
| `search_messages` | Full-text search |

## Development

```bash
# Rebuild after code changes
docker compose build --no-cache

# View logs
docker compose logs -f processor

# Stop services
docker compose down

# Reset database
rm data/sessions.db && docker compose restart processor
```

## License

MIT
