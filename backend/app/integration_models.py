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
    snapshot_at: datetime | None = None

    @field_validator("snapshot_at")
    @classmethod
    def check_snapshot_time(cls, value: datetime | None) -> datetime | None:
        return aware(value) if value else None

    @model_validator(mode="after")
    def check_size(self):
        records = getattr(self, "records", [])
        if self.mode == "incremental" and not 1 <= len(records) <= 500:
            raise ValueError("增量同步每批必须包含 1～500 条记录")
        if self.mode == "full" and len(records) > 5000:
            raise ValueError("全量同步每批最多包含 5000 条记录")
        return self


class AccountInteraction(BaseModel):
    content_id: str = Field(default="", max_length=64)
    published_at: datetime
    title: str = Field(default="", max_length=255)
    red_star_count: int = Field(default=0, ge=0)
    favorite_count: int = Field(default=0, ge=0)
    comment_count: int = Field(default=0, ge=0)

    @field_validator("published_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)


class AccountFact(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=120)
    account_alias: str = Field(default="", max_length=120)
    account_status: bool | None = None
    certification_status: bool | None = None
    account_persona: str | None = Field(default=None, max_length=500)
    account_tags: list[str] = Field(default_factory=list, max_length=100)
    follower_count: int | None = Field(default=None, ge=0)
    interaction_data: list[AccountInteraction] | None = Field(default=None, max_length=1000)
    platform: str = ""
    organization: str = ""
    city: str = Field(default="", max_length=50)
    marketing_eligible: bool = False
    is_marketing_account: bool | None = None
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

    @model_validator(mode="after")
    def check_interaction_ids(self):
        ids = [post.content_id for post in self.interaction_data or [] if post.content_id]
        if len(ids) != len(set(ids)):
            raise ValueError("同一账号的 interaction_data 不能重复 content_id")
        return self


class AccountSync(SyncBase):
    records: list[AccountFact] = Field(max_length=5000)


class TopicFact(BaseModel):
    topic_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    summary: str = ""
    outline: str = ""
    source: str = ""
    category: str = Field(default="", max_length=50)
    content_type: str = ""
    topic_heat: float = Field(default=0, ge=0)
    status: bool | None = None
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
    records: list[TopicFact] = Field(max_length=5000)

    @model_validator(mode="after")
    def ordinary_only_full_snapshot(self):
        if self.mode == "full" and any(record.is_marketing for record in self.records):
            raise ValueError("普通选题全量快照不能包含营销选题；营销选题请使用 IF-03")
        return self


class MarketingTopicFact(BaseModel):
    topic_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    outline: str = ""
    content_type: str = ""
    approval_status: Literal["pending", "approved", "rejected"]
    approved_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    enabled: bool = True

    @field_validator("approved_at", "valid_from", "valid_to")
    @classmethod
    def check_times(cls, value: datetime | None) -> datetime | None:
        return aware(value) if value else None

    @model_validator(mode="after")
    def check_validity(self):
        if self.approval_status == "approved" and not self.approved_at:
            raise ValueError("已审核通过的营销选题必须提供 approved_at")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from 不能晚于 valid_to")
        return self


class MarketingTopicSync(BaseModel):
    source_batch_id: str = Field(min_length=1, max_length=64)
    snapshot_at: datetime
    records: list[MarketingTopicFact] = Field(max_length=5000)

    @field_validator("snapshot_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)

    @model_validator(mode="after")
    def check_records(self):
        ids = [record.topic_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("同一快照的 topic_id 不能重复")
        if any(value.startswith("DEMO-") for value in ids) or any(
            record.account_id.startswith("DEMO-") for record in self.records
        ):
            raise ValueError("DEMO- 编码保留给演示数据")
        return self


class HotspotTopicFact(BaseModel):
    topic_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    outline: str = ""
    content_type: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    enabled: bool = True

    @field_validator("valid_from", "valid_to")
    @classmethod
    def check_times(cls, value: datetime | None) -> datetime | None:
        return aware(value) if value else None

    @model_validator(mode="after")
    def check_validity(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from 不能晚于 valid_to")
        return self


class HotspotTopicSync(BaseModel):
    source_batch_id: str = Field(min_length=1, max_length=64)
    snapshot_at: datetime
    records: list[HotspotTopicFact] = Field(max_length=5000)

    @field_validator("snapshot_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)

    @model_validator(mode="after")
    def check_records(self):
        ids = [record.topic_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("同一快照的 topic_id 不能重复")
        if any(value.startswith("DEMO-") for value in ids):
            raise ValueError("DEMO- 编码保留给演示数据")
        return self


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
    deactivated: int = 0


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


class PublicationStatusCallback(BaseModel):
    """IF-06: publication facts, separate from content production progress."""

    event_id: str = Field(min_length=1, max_length=64)
    planning_result_id: int = Field(ge=1)
    result_version: int = Field(ge=1)
    topic_id: str = Field(min_length=1, max_length=64)
    topic_type: Literal["普通", "营销", "热点"]
    publish_status: Literal["未发布", "已发布"]
    occurred_at: datetime
    content_id: str | None = Field(default=None, max_length=64)

    @field_validator("occurred_at")
    @classmethod
    def check_time(cls, value: datetime) -> datetime:
        return aware(value)


class OfficialUsageQuery(BaseModel):
    topic_type: Literal["普通", "营销", "热点"]
    topic_ids: list[str] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_topic_ids(self):
        if any(not value.strip() or len(value) > 64 for value in self.topic_ids):
            raise ValueError("topic_ids 不能包含空值且每个 ID 最多 64 字符")
        if len(set(self.topic_ids)) != len(self.topic_ids):
            raise ValueError("topic_ids 不能重复")
        return self


class OfficialUsageFact(BaseModel):
    topic_id: str = Field(min_length=1, max_length=64)
    official_use_count: int = Field(ge=0, le=9223372036854775807)
    source_revision: int = Field(ge=1, le=9223372036854775807)


class OfficialUsageUpdate(BaseModel):
    topic_type: Literal["普通", "营销", "热点"]
    source_name: str = Field(min_length=1, max_length=64)
    records: list[OfficialUsageFact] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_duplicates(self):
        ids = [item.topic_id for item in self.records]
        if any(not item.strip() for item in ids) or not self.source_name.strip():
            raise ValueError("source_name 和 topic_id 不能为空")
        if len(set(ids)) != len(ids):
            raise ValueError("同一批次 topic_id 不能重复")
        if any(item.startswith("DEMO-") for item in ids):
            raise ValueError("DEMO- 编码保留给演示数据")
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
