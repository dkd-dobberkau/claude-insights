# Solo Setup

Local analytics and replay for individual developers. Get insights into your Claude Code sessions without any server infrastructure.

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

## Features

### Session Replay

Step through your Claude Code conversations message by message:

- **Timeline Navigation**: Click any message in the sidebar
- **Keyboard Shortcuts**: `←`/`→` for prev/next, `Space` for play/pause
- **Auto-Play**: Adjustable playback speed
- **Syntax Highlighting**: Automatic for code blocks
- **Tool Visualization**: Shows tool calls with parameters

### Datasette Queries

Pre-defined queries at http://localhost:8001:

| Query | Description |
|-------|-------------|
| `recent_sessions` | Last 20 sessions |
| `tool_usage_stats` | Tool usage frequency |
| `sessions_by_tag` | Sessions grouped by tags |
| `daily_activity` | Daily activity overview |
| `search_messages` | Full-text search |

### Data Imported

- **Sessions**: Individual Claude Code conversations
- **Messages**: User and assistant messages with content
- **Tool Calls**: All tool invocations (Bash, Read, Edit, etc.)
- **Prompt History**: Historical prompts from `history.jsonl`
- **Plans**: Implementation plans from the plans directory
- **Todos**: Session todos and task lists

## Commands

```bash
# View logs
docker compose logs -f processor    # Log processor output
docker compose logs -f replay-ui    # Flask UI logs
docker compose logs -f datasette    # Datasette logs

# Rebuild after code changes
docker compose build --no-cache

# Stop services
docker compose down

# Reset database
rm data/sessions.db && docker compose restart processor
```

## Troubleshooting

**No sessions appearing?**
- Check that `CLAUDE_LOGS_PATH` points to your Claude Code logs directory
- View processor logs: `docker compose logs processor`
- Ensure the logs directory is mounted correctly in docker-compose.yml

**Database locked errors?**
- Stop all services: `docker compose down`
- Restart: `docker compose up -d`

**Port conflicts?**
- Change ports in `.env` file
- Rebuild: `docker compose up -d`
