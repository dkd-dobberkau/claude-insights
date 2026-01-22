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
