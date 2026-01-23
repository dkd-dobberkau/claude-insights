# Development

Guide for contributing to Claude Insights.

## Project Structure

```
claude-insights/
├── processor/              # Log processing service
│   └── process_logs.py     # LogProcessor class
├── ui/                     # Solo Replay UI
│   └── app.py              # Flask routes and templates
├── datasette/              # Datasette configuration
│   └── metadata.yml        # Predefined queries
├── server/                 # Team server
│   ├── api/                # FastAPI application
│   ├── dashboard/          # Team dashboard
│   └── exporter/           # Parquet export service
├── data/                   # SQLite database (gitignored)
└── docs/                   # Documentation
```

## Local Development

### Solo Components

```bash
# Start services in development mode
docker compose up

# Or run components directly:

# Processor
cd processor
python process_logs.py

# UI
cd ui
flask run --port 8002

# Datasette
datasette data/sessions.db --metadata datasette/metadata.yml
```

### Team Components

```bash
cd server

# Start all services
docker compose up

# Or run API directly:
cd api
uvicorn app.main:app --reload --port 8080
```

## Code Patterns

### Python Style

- snake_case for functions and variables
- Type hints on function signatures
- Docstrings on public functions

```python
def process_session(session_id: str, data: dict) -> bool:
    """Process a single session and store in database.

    Args:
        session_id: Unique session identifier
        data: Raw session data from log file

    Returns:
        True if successfully processed
    """
    ...
```

### Database Access

- Use parameterized queries (never string concatenation)
- Wrap related operations in transactions
- Use MD5 hashing for change detection

```python
# Good
cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))

# Bad
cursor.execute(f"SELECT * FROM sessions WHERE id = '{session_id}'")
```

### Error Handling

- Log errors with context
- Fail gracefully, don't crash the service
- Return meaningful error messages

## Extending

### Add Custom Session Tags

Edit `processor/process_logs.py`, method `_generate_tags`:

```python
patterns = {
    'debugging': ['error', 'bug', 'fix'],
    'refactoring': ['refactor', 'cleanup', 'reorganize'],
    'your_tag': ['keyword1', 'keyword2'],
}
```

### Add New Log Format

Implement a `_normalize_*` method in `LogProcessor`:

```python
def _normalize_newformat(self, data: dict) -> dict:
    """Normalize new format to standard schema."""
    return {
        'session_id': data.get('id'),
        'messages': self._extract_messages(data),
        ...
    }
```

### Add Datasette Query

Edit `datasette/metadata.yml`:

```yaml
queries:
  your_query:
    sql: |
      SELECT * FROM sessions
      WHERE ...
    title: "Your Query Title"
    description: "What this query shows"
```

### Add API Endpoint (Team)

Edit `server/api/app/routes.py`:

```python
@router.get("/api/v1/your-endpoint")
async def your_endpoint(user: User = Depends(get_current_user)):
    ...
```

## Testing

```bash
# Run processor tests
cd processor
python -m pytest

# Run API tests
cd server/api
python -m pytest
```

## Building

```bash
# Rebuild all containers
docker compose build --no-cache

# Rebuild specific service
docker compose build processor
```
