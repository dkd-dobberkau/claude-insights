# Claude Insights

Analytics and replay system for Claude Code sessions. Understand how you and your team use Claude Code.

## Choose Your Setup

| | **Solo** | **Team** |
|---|----------|----------|
| **For** | Individual developers | Teams sharing insights |
| **Database** | SQLite | PostgreSQL |
| **Features** | Session replay, search, Datasette | Team dashboard, API, Parquet export |
| **Setup** | Single `docker compose up` | Server + client deployment |

→ [Solo Setup](docs/solo-setup.md) — Get started in 2 minutes
→ [Team Setup](docs/team-setup.md) — Central server for your team

## What You Get

- **Session Replay**: Step through conversations with syntax highlighting
- **Tool Analytics**: See which tools (Bash, Edit, Read) are used most
- **Full-Text Search**: Find any prompt or response
- **Usage Trends**: Track token usage over time

## Documentation

- [Solo Setup](docs/solo-setup.md) — Local installation for individuals
- [Team Setup](docs/team-setup.md) — Server deployment for teams
- [Architecture](docs/architecture.md) — Technical details and diagrams
- [Development](docs/development.md) — Contributing guide

## License

MIT
