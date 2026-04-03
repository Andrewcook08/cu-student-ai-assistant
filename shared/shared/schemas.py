from pydantic import BaseModel


class CourseCard(BaseModel):
    course_code: str
    title: str
    description: str | None = None
    credits: int | None = None
    subject: str | None = None
    topic_titles: str | None = None
    attributes: list[str] | None = None


class Action(BaseModel):
    type: str
    payload: dict  # type: ignore[type-arg]


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    message: str
    session_id: str
    actions: list[Action] | None = None


class ErrorResponse(BaseModel):
    detail: str
