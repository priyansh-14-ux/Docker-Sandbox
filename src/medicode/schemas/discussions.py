from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DiscussionCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: UUID | None = None


class DiscussionEntry(BaseModel):
    id: UUID
    parent_id: UUID | None
    author_profile_id: UUID
    author_name: str
    body: str
    created_at: datetime


class DiscussionThread(DiscussionEntry):
    replies: list[DiscussionEntry]
