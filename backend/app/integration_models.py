"""Contracts at the boundary with customer systems."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须带时区")
    return value


class SyncBase(BaseModel):
    source_batch_id: str = Field(min_length=1, max_length=64)
    mode: Literal["full", "incremental"] = "incremental"


class AccountFact(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=120)
    platform: str = ""
    organization: str = ""
    city: str = Field(default="", max_length=50)
    marketing_eligible: bool = False
    persona: str = Field(default="", max_length=80)
    target_audience: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    family_identity: str = ""
    expression_style: str = ""
    certified: bool = False
    followers: int = Field(default=0, ge=0)
    enabled: bool = True
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)


class AccountSync(SyncBase):
    records: list[AccountFact] = Field(min_length=1, max_length=500)


class TopicFact(BaseModel):
    topic_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    summary: str = ""
    outline: str = ""
    source: str = ""
    category: str = Field(default="", max_length=50)
    content_type: str = ""
    applicable_cities: list[str] = Field(default_factory=list)
    is_marketing: bool = False
    product_or_activity: str = ""
    generated_at: datetime | None = None
    approval_status: Literal["pending", "approved", "rejected"] = "pending"
    approved_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    enabled: bool = True
    updated_at: datetime

    @field_validator("updated_at", "generated_at", "approved_at", "valid_from", "valid_to")
    @classmethod
    def check_times(cls, value: datetime | None) -> datetime | None:
        return aware(value) if value else None

    @model_validator(mode="after")
    def check_validity(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from 不能晚于 valid_to")
        if self.is_marketing and self.approval_status == "approved" and not self.generated_at:
            raise ValueError("已审核通过的营销选题必须提供 generated_at")
        return self


class TopicSync(SyncBase):
    records: list[TopicFact] = Field(min_length=1, max_length=500)


class HistoryFact(BaseModel):
    content_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)
    topic_id: str = Field(default="", max_length=64)
    title: str = ""
    published_at: datetime | None = None
    content_type: str = ""
    t2_role: str = ""
    impressions: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    favorites: int = Field(default=0, ge=0)
    interactions: int = Field(default=0, ge=0)
    status: str = ""
    updated_at: datetime

    @field_validator("updated_at", "published_at")
    @classmethod
    def check_times(cls, value: datetime | None) -> datetime | None:
        return aware(value) if value else None


class HistorySync(SyncBase):
    records: list[HistoryFact] = Field(min_length=1, max_length=500)


class SyncResult(BaseModel):
    source_batch_id: str
    received: int
    inserted: int
    updated: int
    unchanged: int
    stale: int


class ContentStatusCallback(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    production_task_id: str = Field(min_length=1, max_length=64)
    slot_id: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    status: Literal["generated", "failed", "published"]
    content_id: str | None = Field(default=None, max_length=64)
    occurred_at: datetime
    failure_reason: str = ""

    @field_validator("occurred_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)

    @model_validator(mode="after")
    def check_content(self):
        if self.status in ("generated", "published") and not self.content_id:
            raise ValueError("生成完成或已发布必须提供 content_id")
        return self


class ContentReadyInput(BaseModel):
    fit_score: float = Field(ge=0, le=100)
    tags: dict[str, Any]
    agent_type: str = Field(min_length=1, max_length=64)
    content_agent_input: dict[str, Any]

    @model_validator(mode="after")
    def check_complete(self):
        if not all(f"T{number}" in self.tags for number in range(1, 8)):
            raise ValueError("tags 必须包含 T1–T7")
        if not self.content_agent_input:
            raise ValueError("content_agent_input 不能为空")
        return self
