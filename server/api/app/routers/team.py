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
