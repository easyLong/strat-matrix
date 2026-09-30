"""API contracts. Business rules will grow with the approved PRD."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StageTarget(BaseModel):
    name: str
    traffic: int = Field(ge=0, le=100)
    conversion: int = Field(ge=0, le=100)

class StrategyConfig(BaseModel):
    marketing_max: int = Field(default=1, ge=0, le=10000)
    rolling_posts: int = Field(default=10, ge=1, le=100)
    stage_targets: list[StageTarget] = Field(
        default_factory=lambda: [
            StageTarget(name="冷启验证期", traffic=80, conversion=20),
            StageTarget(name="流量增长期", traffic=70, conversion=30),
            StageTarget(name="转化试探期", traffic=50, conversion=50),
            StageTarget(name="转化放大期", traffic=30, conversion=70),
            StageTarget(name="稳定经营期", traffic=50, conversion=50),
        ]
    )

    @field_validator("stage_targets")
    @classmethod
    def validate_targets(cls, targets: list[StageTarget]) -> list[StageTarget]:
        if len(targets) != 5 or len({target.name for target in targets}) != 5:
            raise ValueError("必须配置五个互不重复的生命周期阶段")
        if any(target.traffic + target.conversion != 100 for target in targets):
            raise ValueError("每个阶段的流量与转化占比之和必须为 100%")
        return targets


class ConfigResponse(BaseModel):
    version: int
    updated_at: datetime | None
    config: StrategyConfig
    is_demo: bool = False


class ConfigVersionSummary(BaseModel):
    version: int
    action: str
    source_version: int | None = None
    created_at: datetime
    created_by: str
    config: StrategyConfig


class AccountOption(BaseModel):
    account_id: str
    account_name: str
    city: str
    persona: str
    marketing_eligible: bool
    status: str
    certified: bool | None = None
    followers: int | None = None
    traffic_trend: str = "数据不足"


class TopicOption(BaseModel):
    topic_id: str
    topic_title: str
    category: str
    content_type: str = ""
    outline: str = ""
    is_marketing: bool
    status: str


class ManualItem(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=120)
    topic_id: str = Field(min_length=1, max_length=64)
    topic_title: str = Field(min_length=1, max_length=255)


class ManualPlanCreate(BaseModel):
    publish_date: date
    items: list[ManualItem] = Field(min_length=1, max_length=1000)
    note: str = Field(default="", max_length=500)

    @field_validator("items")
    @classmethod
    def unique_accounts(cls, items: list[ManualItem]) -> list[ManualItem]:
        account_ids = [item.account_id for item in items]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("同一批次中账号不能重复")
        return items


class ManualPreviewInput(BaseModel):
    publish_date: date
    account_ids: list[str] = Field(default_factory=list, max_length=1000)
    target_count: int | None = Field(default=None, ge=1, le=1000)
    topic_ids: list[str] = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)
    city: str = ""
    persona: str = ""
    keyword: str = ""
    certified: bool | None = None
    followers_min: int | None = Field(default=None, ge=0)
    followers_max: int | None = Field(default=None, ge=0)
    traffic_trend: str = ""

    @field_validator("account_ids", "topic_ids")
    @classmethod
    def unique_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("账号或选题不能重复选择")
        if any(not value.strip() for value in values):
            raise ValueError("账号或选题 ID 不能为空")
        return values


class ManualPreviewResponse(BaseModel):
    preview_id: str
    publish_date: date
    expires_at: datetime
    items: list[ManualItem]
    note: str


class ManualTaskSummary(BaseModel):
    id: int
    task_code: str
    preview_code: str
    publish_date: date
    planned_account_count: int
    result_count: int
    failure_count: int
    topic_count: int
    status: str
    failure_reason: str
    batch_id: int | None = None
    last_error: str
    created_at: datetime
    updated_at: datetime


class ReplaceTopicInput(BaseModel):
    new_topic_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=500)
    expected_version: int = Field(ge=1)


class AdjustmentRecord(BaseModel):
    id: int
    item_id: int
    result_version: int
    adjustment_source: str
    old_topic_id: str
    old_topic_title: str
    new_topic_id: str
    new_topic_title: str
    reason: str
    created_at: datetime
    created_by: str


class ReplaceTopicResponse(BaseModel):
    item: dict
    adjustment: AdjustmentRecord


class BatchSummary(BaseModel):
    id: int
    batch_code: str
    plan_type: Literal["manual", "auto"]
    status: str
    cycle_start: date
    cycle_end: date
    account_count: int
    content_count: int
    result_count: int = 0
    note: str
    created_at: datetime


class PlanItemResponse(BaseModel):
    id: int
    account_id: str
    account_name: str
    publish_date: date
    slot_type: str
    topic_id: str
    topic_title: str
    status: str
    slot_id: str | None = None
    production_status: str | None = None
    publish_status: str = "状态未知"
    allow_replace: bool = False
    replace_block_reason: str = ""
    result_version: int | None = None
    content_type: str = ""
    outline: str = ""
    lifecycle_stage: str | None = None
    content_role: str | None = None


class BatchDetail(BatchSummary):
    items: list[PlanItemResponse]


class AccountPlanRecord(PlanItemResponse):
    batch_code: str
    plan_type: Literal["manual", "auto"]
    cycle_start: date
    cycle_end: date


class PlanningCycleSummary(BaseModel):
    cycle_id: str
    cycle_start: date
    cycle_end: date
    batch_count: int
    account_count: int
    auto_item_count: int
    manual_item_count: int
    content_count: int
    regular_slots: int
    marketing_slots: int
    hotspot_slots: int
    topic_uses: int
    unique_topics: int
    success_accounts: int
    failed_accounts: int
    updated_at: datetime


class AutoCycleSummary(BaseModel):
    cycle_id: str
    cycle_start: date
    cycle_end: date
    batch_count: int
    account_count: int
    success_accounts: int
    failed_accounts: int
    regular_slots: int
    marketing_slots: int
    hotspot_slots: int
    hotspot_submitted: int
    hotspot_pending: int
    status: str
    updated_at: datetime


class AutoFailure(BaseModel):
    batch_code: str
    account_id: str | None = None
    account_name: str
    reason: str

