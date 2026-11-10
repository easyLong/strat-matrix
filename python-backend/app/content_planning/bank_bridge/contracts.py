"""Business DTOs, independent of bank tables; Chinese aliases are the review contract."""

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

BEIJING = ZoneInfo('Asia/Shanghai')
T = TypeVar('T')


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)

    @field_validator('*', mode='after')
    @classmethod
    def normalize_time(cls, value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING)
        return value

    @field_validator('account_id', 'topic_id', 'content_id', 'owner_um', check_fields=False)
    @classmethod
    def trim_identity(cls, value):
        if isinstance(value, str) and value != value.strip():
            raise ValueError('业务标识不允许前后空格')
        return value


class PageQuery(Contract):
    page_no: int = Field(1, ge=1, alias='页码')
    page_size: int = Field(100, ge=1, le=500, alias='每页条数')

    @property
    def offset(self):
        return (self.page_no - 1) * self.page_size


class UpdatedQuery(PageQuery):
    updated_from: datetime | None = Field(None, alias='更新开始时间')
    updated_to: datetime | None = Field(None, alias='更新结束时间')

    @model_validator(mode='after')
    def check_range(self):
        if self.updated_from and self.updated_to and self.updated_from >= self.updated_to:
            raise ValueError('更新开始时间必须早于更新结束时间')
        return self


class AccountQuery(UpdatedQuery):
    account_ids: list[str] | None = Field(None, max_length=500, alias='账号ID列表')


class TopicQuery(UpdatedQuery):
    topic_ids: list[str] | None = Field(None, max_length=500, alias='选题ID列表')
    source: Literal['普通', '热点'] | None = Field(None, alias='选题来源')
    topic_type: Literal['营销', '非营销'] | None = Field(None, alias='选题类型')
    available_only: bool = Field(False, alias='仅可用选题')
    valid_at: datetime | None = Field(None, alias='有效时点')


class MarketingQuery(PageQuery):
    account_id: str = Field(min_length=1, max_length=64, alias='账号ID')


class Interaction(Contract):
    content_id: str = Field(min_length=1, alias='内容ID')
    account_id: str = Field(min_length=1, alias='账号ID')
    published_at: datetime = Field(alias='发布时间')
    title: str = Field('', alias='内容标题')
    likes: int | None = Field(None, ge=0, alias='点赞数')
    favorites: int | None = Field(None, ge=0, alias='收藏数')
    comments: int | None = Field(None, ge=0, alias='评论数')
    updated_at: datetime | None = Field(None, alias='互动数据更新时间')


class Account(Contract):
    account_id: str = Field(min_length=1, max_length=64, alias='账号ID')
    nickname: str = Field(min_length=1, alias='账号昵称')
    owner_um: str = Field('', alias='属主UM号')
    organization: str = Field('', alias='属主组织', description='最细映射至二级分行')
    platform: str = Field('', alias='平台')
    account_type: Literal['认证', '非认证'] | None = Field(None, alias='账号类型')
    eligible: bool = Field(alias='可参与策划')
    followers: int | None = Field(None, ge=0, alias='粉丝量')
    updated_at: datetime = Field(alias='账号信息更新时间')
    persona: str = Field('', alias='账号人设')
    gender: str | None = Field(None, alias='性别')
    interests: list[str] = Field(default_factory=list, alias='兴趣爱好')
    expression_style: str = Field('', alias='表达风格')
    interactions: list[Interaction] = Field(default_factory=list, alias='近三个月内容互动明细')
    _local_payload: dict = PrivateAttr(default_factory=dict)


class Topic(Contract):
    topic_id: str = Field(min_length=1, max_length=64, alias='选题ID')
    source: Literal['普通', '热点'] = Field(alias='选题来源')
    topic_type: Literal['营销', '非营销'] = Field(alias='选题类型')
    title: str = Field('', alias='选题标题')
    outline: str = Field('', alias='选题大纲')
    content_type: str = Field('', alias='选题二级分类')
    heat: float | None = Field(None, ge=0, allow_inf_nan=False, alias='热度')
    available: bool = Field(alias='可用状态')
    valid_from: datetime | None = Field(None, alias='有效开始时间')
    valid_to: datetime | None = Field(None, alias='有效结束时间')
    updated_at: datetime = Field(alias='选题更新时间')
    related_product: str = Field('', alias='关联产品')
    related_product_id: str = Field('', alias='关联产品ID')
    related_activity: str = Field('', alias='关联活动')
    related_activity_id: str = Field('', alias='关联活动ID')
    activity_organization: str = Field('', alias='活动所属组织')
    related_hotspot: str = Field('', alias='关联属地热点')
    _local_payload: dict = PrivateAttr(default_factory=dict)

    @field_validator('title', 'outline', mode='before')
    @classmethod
    def empty_optional_marketing_text(cls, value):
        return '' if value is None else value

    @model_validator(mode='after')
    def check_validity(self):
        if self.topic_type == '非营销' and not self.title.strip():
            raise ValueError('非营销选题必须提供选题标题')
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError('选题有效开始时间不可晚于结束时间')
        return self


class MarketingContent(Contract):
    content_id: str = Field(min_length=1, alias='内容ID')
    account_id: str = Field(min_length=1, alias='绑定账号ID')
    title: str = Field(alias='内容标题')
    body: str = Field(alias='内容正文')
    related_product: str = Field('', alias='关联产品')
    related_activity: str = Field('', alias='关联活动')
    approved_at: datetime = Field(alias='审核通过时间')


class EffectivePlacementQuery(Contract):
    account_id: str = Field(min_length=1, alias='账号ID')
    publish_date: date = Field(alias='投放日期')


class EffectivePlacement(Contract):
    placement_id: str = Field(min_length=1, alias='投放记录ID')
    account_id: str = Field(min_length=1, alias='账号ID')
    content_id: str = Field(min_length=1, alias='内容ID')
    publish_date: date = Field(alias='投放日期')


class Page(Contract, Generic[T]):
    total: int = Field(ge=0, alias='总数')
    page_no: int = Field(ge=1, alias='页码')
    page_size: int = Field(ge=1, le=500, alias='每页条数')
    items: list[T] = Field(alias='数据列表')

    @model_validator(mode='after')
    def check_page(self):
        remaining = max(0, self.total - (self.page_no - 1) * self.page_size)
        if len(self.items) != min(self.page_size, remaining):
            raise ValueError('分页总数与本页条数不一致')
        keys = []
        for item in self.items:
            keys.append(getattr(item, 'content_id', None) or getattr(item, 'topic_id', None) or getattr(item, 'account_id', None))
        if len(keys) != len(set(keys)) and keys:
            raise ValueError('同一页存在重复业务ID')
        return self


class AccountPlanningQuery(PageQuery):
    account_id: str = Field(min_length=1, alias='账号ID')
    date_from: date | None = Field(None, alias='投放开始日期')
    date_to: date | None = Field(None, alias='投放结束日期')

    @model_validator(mode='after')
    def check_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('投放开始日期不可晚于结束日期')
        return self


class UsageQuery(Contract):
    topic_ids: list[str] = Field(min_length=1, max_length=500, alias='选题ID列表')
    started_at: datetime | None = Field(None, alias='统计开始时间')
    ended_at: datetime | None = Field(None, alias='统计结束时间')

    @model_validator(mode='after')
    def check_input(self):
        if len(set(self.topic_ids)) != len(self.topic_ids) or any(not x.strip() for x in self.topic_ids):
            raise ValueError('选题ID必须非空且不重复')
        if self.started_at and self.ended_at and self.started_at >= self.ended_at:
            raise ValueError('统计开始时间必须早于统计结束时间')
        return self


class TopicIdentity(Contract):
    topic_id: str = Field(min_length=1, alias='选题ID')


class LabelTestItem(TopicIdentity):
    title: str = Field(min_length=1, alias='选题标题')
    outline: str = Field(min_length=1, alias='选题大纲')


class LabelTestQuery(Contract):
    topics: list[LabelTestItem] = Field(min_length=1, max_length=100, alias='选题详情数组')


class MarketingDemand(Contract):
    request_id: str = Field(min_length=1, max_length=64, alias='request_id', description='策划侧幂等请求标识')
    task_code: str = Field(min_length=1, alias='task_code', description='策划侧任务编号')
    topic: Topic = Field(alias='选题信息')
    quantity: int = Field(ge=1, le=1000, alias='生成内容数量')


class ProductionRecord(Contract):
    slot_id: str = Field(min_length=1, description='策划侧明细标识')
    version: int = Field(ge=1, description='策划侧结果版本')
    content_id: str | None = Field(None, alias='内容ID')
    status: Literal['待生产', '生产中', '已完成', '生产失败'] = Field(alias='内容状态')
    updated_at: datetime = Field(alias='状态更新时间')
    production_task_id: str | None = Field(None, max_length=64, alias='生产任务ID')
    error: str = Field('', max_length=500, alias='失败原因')

    @model_validator(mode='after')
    def require_generated_content(self):
        if self.status == '已完成' and not self.content_id:
            raise ValueError('已完成生产必须返回内容ID')
        return self


class ProductionQuery(Contract):
    slot_ids: list[str] = Field(min_length=1, max_length=500, description='策划侧明细标识列表')


class MarketingStatusQuery(Contract):
    task_codes: list[str] = Field(min_length=1, max_length=500, description='策划侧人工营销需求编号列表')


class MarketingProductionRecord(Contract):
    task_code: str = Field(min_length=1, max_length=64)
    status: Literal['待分配', '待生产', '生产中', '已完成', '生产失败'] = Field(alias='内容状态')
    completed_count: int = Field(ge=0, alias='完成数')
    failed_count: int = Field(ge=0, alias='失败数')
    account_count: int = Field(0, ge=0, alias='已分配账号数')
    updated_at: datetime = Field(alias='状态更新时间')


class DemandReceipt(Contract):
    request_id: str
    accepted: bool
    external_request_id: str | None = None


class PlanningRecord(Contract):
    batch_name: str
    batch_code: str
    plan_type: str
    slot_type: str
    cycle_start: date | None
    cycle_end: date | None
    publish_date: date | None
    weekday: int | None = Field(ge=1, le=7)
    planning_status: str
    content_status: Literal['待定题', '待生产', '生产中', '已完成', '生产失败']
    topic_info: dict[str, Any] | None
    marketing_content_info: dict[str, Any] | None
    updated_at: datetime


class PlanningOutput(Contract):
    queried_at: datetime
    status: Literal['success'] = 'success'
    account_id: str = Field(alias='账号ID')
    nickname: str = Field('', alias='账号昵称')
    total_count: int = Field(ge=0)
    page_no: int = Field(ge=1)
    page_size: int = Field(ge=1, le=500)
    planning_results: list[PlanningRecord]


class UsageResult(Contract):
    topic_id: str = Field(alias='选题ID')
    official_use_count: int = Field(ge=0)


class UsageOutput(Contract):
    queried_at: datetime
    status: Literal['success'] = 'success'
    topic_results: list[UsageResult]


class LabelResult(Contract):
    topic_id: str = Field(alias='选题ID')
    label_status: Literal['待打标', '打标中', '已完成', '打标失败']
    labels: dict[str, Any]


class LabelOutput(Contract):
    queried_at: datetime
    status: Literal['success'] = 'success'
    topic_result: LabelResult


class LabelTestResult(LabelResult):
    label_error: str = ''


class LabelTestOutput(Contract):
    tested_at: datetime
    status: Literal['success', 'failed']
    topic_results: list[LabelTestResult]
