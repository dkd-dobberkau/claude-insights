# Team Setup

Central server for collecting Claude Code session insights from team members. Provides a shared dashboard, API for data collection, and Parquet exports for analytics.

## Quick Start

```bash
# Copy environment file
cp .env.example .env
# Edit .env with secure passwords (DB_PASSWORD, API_SECRET_KEY, FLASK_SECRET_KEY)

# Start services
docker compose up -d

# Create first user
docker compose exec api python -m app.cli create-user max --email max@example.com
```

## Access Services

| Service | URL | Description |
|---------|-----|-------------|
| Dashboard | http://localhost:8081 | Team statistics and visualizations |
| API | http://localhost:8080 | REST API for data collection |
| API Docs | http://localhost:8080/docs | OpenAPI documentation |

## User Management

```bash
# List users
docker compose exec api python -m app.cli list-users

# Create user (returns API key)
docker compose exec api python -m app.cli create-user <username> --email <email>

# Rotate API key
docker compose exec api python -m app.cli rotate-key <username>

# Delete user
docker compose exec api python -m app.cli delete-user <username>
```

## API Endpoints

### Authentication

All endpoints require an API key via header:
```
X-API-Key: <your-api-key>
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth required) |
| `/api/v1/sessions` | POST | Upload session |
| `/api/v1/sessions/batch` | POST | Upload multiple sessions |
| `/api/v1/me` | GET | Get own stats |
| `/api/v1/me/settings` | PUT | Update settings |
| `/api/v1/team/stats` | GET | Team statistics |
| `/api/v1/team/tools` | GET | Tool usage stats |
| `/api/v1/team/leaderboard` | GET | Top users |
| `/api/v1/team/trends` | GET | Usage trends |

## Client Configuration

Team members need to configure their local Claude Code to send data to the server.

### Option 1: Claude Insights Agent (Recommended)

Use [claude-insights-agent](https://github.com/dkd-dobberkau/claude-insights-agent) for automatic session sync:

```bash
# Install and configure the agent
# See https://github.com/dkd-dobberkau/claude-insights-agent for details
```

The agent runs locally and automatically uploads new sessions to the team server.

### Option 2: Direct API calls

```bash
# Upload a session manually
curl -X POST http://your-server:8080/api/v1/sessions \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d @session.json
```

## Backups

Parquet exports run daily at 2:00 AM and are stored in the `parquet_backup` volume.

```bash
# Access backups
docker compose exec exporter ls /backup/parquet

# Query with DuckDB
duckdb -c "SELECT * FROM read_parquet('/path/to/backup/**/*.parquet');"
```

## Configuration

Environment variables in `.env`:

| Variable | Description |
|----------|-------------|
| `DB_PASSWORD` | PostgreSQL password |
| `API_SECRET_KEY` | API JWT secret key |
| `FLASK_SECRET_KEY` | Dashboard session secret |

## Production Deployment

### Elestio (Recommended)

Deploy to [Elestio](https://elestio.com) with automatic HTTPS and managed infrastructure:

1. **Create Service**
   - Elestio Dashboard → "Deploy my source code"
   - Connect your GitHub/GitLab repository
   - Use repository root (no subdirectory needed)

2. **Configure Environment Variables**
   ```
   DB_PASSWORD=<generate-secure-password>
   API_SECRET_KEY=<openssl rand -hex 32>
   FLASK_SECRET_KEY=<openssl rand -hex 32>
   ```

3. **Access URLs** (after deployment)
   - API: `https://[your-app].elestio.app`
   - Dashboard: `https://[your-app].elestio.app:8443`

4. **Create Users** via Elestio Terminal:
   ```bash
   docker compose exec api python -m app.cli create-user max --email max@example.com
   ```

### Self-Hosted Production

For self-hosted production, consider:

1. **Reverse Proxy**: Put nginx/traefik in front for HTTPS
2. **Authentication**: Integrate with your SSO provider
3. **Backups**: Configure external backup storage
4. **Monitoring**: Add health check monitoring

## Troubleshooting

**API not responding?**
```bash
docker compose logs api
```

**Database connection issues?**
```bash
docker compose exec db psql -U postgres -c "SELECT 1"
```

**Reset everything?**
```bash
docker compose down -v
docker compose up -d
```
