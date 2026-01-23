# Claude Insights Server

Central server for team-wide Claude Code session analytics.

→ **Full documentation**: [Team Setup Guide](../docs/team-setup.md)

## Quick Reference

```bash
# Start
docker compose up -d

# Create user
docker compose exec api python -m app.cli create-user <username> --email <email>

# View logs
docker compose logs -f api
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8080 | REST API |
| Dashboard | 8081 | Team statistics |
| PostgreSQL | 5432 | Database |

## User Management

```bash
docker compose exec api python -m app.cli list-users
docker compose exec api python -m app.cli create-user <name> --email <email>
docker compose exec api python -m app.cli rotate-key <name>
docker compose exec api python -m app.cli delete-user <name>
```
