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
