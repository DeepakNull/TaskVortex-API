from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=100, description="Title of the task")
    description: str | None = Field(default=None, max_length=1000)
    task_type: Literal["data_extraction", "report_generation", "web_scraping"]
    complexity: Literal["light", "heavy"]
    priority: int = Field(default=1, ge=1, le=5, description="Priority from 1 to 5")
    payload: dict[str, Any]


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    priority: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def required_fields_not_null(self):
        # description is nullable in the DB; title and priority are not.
        for field in ("title", "priority"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TaskAccepted(BaseModel):
    task_id: UUID
    status: TaskStatus
    message: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    task_type: str | None
    priority: int
    status: TaskStatus
    payload: dict[str, Any]
    created_at: datetime