# dkd Claude Insights Server

Central server for collecting Claude Code session insights from team members.

## Quick Start

1. **Copy environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with secure passwords
   ```

2. **Start services:**
   ```bash
   docker compose up -d
   ```

3. **Create first user:**
   ```bash
   docker compose exec api python -m app.cli create-user max --email max@dkd.de
   ```

4. **Access services:**
   - Dashboard: http://localhost:8081
   - API: http://localhost:8080
   - API Docs: http://localhost:8080/docs

## User Management

```bash
# List users
docker compose exec api python -m app.cli list-users

# Create user
docker compose exec api python -m app.cli create-user <username> --email <email>

# Rotate API key
docker compose exec api python -m app.cli rotate-key <username>

# Delete user
docker compose exec api python -m app.cli delete-user <username>
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/sessions` | POST | Upload session |
| `/api/v1/sessions/batch` | POST | Upload multiple sessions |
| `/api/v1/me` | GET | Get own stats |
| `/api/v1/me/settings` | PUT | Update settings |
| `/api/v1/team/stats` | GET | Team statistics |
| `/api/v1/team/tools` | GET | Tool usage stats |
| `/api/v1/team/leaderboard` | GET | Top users |
| `/api/v1/team/trends` | GET | Usage trends |

## Backups

Parquet exports run daily at 2:00 AM and are stored in the `parquet_backup` volume.

Access backups:
```bash
docker compose exec exporter ls /backup/parquet
```

Query with DuckDB:
```sql
SELECT * FROM read_parquet('/backup/parquet/**/*.parquet');
```

## Architecture

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
