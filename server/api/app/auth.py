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
