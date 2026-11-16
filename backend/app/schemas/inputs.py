from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.policy import CATEGORIES


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Register(Input):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)
    role: Literal["worker", "client"]
    adult_confirmed: Literal[True]


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class EmailInput(Input):
    email: EmailStr


class TokenInput(Input):
    token: str = Field(min_length=20, max_length=200)


class ResetPassword(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class ChangePassword(Input):
    current_password: str = Field(max_length=128)
    password: str = Field(min_length=12, max_length=128)


class WorkerInput(Input):
    display_name: str = Field(min_length=2, max_length=80)
    headline: str = Field(min_length=5, max_length=160)
    bio: str = Field(min_length=20, max_length=3000)
    city: str = Field(min_length=2, max_length=80)
    category: str
    skills: list[str] = Field(min_length=1, max_length=15)
    hourly_rate: int = Field(ge=100, le=100000, strict=True)
    currency: Literal["CAD", "USD", "EUR"] = "CAD"
    available: bool = True
    published: bool = False

    @field_validator("category")
    @classmethod
    def category_allowed(cls, value):
        if value not in CATEGORIES:
            raise ValueError("Unsupported category")
        return value

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, value):
        if any(not s.strip() or len(s) > 60 for s in value):
            raise ValueError("Skills must contain 1 to 60 characters")
        return sorted(set(s.strip().lower() for s in value))


class TaskInput(Input):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=20, max_length=8000)
    category: str
    required_skills: list[str] = Field(default_factory=list, max_length=15)
    city: str = Field(min_length=2, max_length=80)
    budget: int = Field(ge=100, le=1000000, strict=True)
    currency: Literal["CAD", "USD", "EUR"] = "CAD"
    expected_minutes: int = Field(default=60, ge=15, le=1440)
    deadline: datetime | None = None
    requirements: str = Field(default="", max_length=4000)
    visibility: Literal["PUBLIC", "PRIVATE"] = "PUBLIC"


class ApplicationInput(Input):
    proposal: str = Field(min_length=10, max_length=3000)
    compensation: int = Field(ge=100, le=1000000, strict=True)
    estimated_minutes: int = Field(ge=15, le=1440)


class MessageInput(Input):
    content: str = Field(min_length=1, max_length=4000)


class AgentMessage(MessageInput):
    task_id: str = Field(min_length=36, max_length=36)


class SubmissionInput(Input):
    report: str = Field(min_length=20, max_length=12000)


class ReasonInput(Input):
    reason: str = Field(min_length=10, max_length=3000)


class ReviewInput(Input):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=5, max_length=2000)


class KeyInput(Input):
    name: str = Field(min_length=2, max_length=80)
    scopes: list[
        Literal["workers:read", "tasks:read", "tasks:write", "messages:write", "notifications:read"]
    ] = Field(min_length=1, max_length=5)


class PlaygroundInput(Input):
    prompt: str = Field(min_length=20, max_length=4000)


class ServiceInput(Input):
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=20, max_length=2000)
    price: int = Field(ge=100, le=100000)
