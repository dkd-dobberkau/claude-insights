# Zentrale dkd Claude Insights Datenbank

Design-Dokument für eine team-weite Datenbank zur Sammlung von Claude Code Session-Insights.

## Entscheidungen

| Aspekt | Entscheidung |
|--------|--------------|
| Daten-Transfer | Push-Modell (Entwickler senden an Server) |
| Datenschutz | Konfigurierbar pro User (none/metadata/full) |
| Authentifizierung | API-Keys pro User |
| Datenbank | PostgreSQL + Parquet Backup |
| Deployment | Docker Compose |
| Client | Go (Single Binary) |
| Server | Python/FastAPI |

## Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                         dkd Entwickler                              │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│  Dev 1       │  Dev 2       │  Dev 3       │  ...                  │
│  ~/.claude/  │  ~/.claude/  │  ~/.claude/  │                       │
│      │       │      │       │      │       │                       │
│      ▼       │      ▼       │      ▼       │                       │
│  [Local      │  [Local      │  [Local      │                       │
│   Agent]     │   Agent]     │   Agent]     │                       │
└──────┬───────┴──────┬───────┴──────┬───────┴───────────────────────┘
       │              │              │
       │   HTTPS POST (API-Key Auth) │
       ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Zentraler Server (Docker Compose)                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │   API       │  │ PostgreSQL  │  │  Parquet    │                 │
│  │  (FastAPI)  │──│             │──│  Exporter   │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│         │                │                │                         │
│         ▼                ▼                ▼                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Dashboard  │  │  Datasette  │  │  /backup/   │                 │
│  │  (Team UI)  │  │  (SQL UI)   │  │  *.parquet  │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Komponenten:**

- **Local Agent (Go)**: Läuft bei jedem Entwickler, verarbeitet lokale Logs, sendet nach Konfiguration
- **API (FastAPI)**: Empfängt Daten, validiert API-Keys, schreibt in PostgreSQL
- **PostgreSQL**: Zentrale Datenbank mit User-Trennung
- **Parquet Exporter**: Nächtlicher Job der Snapshots als Parquet exportiert
- **Dashboard (Flask)**: Team-Übersicht und persönliche Statistiken
- **Datasette**: SQL-Zugriff für Power-User

## PostgreSQL Schema

```sql
-- Benutzer-Verwaltung
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL,
    email VARCHAR(255),
    share_level VARCHAR(20) DEFAULT 'metadata',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- Sessions (erweitert um user_id)
CREATE TABLE sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    project_path VARCHAR(500),
    project_name VARCHAR(100),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (ended_at - started_at))) STORED,
    total_messages INTEGER DEFAULT 0,
    total_tokens_in INTEGER DEFAULT 0,
    total_tokens_out INTEGER DEFAULT 0,
    model VARCHAR(50),
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages (nur bei share_level='full')
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

-- Tool-Nutzung (immer, da nicht sensitiv)
CREATE TABLE tool_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    call_count INTEGER DEFAULT 1,
    total_duration_ms INTEGER,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0
);

-- Tags
CREATE TABLE session_tags (
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    auto_generated BOOLEAN DEFAULT true,
    PRIMARY KEY (session_id, tag)
);

-- Tägliche Aggregationen für schnelle Dashboards
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
CREATE INDEX idx_tool_usage_name ON tool_usage(tool_name);
CREATE INDEX idx_daily_stats_date ON daily_stats(stat_date);
```

## API-Endpunkte

```
POST /api/v1/sessions          # Session(s) hochladen
POST /api/v1/sessions/batch    # Mehrere Sessions auf einmal
GET  /api/v1/health            # Health-Check

GET  /api/v1/me                # Eigene Stats & Einstellungen
PUT  /api/v1/me/settings       # Share-Level ändern

GET  /api/v1/team/stats        # Team-Übersicht
GET  /api/v1/team/leaderboard  # Top-Nutzer (opt-in)
GET  /api/v1/team/tools        # Meistgenutzte Tools im Team
GET  /api/v1/team/trends       # Nutzung über Zeit
```

### Request/Response Beispiel

```json
// POST /api/v1/sessions
// Header: X-API-Key: dkd_abc123...

// Request (share_level=metadata):
{
    "session_id": "abc-123-def",
    "project_name": "customer-portal",
    "started_at": "2026-01-22T10:30:00Z",
    "ended_at": "2026-01-22T11:45:00Z",
    "total_messages": 24,
    "total_tokens_in": 45230,
    "total_tokens_out": 12840,
    "model": "claude-sonnet-4-20250514",
    "tools": {
        "Read": {"count": 15, "success": 15},
        "Edit": {"count": 8, "success": 7, "errors": 1},
        "Bash": {"count": 3, "success": 3}
    },
    "tags": ["debugging", "typescript"]
}

// Response:
{
    "status": "ok",
    "session_id": "abc-123-def",
    "warnings": []
}
```

### Server-Struktur

```
server/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── models.py
│   ├── db.py
│   ├── routers/
│   │   ├── sessions.py
│   │   ├── me.py
│   │   └── team.py
│   └── services/
│       ├── ingest.py
│       ├── stats.py
│       └── parquet.py
├── requirements.txt
└── Dockerfile
```

## Go Client (Local Agent)

### Struktur

```
claude-insights-agent/
├── cmd/
│   └── agent/
│       └── main.go
├── internal/
│   ├── config/
│   │   └── config.go
│   ├── watcher/
│   │   └── watcher.go
│   ├── parser/
│   │   └── jsonl.go
│   ├── filter/
│   │   └── filter.go
│   └── client/
│       └── api.go
├── go.mod
└── go.sum
```

### Config

```yaml
# ~/.config/claude-insights/config.yaml
server:
  url: https://insights.dkd.internal
  api_key: dkd_sk_abc123...

sharing:
  level: metadata          # none | metadata | full
  exclude_projects:
    - "**/personal/**"
    - "**/secret-*"
  anonymize_paths: true

sync:
  interval: 300            # Sekunden
  retry_attempts: 3

logging:
  level: info
  file: ~/.local/log/claude-insights-agent.log
```

### Installation

```bash
# macOS
brew install dkd/tap/claude-insights-agent
# oder
curl -L https://insights.dkd.internal/install.sh | bash

# Einrichtung
claude-insights-agent init

# Status
claude-insights-agent status
```

## Parquet Export

### Verzeichnisstruktur

```
/backup/parquet/
├── year=2026/
│   └── month=01/
│       ├── sessions_2026-01-20.parquet
│       ├── sessions_2026-01-21.parquet
│       ├── tools_2026-01-20.parquet
│       └── tools_2026-01-21.parquet
└── _schema/
    ├── sessions.schema
    └── tools.schema
```

### Nutzung mit DuckDB

```sql
SELECT
    username,
    COUNT(*) as sessions,
    SUM(total_tokens_in + total_tokens_out) as total_tokens
FROM read_parquet('/backup/parquet/year=2026/month=01/sessions_*.parquet')
GROUP BY username
ORDER BY total_tokens DESC;
```

### Retention Policy

```yaml
backup:
  parquet_dir: /backup/parquet
  schedule: "0 2 * * *"
  retention:
    daily: 30
    monthly: 12
    yearly: unlimited
```

## Dashboard

### Team-Übersicht

```
┌─────────────────────────────────────────────────────────────────────┐
│  dkd Claude Insights                    [Meine Stats] [Team] [SQL] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Team-Übersicht (diese Woche)                                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │ 247          │ │ 12.4M        │ │ 89h          │ │ 18         │ │
│  │ Sessions     │ │ Tokens       │ │ Coding-Zeit  │ │ Entwickler │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │
│                                                                     │
│  Token-Verbrauch (30 Tage)              Top Tools                   │
│  ┌─────────────────────────────┐        ┌─────────────────────────┐ │
│  │  Chart                      │        │ Read          ████ 2.4k │ │
│  └─────────────────────────────┘        │ Edit          ███  1.8k │ │
│                                          │ Bash          ██   980  │ │
│                                          └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Persönliche Stats

- Eigene Session-Statistiken
- Vergleich mit Team-Durchschnitt
- Einstellungen (Share-Level, Leaderboard Opt-in, API-Key)

## Docker Compose (Server)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: insights-db
    environment:
      POSTGRES_DB: claude_insights
      POSTGRES_USER: insights
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    secrets:
      - db_password
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "insights"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  api:
    build:
      context: ./server
      dockerfile: Dockerfile
    container_name: insights-api
    environment:
      DATABASE_URL: postgresql://insights:${DB_PASSWORD}@postgres/claude_insights
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    container_name: insights-dashboard
    environment:
      DATABASE_URL: postgresql://insights:${DB_PASSWORD}@postgres/claude_insights
    ports:
      - "8081:8081"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  datasette:
    build:
      context: ./datasette
      dockerfile: Dockerfile
    container_name: insights-datasette
    ports:
      - "8082:8082"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  exporter:
    build:
      context: ./exporter
      dockerfile: Dockerfile
    container_name: insights-exporter
    environment:
      DATABASE_URL: postgresql://insights:${DB_PASSWORD}@postgres/claude_insights
      EXPORT_SCHEDULE: "0 2 * * *"
    volumes:
      - parquet_backup:/backup/parquet
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: insights-proxy
    ports:
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - api
      - dashboard
      - datasette
    restart: unless-stopped

volumes:
  postgres_data:
  parquet_backup:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## Projekt-Struktur (Server)

```
dkd-claude-insights-server/
├── docker-compose.yml
├── .env.example
├── init.sql
├── secrets/
├── server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── datasette/
│   ├── Dockerfile
│   └── metadata.yml
├── exporter/
│   ├── Dockerfile
│   └── export.py
└── nginx/
    ├── nginx.conf
    └── certs/
```

## Implementierungs-Reihenfolge

1. PostgreSQL Schema + API-Grundgerüst
2. Go Client (Minimal: config, watch, upload)
3. Dashboard (Team-Übersicht)
4. Parquet Export
5. Datasette Integration
6. Nginx + HTTPS
7. Installation-Script für Entwickler

## Datenschutz-Stufen

| Level | Was wird geteilt |
|-------|------------------|
| `none` | Nichts (Agent pausiert) |
| `metadata` | Session-Dauer, Token-Counts, Tool-Namen, Tags, Projektname |
| `full` | Alles inkl. Message-Inhalte |

## Repositories

```
github.com/dkd/
├── claude-insights-server/     # Server + Dashboard + Exporter
└── claude-insights-agent/      # Go Client für Entwickler
```
