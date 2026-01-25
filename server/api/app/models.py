from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ToolStats(BaseModel):
    count: int
    success: int = 0
    errors: int = 0


class TokenUsageItem(BaseModel):
    message_sequence: Optional[int] = None
    timestamp: Optional[datetime] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ToolCallItem(BaseModel):
    message_sequence: Optional[int] = None
    tool_name: str
    tool_input: Optional[str] = None
    tool_output: Optional[str] = None
    duration_ms: Optional[int] = None
    success: bool = True


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
    messages: Optional[list[dict]] = None
    token_usage: list[TokenUsageItem] = Field(default_factory=list)
    tool_calls: list[ToolCallItem] = Field(default_factory=list)


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


class PlanCreate(BaseModel):
    name: str
    title: Optional[str] = None
    content: str
    created_at: Optional[datetime] = None


class PlanResponse(BaseModel):
    status: str
    name: str
    warnings: list[str] = Field(default_factory=list)
