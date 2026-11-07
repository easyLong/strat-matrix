"""Java-owned generation rules, frozen once per business task."""

from typing import Annotated, Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .account_profile import canonical_json


class BusinessConfigSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    planning_days: list[int] = Field(min_length=1, max_length=7)
    schedule_day: int = Field(ge=1, le=7, strict=True)
    schedule_time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    marketing_max: int = Field(ge=0, le=10000, strict=True)
    hotspot_ratio: int = Field(ge=0, le=100, strict=True)
    content_production_lead_days: dict[
        Literal['ordinary', 'marketing', 'hotspot'],
        Annotated[int, Field(ge=0, le=365, strict=True)] | None,
    ] | None = None

    @field_validator('planning_days')
    @classmethod
    def check_days(cls, days):
        if len(set(days)) != len(days) or any(type(day) is not int or not 1 <= day <= 7 for day in days):
            raise ValueError('策划日须为不重复的周一至周日')
        return sorted(days)


def normalize_business_snapshot(version=None, config=None):
    if version is None and config is None:
        return None, None
    if type(version) is not int or version < 1 or not isinstance(config, dict):
        raise HTTPException(422, 'Java业务配置版本和快照必须同时提供')
    try:
        # New optional metadata must not change old frozen payload fingerprints.
        normalized = BusinessConfigSnapshot.model_validate(config).model_dump(exclude_unset=True)
    except ValueError as exc:
        raise HTTPException(422, 'Java业务配置快照无效') from exc
    return version, canonical_json(normalized)


def ensure_business_snapshot_columns(cursor):
    for table in ('godp_planning_pipeline_run', 'godp_ai_preparation'):
        cursor.execute(f'SHOW COLUMNS FROM {table}')
        columns = {row['Field'] for row in cursor.fetchall()}
        for name, definition in (
            ('business_config_version', "INT NULL COMMENT 'Java业务任务冻结的生成规则版本，旧任务为空'"),
            ('business_config_json', "LONGTEXT NULL COMMENT 'Java业务任务冻结的策划日调度时间营销上限与热点占比快照'"),
        ):
            if name not in columns:
                cursor.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
