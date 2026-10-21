from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    knowledge_base_ids: list[Annotated[str, Field(min_length=1, max_length=36)]] = Field(default_factory=list, max_length=20)
    # Accept the former single-library field for existing API clients.
    knowledge_base_id: str | None = Field(default=None, min_length=1, max_length=36)
    question: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)
    history_summary: str = Field(default="", max_length=12000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=36)
    attachment_filename: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def normalize_knowledge_base_ids(self):
        ids = self.knowledge_base_ids or ([self.knowledge_base_id] if self.knowledge_base_id else [])
        ids = list(dict.fromkeys(ids))
        if len(ids) > 20:
            raise ValueError("Select no more than 20 knowledge bases")
        self.knowledge_base_ids = ids
        return self


class UserCreate(BaseModel):
    username: str
    password: str
    department_id: str
    clearance: int
    role_ids: list[str] = Field(min_length=1, max_length=64)


class UserRolesUpdate(BaseModel):
    role_ids: list[str] = Field(min_length=1, max_length=64)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=190)
    description: str = Field(default="", max_length=1000)


class KnowledgeBaseMemoryInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=2000)


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=500)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    description: str = Field(default="", max_length=500)
    permissions: list[str] = Field(default_factory=list)
