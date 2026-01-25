from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.database import get_db
from app.auth import get_current_user
from app.models import PlanCreate, PlanResponse

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.post("", response_model=PlanResponse)
async def create_plan(
    plan: PlanCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload or update a plan."""
    warnings = []

    try:
        await db.execute(
            text("""
                INSERT INTO plans
                (user_id, name, title, content, created_at, updated_at)
                VALUES (:user_id, :name, :title, :content, :created_at, NOW())
                ON CONFLICT (user_id, name) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    updated_at = NOW()
            """),
            {
                "user_id": user["id"],
                "name": plan.name,
                "title": plan.title or plan.name,
                "content": plan.content,
                "created_at": plan.created_at or datetime.now()
            }
        )

        await db.commit()

        return PlanResponse(
            status="ok",
            name=plan.name,
            warnings=warnings
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=list[PlanResponse])
async def create_plans_batch(
    plans: list[PlanCreate],
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload multiple plans at once."""
    results = []
    for plan in plans:
        try:
            result = await create_plan(plan, user, db)
            results.append(result)
        except HTTPException as e:
            results.append(PlanResponse(
                status="error",
                name=plan.name,
                warnings=[str(e.detail)]
            ))
    return results
