from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import get_current_user
from app.models import SessionCreate, SessionResponse


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp string to datetime object."""
    if ts is None:
        return None
    # Handle 'Z' suffix (replace with +00:00 for fromisoformat)
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    return datetime.fromisoformat(ts)

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
                        "ts": parse_timestamp(msg.get("timestamp")),
                        "role": msg.get("role", "unknown"),
                        "content": msg.get("content", "")
                    }
                )

        # Insert token usage (per-message/per-model tracking)
        for tu in session.token_usage:
            await db.execute(
                text("""
                    INSERT INTO token_usage
                    (session_id, message_sequence, timestamp, model,
                     input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
                    VALUES (:session_id, :seq, :ts, :model, :input, :output, :cache_read, :cache_creation)
                """),
                {
                    "session_id": session.session_id,
                    "seq": tu.message_sequence,
                    "ts": tu.timestamp,
                    "model": tu.model,
                    "input": tu.input_tokens,
                    "output": tu.output_tokens,
                    "cache_read": tu.cache_read_tokens,
                    "cache_creation": tu.cache_creation_tokens
                }
            )

        # Insert detailed tool calls (if full sharing)
        if store_messages:
            for tc in session.tool_calls:
                await db.execute(
                    text("""
                        INSERT INTO tool_calls
                        (session_id, sequence, tool_name, tool_input, tool_output, duration_ms, success)
                        VALUES (:session_id, :seq, :name, :input, :output, :duration, :success)
                    """),
                    {
                        "session_id": session.session_id,
                        "seq": tc.message_sequence,
                        "name": tc.tool_name,
                        "input": tc.tool_input,
                        "output": tc.tool_output,
                        "duration": tc.duration_ms,
                        "success": tc.success
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
