# Team Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the central server infrastructure for collecting Claude Code insights from all dkd team members.

**Architecture:** FastAPI server receives session data via authenticated API, stores in PostgreSQL with configurable privacy levels, exports daily Parquet backups, serves team dashboard via Flask.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL 16, SQLAlchemy, Pydantic, Flask, HTMX, PyArrow, Docker Compose

---

## Task 1: Project Structure & Docker Compose

**Files:**
- Create: `server/docker-compose.yml`
- Create: `server/.env.example`
- Create: `server/init.sql`
- Create: `server/secrets/.gitkeep`

**Step 1: Create server directory structure**

```bash
mkdir -p server/api server/dashboard server/exporter server/datasette server/nginx server/secrets
```

**Step 2: Create Docker Compose file**

Create `server/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: insights-db
    environment:
      POSTGRES_DB: claude_insights
      POSTGRES_USER: insights
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "insights"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  api:
    build:
      context: ./api
      dockerfile: Dockerfile
    container_name: insights-api
    environment:
      DATABASE_URL: postgresql://insights:${DB_PASSWORD}@postgres/claude_insights
      API_SECRET_KEY: ${API_SECRET_KEY}
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
      SECRET_KEY: ${FLASK_SECRET_KEY}
    ports:
      - "8081:8081"
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
    volumes:
      - parquet_backup:/backup/parquet
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
  parquet_backup:
```

**Step 3: Create environment example**

Create `server/.env.example`:

```bash
DB_PASSWORD=change_me_in_production
API_SECRET_KEY=change_me_random_string
FLASK_SECRET_KEY=change_me_another_random_string
```

**Step 4: Create PostgreSQL init script**

Create `server/init.sql`:

```sql
-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL,
    email VARCHAR(255),
    share_level VARCHAR(20) DEFAULT 'metadata' CHECK (share_level IN ('none', 'metadata', 'full')),
    show_in_leaderboard BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ
);

-- Sessions table
CREATE TABLE sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    project_name VARCHAR(100),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (ended_at - started_at))::INTEGER) STORED,
    total_messages INTEGER DEFAULT 0,
    total_tokens_in INTEGER DEFAULT 0,
    total_tokens_out INTEGER DEFAULT 0,
    model VARCHAR(50),
    imported_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages table (only populated for share_level='full')
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

-- Tool usage (always populated)
CREATE TABLE tool_usage (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    call_count INTEGER DEFAULT 1,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0
);

-- Session tags
CREATE TABLE session_tags (
    session_id VARCHAR(100) REFERENCES sessions(id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    auto_generated BOOLEAN DEFAULT true,
    PRIMARY KEY (session_id, tag)
);

-- Daily aggregated stats for fast dashboard queries
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
CREATE INDEX idx_tool_usage_session ON tool_usage(session_id);
CREATE INDEX idx_tool_usage_name ON tool_usage(tool_name);
CREATE INDEX idx_daily_stats_date ON daily_stats(stat_date);
CREATE INDEX idx_daily_stats_user ON daily_stats(user_id);
```

**Step 5: Create secrets placeholder**

```bash
touch server/secrets/.gitkeep
echo "*.txt" > server/secrets/.gitignore
```

**Step 6: Commit**

```bash
git add server/
git commit -m "feat: add server project structure with Docker Compose and PostgreSQL schema"
```

---

## Task 2: FastAPI - Project Setup & Models

**Files:**
- Create: `server/api/Dockerfile`
- Create: `server/api/requirements.txt`
- Create: `server/api/app/__init__.py`
- Create: `server/api/app/main.py`
- Create: `server/api/app/config.py`
- Create: `server/api/app/models.py`
- Create: `server/api/app/database.py`

**Step 1: Create Dockerfile**

Create `server/api/Dockerfile`:

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
RUN apt-get update && apt-get install -y libpq5 curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser app/ ./app/
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8080/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Step 2: Create requirements.txt**

Create `server/api/requirements.txt`:

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6
```

**Step 3: Create config**

Create `server/api/app/__init__.py`:

```python
```

Create `server/api/app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://insights:password@localhost/claude_insights"
    api_secret_key: str = "dev-secret-key"

    class Config:
        env_file = ".env"


settings = Settings()
```

**Step 4: Create Pydantic models**

Create `server/api/app/models.py`:

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolStats(BaseModel):
    count: int
    success: int = 0
    errors: int = 0


class SessionCreate(BaseModel):
    session_id: str
    project_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    total_messages: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    model: Optional[str] = None
    tools: dict[str, ToolStats] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    messages: Optional[list[dict]] = None  # Only for share_level=full


class SessionResponse(BaseModel):
    status: str
    session_id: str
    warnings: list[str] = Field(default_factory=list)


class UserSettings(BaseModel):
    share_level: str = "metadata"
    show_in_leaderboard: bool = True


class UserInfo(BaseModel):
    username: str
    email: Optional[str]
    share_level: str
    show_in_leaderboard: bool
    sessions_count: int
    total_tokens: int


class HealthResponse(BaseModel):
    status: str
    database: str
```

**Step 5: Create database module**

Create `server/api/app/database.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

**Step 6: Create main FastAPI app**

Create `server/api/app/main.py`:

```python
from fastapi import FastAPI
from app.models import HealthResponse

app = FastAPI(
    title="dkd Claude Insights API",
    description="Central API for collecting Claude Code session insights",
    version="1.0.0"
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", database="connected")
```

**Step 7: Commit**

```bash
git add server/api/
git commit -m "feat: add FastAPI project setup with models and database config"
```

---

## Task 3: FastAPI - Authentication

**Files:**
- Create: `server/api/app/auth.py`
- Modify: `server/api/app/main.py`

**Step 1: Create auth module**

Create `server/api/app/auth.py`:

```python
import hashlib
from typing import Optional
from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db


def hash_api_key(api_key: str) -> str:
    """Hash API key with SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def get_current_user(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Validate API key and return user info."""
    key_hash = hash_api_key(x_api_key)

    result = await db.execute(
        text("""
            SELECT id, username, share_level, show_in_leaderboard
            FROM users
            WHERE api_key_hash = :key_hash
        """),
        {"key_hash": key_hash}
    )
    user = result.fetchone()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Update last_seen
    await db.execute(
        text("UPDATE users SET last_seen_at = NOW() WHERE id = :id"),
        {"id": user.id}
    )
    await db.commit()

    return {
        "id": user.id,
        "username": user.username,
        "share_level": user.share_level,
        "show_in_leaderboard": user.show_in_leaderboard
    }


async def get_optional_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Optional[dict]:
    """Optional authentication for public endpoints."""
    if not x_api_key:
        return None
    return await get_current_user(x_api_key, db)
```

**Step 2: Commit**

```bash
git add server/api/app/auth.py
git commit -m "feat: add API key authentication"
```

---

## Task 4: FastAPI - Sessions Router

**Files:**
- Create: `server/api/app/routers/__init__.py`
- Create: `server/api/app/routers/sessions.py`
- Modify: `server/api/app/main.py`

**Step 1: Create sessions router**

Create `server/api/app/routers/__init__.py`:

```python
```

Create `server/api/app/routers/sessions.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import get_current_user
from app.models import SessionCreate, SessionResponse

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(
    session: SessionCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a new session."""
    warnings = []

    # Check if messages should be stored based on share_level
    store_messages = user["share_level"] == "full" and session.messages
    if session.messages and user["share_level"] != "full":
        warnings.append("Messages stripped due to share_level setting")

    try:
        # Insert session
        await db.execute(
            text("""
                INSERT INTO sessions
                (id, user_id, project_name, started_at, ended_at,
                 total_messages, total_tokens_in, total_tokens_out, model)
                VALUES (:id, :user_id, :project_name, :started_at, :ended_at,
                        :total_messages, :total_tokens_in, :total_tokens_out, :model)
                ON CONFLICT (id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    total_messages = EXCLUDED.total_messages,
                    total_tokens_in = EXCLUDED.total_tokens_in,
                    total_tokens_out = EXCLUDED.total_tokens_out
            """),
            {
                "id": session.session_id,
                "user_id": user["id"],
                "project_name": session.project_name,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "total_messages": session.total_messages,
                "total_tokens_in": session.total_tokens_in,
                "total_tokens_out": session.total_tokens_out,
                "model": session.model
            }
        )

        # Insert tool usage
        for tool_name, stats in session.tools.items():
            await db.execute(
                text("""
                    INSERT INTO tool_usage
                    (session_id, tool_name, call_count, success_count, error_count)
                    VALUES (:session_id, :tool_name, :count, :success, :errors)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "session_id": session.session_id,
                    "tool_name": tool_name,
                    "count": stats.count,
                    "success": stats.success,
                    "errors": stats.errors
                }
            )

        # Insert tags
        for tag in session.tags:
            await db.execute(
                text("""
                    INSERT INTO session_tags (session_id, tag, auto_generated)
                    VALUES (:session_id, :tag, true)
                    ON CONFLICT DO NOTHING
                """),
                {"session_id": session.session_id, "tag": tag}
            )

        # Insert messages if full sharing
        if store_messages:
            for msg in session.messages:
                await db.execute(
                    text("""
                        INSERT INTO messages
                        (session_id, sequence, timestamp, role, content)
                        VALUES (:session_id, :seq, :ts, :role, :content)
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "session_id": session.session_id,
                        "seq": msg.get("seq", 0),
                        "ts": msg.get("timestamp"),
                        "role": msg.get("role", "unknown"),
                        "content": msg.get("content", "")
                    }
                )

        await db.commit()

        return SessionResponse(
            status="ok",
            session_id=session.session_id,
            warnings=warnings
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=list[SessionResponse])
async def create_sessions_batch(
    sessions: list[SessionCreate],
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload multiple sessions at once."""
    results = []
    for session in sessions:
        try:
            result = await create_session(session, user, db)
            results.append(result)
        except HTTPException as e:
            results.append(SessionResponse(
                status="error",
                session_id=session.session_id,
                warnings=[str(e.detail)]
            ))
    return results
```

**Step 2: Update main.py to include router**

Modify `server/api/app/main.py`:

```python
from fastapi import FastAPI
from app.models import HealthResponse
from app.routers import sessions

app = FastAPI(
    title="dkd Claude Insights API",
    description="Central API for collecting Claude Code session insights",
    version="1.0.0"
)

app.include_router(sessions.router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", database="connected")
```

**Step 3: Commit**

```bash
git add server/api/app/
git commit -m "feat: add sessions router with create and batch endpoints"
```

---

## Task 5: FastAPI - User & Team Routers

**Files:**
- Create: `server/api/app/routers/me.py`
- Create: `server/api/app/routers/team.py`
- Modify: `server/api/app/main.py`

**Step 1: Create me router (personal stats)**

Create `server/api/app/routers/me.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import get_current_user
from app.models import UserInfo, UserSettings

router = APIRouter(prefix="/api/v1/me", tags=["me"])


@router.get("", response_model=UserInfo)
async def get_my_info(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user info and stats."""
    result = await db.execute(
        text("""
            SELECT
                u.username,
                u.email,
                u.share_level,
                u.show_in_leaderboard,
                COUNT(s.id) as sessions_count,
                COALESCE(SUM(s.total_tokens_in + s.total_tokens_out), 0) as total_tokens
            FROM users u
            LEFT JOIN sessions s ON s.user_id = u.id
            WHERE u.id = :user_id
            GROUP BY u.id
        """),
        {"user_id": user["id"]}
    )
    row = result.fetchone()

    return UserInfo(
        username=row.username,
        email=row.email,
        share_level=row.share_level,
        show_in_leaderboard=row.show_in_leaderboard,
        sessions_count=row.sessions_count,
        total_tokens=row.total_tokens
    )


@router.put("/settings", response_model=UserSettings)
async def update_settings(
    settings: UserSettings,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user settings."""
    await db.execute(
        text("""
            UPDATE users
            SET share_level = :share_level,
                show_in_leaderboard = :show_in_leaderboard
            WHERE id = :user_id
        """),
        {
            "share_level": settings.share_level,
            "show_in_leaderboard": settings.show_in_leaderboard,
            "user_id": user["id"]
        }
    )
    await db.commit()

    return settings
```

**Step 2: Create team router**

Create `server/api/app/routers/team.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import get_optional_user

router = APIRouter(prefix="/api/v1/team", tags=["team"])


@router.get("/stats")
async def get_team_stats(
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get aggregated team statistics."""
    result = await db.execute(
        text("""
            SELECT
                COUNT(DISTINCT s.id) as total_sessions,
                COUNT(DISTINCT s.user_id) as active_users,
                COALESCE(SUM(s.total_tokens_in), 0) as total_tokens_in,
                COALESCE(SUM(s.total_tokens_out), 0) as total_tokens_out,
                COALESCE(SUM(s.duration_seconds), 0) as total_duration
            FROM sessions s
            WHERE s.started_at >= NOW() - INTERVAL '1 day' * :days
        """),
        {"days": days}
    )
    row = result.fetchone()

    return {
        "period_days": days,
        "total_sessions": row.total_sessions,
        "active_users": row.active_users,
        "total_tokens_in": row.total_tokens_in,
        "total_tokens_out": row.total_tokens_out,
        "total_duration_seconds": row.total_duration
    }


@router.get("/tools")
async def get_team_tools(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Get most used tools across the team."""
    result = await db.execute(
        text("""
            SELECT
                t.tool_name,
                SUM(t.call_count) as total_calls,
                SUM(t.success_count) as total_success,
                SUM(t.error_count) as total_errors
            FROM tool_usage t
            JOIN sessions s ON t.session_id = s.id
            WHERE s.started_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY t.tool_name
            ORDER BY total_calls DESC
            LIMIT :limit
        """),
        {"days": days, "limit": limit}
    )

    return [
        {
            "tool_name": row.tool_name,
            "total_calls": row.total_calls,
            "success_rate": row.total_success / row.total_calls if row.total_calls > 0 else 0
        }
        for row in result.fetchall()
    ]


@router.get("/leaderboard")
async def get_leaderboard(
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Get top users by token usage (opt-in only)."""
    result = await db.execute(
        text("""
            SELECT
                u.username,
                COUNT(s.id) as session_count,
                COALESCE(SUM(s.total_tokens_in + s.total_tokens_out), 0) as total_tokens
            FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE u.show_in_leaderboard = true
              AND s.started_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY u.id
            ORDER BY total_tokens DESC
            LIMIT :limit
        """),
        {"days": days, "limit": limit}
    )

    return [
        {
            "rank": idx + 1,
            "username": row.username,
            "session_count": row.session_count,
            "total_tokens": row.total_tokens
        }
        for idx, row in enumerate(result.fetchall())
    ]


@router.get("/trends")
async def get_trends(
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Get daily token usage trends."""
    result = await db.execute(
        text("""
            SELECT
                DATE(s.started_at) as date,
                COUNT(s.id) as sessions,
                SUM(s.total_tokens_in + s.total_tokens_out) as tokens
            FROM sessions s
            WHERE s.started_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY DATE(s.started_at)
            ORDER BY date
        """),
        {"days": days}
    )

    return [
        {
            "date": row.date.isoformat(),
            "sessions": row.sessions,
            "tokens": row.tokens
        }
        for row in result.fetchall()
    ]
```

**Step 3: Update main.py**

Modify `server/api/app/main.py`:

```python
from fastapi import FastAPI
from app.models import HealthResponse
from app.routers import sessions, me, team

app = FastAPI(
    title="dkd Claude Insights API",
    description="Central API for collecting Claude Code session insights",
    version="1.0.0"
)

app.include_router(sessions.router)
app.include_router(me.router)
app.include_router(team.router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", database="connected")
```

**Step 4: Commit**

```bash
git add server/api/app/
git commit -m "feat: add me and team routers with stats endpoints"
```

---

## Task 6: Dashboard - Flask Setup

**Files:**
- Create: `server/dashboard/Dockerfile`
- Create: `server/dashboard/requirements.txt`
- Create: `server/dashboard/app.py`

**Step 1: Create Dockerfile**

Create `server/dashboard/Dockerfile`:

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8081/health || exit 1
CMD ["python", "app.py"]
```

**Step 2: Create requirements.txt**

Create `server/dashboard/requirements.txt`:

```
flask==3.0.0
psycopg2-binary==2.9.9
```

**Step 3: Create Flask app**

Create `server/dashboard/app.py`:

```python
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>dkd Claude Insights</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #1a1a2e;
            --bg-card: #16213e;
            --text: #eee;
            --text-dim: #888;
            --accent: #0f3460;
            --highlight: #e94560;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--accent);
        }
        h1 { font-size: 1.5rem; }
        nav a {
            color: var(--text-dim);
            text-decoration: none;
            margin-left: 1.5rem;
            transition: color 0.2s;
        }
        nav a:hover, nav a.active { color: var(--highlight); }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: var(--highlight);
        }
        .stat-label { color: var(--text-dim); font-size: 0.9rem; }
        .card {
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        .card h2 { margin-bottom: 1rem; font-size: 1.1rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--accent); }
        th { color: var(--text-dim); font-weight: normal; }
        .bar {
            height: 8px;
            background: var(--highlight);
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>dkd Claude Insights</h1>
            <nav>
                <a href="/" class="{{ 'active' if active == 'team' else '' }}">Team</a>
                <a href="/tools" class="{{ 'active' if active == 'tools' else '' }}">Tools</a>
            </nav>
        </header>
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

HOME_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-value">{{ stats.total_sessions }}</div>
        <div class="stat-label">Sessions (7 Tage)</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:,.0f}".format(stats.total_tokens / 1000000) }}M</div>
        <div class="stat-label">Tokens</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:.0f}".format(stats.total_duration / 3600) }}h</div>
        <div class="stat-label">Coding-Zeit</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ stats.active_users }}</div>
        <div class="stat-label">Aktive Entwickler</div>
    </div>
</div>

<div class="card">
    <h2>Leaderboard (diese Woche)</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Entwickler</th><th>Sessions</th><th>Tokens</th></tr>
        </thead>
        <tbody>
            {% for user in leaderboard %}
            <tr>
                <td>{{ user.rank }}</td>
                <td>{{ user.username }}</td>
                <td>{{ user.session_count }}</td>
                <td>{{ "{:,}".format(user.total_tokens) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""

TOOLS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <h2>Meistgenutzte Tools (7 Tage)</h2>
    <table>
        <thead>
            <tr><th>Tool</th><th>Aufrufe</th><th>Erfolgsrate</th><th></th></tr>
        </thead>
        <tbody>
            {% for tool in tools %}
            <tr>
                <td>{{ tool.tool_name }}</td>
                <td>{{ "{:,}".format(tool.total_calls) }}</td>
                <td>{{ "{:.0%}".format(tool.success_rate) }}</td>
                <td style="width: 200px;">
                    <div class="bar" style="width: {{ (tool.total_calls / max_calls * 100) | int }}%"></div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Team stats
            cur.execute("""
                SELECT
                    COUNT(DISTINCT id) as total_sessions,
                    COUNT(DISTINCT user_id) as active_users,
                    COALESCE(SUM(total_tokens_in + total_tokens_out), 0) as total_tokens,
                    COALESCE(SUM(duration_seconds), 0) as total_duration
                FROM sessions
                WHERE started_at >= NOW() - INTERVAL '7 days'
            """)
            stats = cur.fetchone()

            # Leaderboard
            cur.execute("""
                SELECT
                    u.username,
                    COUNT(s.id) as session_count,
                    COALESCE(SUM(s.total_tokens_in + s.total_tokens_out), 0) as total_tokens
                FROM users u
                JOIN sessions s ON s.user_id = u.id
                WHERE u.show_in_leaderboard = true
                  AND s.started_at >= NOW() - INTERVAL '7 days'
                GROUP BY u.id
                ORDER BY total_tokens DESC
                LIMIT 10
            """)
            leaderboard = [
                {"rank": i + 1, **row}
                for i, row in enumerate(cur.fetchall())
            ]

    return render_template_string(
        HOME_TEMPLATE,
        base=BASE_TEMPLATE,
        active="team",
        stats=stats,
        leaderboard=leaderboard
    )


@app.route("/tools")
def tools():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.tool_name,
                    SUM(t.call_count) as total_calls,
                    SUM(t.success_count)::float / NULLIF(SUM(t.call_count), 0) as success_rate
                FROM tool_usage t
                JOIN sessions s ON t.session_id = s.id
                WHERE s.started_at >= NOW() - INTERVAL '7 days'
                GROUP BY t.tool_name
                ORDER BY total_calls DESC
                LIMIT 20
            """)
            tools_data = cur.fetchall()
            max_calls = tools_data[0]["total_calls"] if tools_data else 1

    return render_template_string(
        TOOLS_TEMPLATE,
        base=BASE_TEMPLATE,
        active="tools",
        tools=tools_data,
        max_calls=max_calls
    )


if __name__ == "__main__":
    app.jinja_env.globals["base"] = BASE_TEMPLATE
    app.run(host="0.0.0.0", port=8081, debug=False)
```

**Step 4: Commit**

```bash
git add server/dashboard/
git commit -m "feat: add Flask dashboard with team stats and tools view"
```

---

## Task 7: Parquet Exporter

**Files:**
- Create: `server/exporter/Dockerfile`
- Create: `server/exporter/requirements.txt`
- Create: `server/exporter/export.py`

**Step 1: Create Dockerfile**

Create `server/exporter/Dockerfile`:

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim
RUN apt-get update && apt-get install -y libpq5 cron && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .
RUN mkdir -p /backup/parquet && chown appuser:appuser /backup/parquet
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
CMD ["python", "export.py"]
```

**Step 2: Create requirements.txt**

Create `server/exporter/requirements.txt`:

```
psycopg2-binary==2.9.9
pandas==2.1.4
pyarrow==15.0.0
schedule==1.2.1
```

**Step 3: Create export script**

Create `server/exporter/export.py`:

```python
import os
import logging
import schedule
import time
from datetime import date, timedelta
from pathlib import Path
import psycopg2
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backup/parquet"))
EXPORT_SCHEDULE = os.environ.get("EXPORT_SCHEDULE", "02:00")


def get_db():
    return psycopg2.connect(DATABASE_URL)


def export_daily_snapshot():
    """Export yesterday's data to Parquet files."""
    yesterday = date.today() - timedelta(days=1)
    output_dir = BACKUP_DIR / f"year={yesterday.year}" / f"month={yesterday.month:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting data for {yesterday}")

    try:
        with get_db() as conn:
            # Export sessions
            sessions_df = pd.read_sql("""
                SELECT
                    s.id as session_id,
                    u.username,
                    s.project_name,
                    s.started_at,
                    s.ended_at,
                    s.duration_seconds,
                    s.total_messages,
                    s.total_tokens_in,
                    s.total_tokens_out,
                    s.model
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE DATE(s.started_at) = %s
            """, conn, params=[yesterday])

            if not sessions_df.empty:
                sessions_path = output_dir / f"sessions_{yesterday.isoformat()}.parquet"
                pq.write_table(
                    pa.Table.from_pandas(sessions_df),
                    sessions_path,
                    compression="snappy"
                )
                logger.info(f"Exported {len(sessions_df)} sessions to {sessions_path}")

            # Export tool usage
            tools_df = pd.read_sql("""
                SELECT
                    t.session_id,
                    t.tool_name,
                    t.call_count,
                    t.success_count,
                    t.error_count
                FROM tool_usage t
                JOIN sessions s ON t.session_id = s.id
                WHERE DATE(s.started_at) = %s
            """, conn, params=[yesterday])

            if not tools_df.empty:
                tools_path = output_dir / f"tools_{yesterday.isoformat()}.parquet"
                pq.write_table(
                    pa.Table.from_pandas(tools_df),
                    tools_path,
                    compression="snappy"
                )
                logger.info(f"Exported {len(tools_df)} tool records to {tools_path}")

            # Update daily_stats aggregation
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO daily_stats (user_id, stat_date, session_count, total_tokens_in, total_tokens_out, total_duration_seconds, top_tools)
                    SELECT
                        s.user_id,
                        DATE(s.started_at),
                        COUNT(*),
                        SUM(s.total_tokens_in),
                        SUM(s.total_tokens_out),
                        SUM(s.duration_seconds),
                        (
                            SELECT jsonb_object_agg(tool_name, call_count)
                            FROM (
                                SELECT t.tool_name, SUM(t.call_count) as call_count
                                FROM tool_usage t
                                WHERE t.session_id IN (SELECT id FROM sessions WHERE user_id = s.user_id AND DATE(started_at) = DATE(s.started_at))
                                GROUP BY t.tool_name
                                ORDER BY call_count DESC
                                LIMIT 5
                            ) top
                        )
                    FROM sessions s
                    WHERE DATE(s.started_at) = %s
                    GROUP BY s.user_id, DATE(s.started_at)
                    ON CONFLICT (user_id, stat_date) DO UPDATE SET
                        session_count = EXCLUDED.session_count,
                        total_tokens_in = EXCLUDED.total_tokens_in,
                        total_tokens_out = EXCLUDED.total_tokens_out,
                        total_duration_seconds = EXCLUDED.total_duration_seconds,
                        top_tools = EXCLUDED.top_tools
                """, [yesterday])
                conn.commit()
                logger.info("Updated daily_stats aggregation")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise


def cleanup_old_files():
    """Remove Parquet files older than 30 days."""
    cutoff = date.today() - timedelta(days=30)
    for parquet_file in BACKUP_DIR.glob("**/*.parquet"):
        # Extract date from filename
        try:
            file_date = date.fromisoformat(parquet_file.stem.split("_")[-1])
            if file_date < cutoff:
                parquet_file.unlink()
                logger.info(f"Deleted old file: {parquet_file}")
        except (ValueError, IndexError):
            continue


def main():
    logger.info(f"Parquet exporter started, schedule: {EXPORT_SCHEDULE}")

    # Run export on startup if data exists
    export_daily_snapshot()

    # Schedule daily export
    schedule.every().day.at(EXPORT_SCHEDULE).do(export_daily_snapshot)
    schedule.every().day.at("03:00").do(cleanup_old_files)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
```

**Step 4: Commit**

```bash
git add server/exporter/
git commit -m "feat: add Parquet exporter with daily snapshots and cleanup"
```

---

## Task 8: Admin CLI for User Management

**Files:**
- Create: `server/api/app/cli.py`
- Modify: `server/api/Dockerfile`

**Step 1: Create CLI tool**

Create `server/api/app/cli.py`:

```python
#!/usr/bin/env python3
"""CLI tool for managing users and API keys."""
import argparse
import hashlib
import secrets
import sys
import psycopg2
from psycopg2.extras import RealDictCursor


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"dkd_sk_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    """Hash API key with SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_user(conn, username: str, email: str = None, share_level: str = "metadata"):
    """Create a new user and return their API key."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, api_key_hash, email, share_level)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (username, key_hash, email, share_level))
        user_id = cur.fetchone()["id"]
        conn.commit()

    print(f"Created user: {username} (ID: {user_id})")
    print(f"API Key: {api_key}")
    print("\nSave this API key - it cannot be retrieved later!")
    return api_key


def list_users(conn):
    """List all users."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                u.id, u.username, u.email, u.share_level,
                u.created_at, u.last_seen_at,
                COUNT(s.id) as sessions
            FROM users u
            LEFT JOIN sessions s ON s.user_id = u.id
            GROUP BY u.id
            ORDER BY u.username
        """)
        users = cur.fetchall()

    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Level':<10} {'Sessions':<10} {'Last Seen':<20}")
    print("-" * 95)
    for u in users:
        last_seen = u["last_seen_at"].strftime("%Y-%m-%d %H:%M") if u["last_seen_at"] else "never"
        print(f"{u['id']:<5} {u['username']:<20} {u['email'] or '-':<30} {u['share_level']:<10} {u['sessions']:<10} {last_seen:<20}")


def rotate_key(conn, username: str):
    """Generate a new API key for a user."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET api_key_hash = %s WHERE username = %s RETURNING id
        """, (key_hash, username))
        result = cur.fetchone()
        if not result:
            print(f"Error: User '{username}' not found")
            sys.exit(1)
        conn.commit()

    print(f"New API Key for {username}: {api_key}")
    print("\nSave this API key - it cannot be retrieved later!")


def delete_user(conn, username: str):
    """Delete a user and their data."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if not user:
            print(f"Error: User '{username}' not found")
            sys.exit(1)

        # Delete sessions (cascades to messages, tool_usage, tags)
        cur.execute("DELETE FROM sessions WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM daily_stats WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM users WHERE id = %s", (user["id"],))
        conn.commit()

    print(f"Deleted user: {username}")


def main():
    import os
    parser = argparse.ArgumentParser(description="Claude Insights User Management")
    parser.add_argument("--db", default=os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights"))

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-user
    create_parser = subparsers.add_parser("create-user", help="Create a new user")
    create_parser.add_argument("username")
    create_parser.add_argument("--email", "-e")
    create_parser.add_argument("--share-level", "-s", default="metadata", choices=["none", "metadata", "full"])

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    # rotate-key
    rotate_parser = subparsers.add_parser("rotate-key", help="Generate new API key for user")
    rotate_parser.add_argument("username")

    # delete-user
    delete_parser = subparsers.add_parser("delete-user", help="Delete a user")
    delete_parser.add_argument("username")

    args = parser.parse_args()

    conn = psycopg2.connect(args.db, cursor_factory=RealDictCursor)

    try:
        if args.command == "create-user":
            create_user(conn, args.username, args.email, args.share_level)
        elif args.command == "list-users":
            list_users(conn)
        elif args.command == "rotate-key":
            rotate_key(conn, args.username)
        elif args.command == "delete-user":
            delete_user(conn, args.username)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

**Step 2: Update Dockerfile to include CLI**

Modify `server/api/Dockerfile` - add psycopg2 to requirements and CLI entry point:

Update `server/api/requirements.txt`:

```
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy[asyncio]==2.0.25
asyncpg==0.29.0
psycopg2-binary==2.9.9
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6
```

**Step 3: Commit**

```bash
git add server/api/
git commit -m "feat: add admin CLI for user management"
```

---

## Task 9: Integration Test & Documentation

**Files:**
- Create: `server/README.md`
- Create: `server/scripts/test-setup.sh`

**Step 1: Create README**

Create `server/README.md`:

```markdown
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
```

**Step 2: Create test script**

Create `server/scripts/test-setup.sh`:

```bash
#!/bin/bash
set -e

echo "Testing Claude Insights Server setup..."

# Wait for services
echo "Waiting for services to be healthy..."
sleep 5

# Test API health
echo "Testing API health..."
curl -sf http://localhost:8080/health | grep -q "ok" && echo "✓ API healthy" || echo "✗ API failed"

# Test Dashboard health
echo "Testing Dashboard health..."
curl -sf http://localhost:8081/health | grep -q "ok" && echo "✓ Dashboard healthy" || echo "✗ Dashboard failed"

# Create test user
echo "Creating test user..."
docker compose exec -T api python -m app.cli create-user testuser --email test@dkd.de > /tmp/api_key.txt 2>&1
API_KEY=$(grep "dkd_sk_" /tmp/api_key.txt | awk '{print $NF}')

if [ -n "$API_KEY" ]; then
    echo "✓ User created"

    # Test session upload
    echo "Testing session upload..."
    RESPONSE=$(curl -sf -X POST http://localhost:8080/api/v1/sessions \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $API_KEY" \
        -d '{
            "session_id": "test-123",
            "project_name": "test-project",
            "started_at": "2026-01-22T10:00:00Z",
            "ended_at": "2026-01-22T11:00:00Z",
            "total_messages": 10,
            "total_tokens_in": 5000,
            "total_tokens_out": 2000,
            "tools": {"Read": {"count": 5, "success": 5}},
            "tags": ["testing"]
        }')

    echo $RESPONSE | grep -q "ok" && echo "✓ Session upload works" || echo "✗ Session upload failed"

    # Test team stats
    echo "Testing team stats..."
    curl -sf http://localhost:8080/api/v1/team/stats | grep -q "total_sessions" && echo "✓ Team stats work" || echo "✗ Team stats failed"

    # Cleanup test user
    docker compose exec -T api python -m app.cli delete-user testuser
    echo "✓ Test user cleaned up"
else
    echo "✗ Failed to create user"
fi

echo ""
echo "Setup test complete!"
```

**Step 3: Make script executable and commit**

```bash
chmod +x server/scripts/test-setup.sh
git add server/
git commit -m "docs: add server README and test script"
```

---

## Task 10: Final Integration & Merge Preparation

**Step 1: Verify all files exist**

```bash
ls -la server/
ls -la server/api/app/
ls -la server/dashboard/
ls -la server/exporter/
```

**Step 2: Build and test locally**

```bash
cd server
cp .env.example .env
docker compose build
docker compose up -d
./scripts/test-setup.sh
docker compose down
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete team server implementation

- FastAPI with session upload, user stats, team analytics
- PostgreSQL with full schema
- Flask dashboard with team overview and tools stats
- Parquet exporter for daily backups
- Admin CLI for user management
- Docker Compose deployment"
```

---

## Summary

| Task | Component | Description |
|------|-----------|-------------|
| 1 | Infrastructure | Docker Compose, PostgreSQL schema |
| 2 | API | FastAPI setup, models, database |
| 3 | API | Authentication (API keys) |
| 4 | API | Sessions router |
| 5 | API | User & Team routers |
| 6 | Dashboard | Flask with team stats |
| 7 | Exporter | Parquet daily exports |
| 8 | CLI | User management tool |
| 9 | Docs | README, test script |
| 10 | Integration | Build, test, prepare merge |

After completing all tasks, the server is ready for deployment. The Go client (separate repository) will connect to this server.
