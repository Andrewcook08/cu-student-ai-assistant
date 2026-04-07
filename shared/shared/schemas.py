from typing import Any

from pydantic import BaseModel


class CourseCard(BaseModel):
    code: str
    title: str
    credits: str | None = None
    description: str | None = None
    topic_titles: str | None = None
    instruction_mode: str | None = None
    status: str | None = None
    attributes: list[str] | None = None


class Action(BaseModel):
    type: str
    label: str
    payload: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    structured_data: list[CourseCard] | None = None
    suggested_actions: list[Action] | None = None


class ErrorResponse(BaseModel):
    detail: str
