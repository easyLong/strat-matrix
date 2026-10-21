"""Shared Doubao embedding service for topic and account profile workers."""

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .doubao_labeling import (DoubaoConfigurationError, DoubaoResponseError,
                              DoubaoUnavailable, embed_profile)
from .integration import require_integration_token


router = APIRouter(dependencies=[Depends(require_integration_token)])
LOG = logging.getLogger("shared-embedding-model")


class EmbeddingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["ordinary_topic_embedding", "account_profile_embedding"]
    profile: dict[str, Any]
    topic_id: str | None = Field(default=None, min_length=1, max_length=100)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    tag_version: int | None = Field(default=None, ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    preparation_id: int | None = Field(default=None, ge=1)
    account_id: str | None = Field(default=None, min_length=1, max_length=64)
    profile_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_identity(self):
        if self.task == "ordinary_topic_embedding":
            if not self.topic_id or not self.content_hash or self.tag_version is None:
                raise ValueError("选题画像向量任务缺少选题版本标识")
            if self.account_id or self.batch_id or self.preparation_id:
                raise ValueError("选题画像向量任务不能携带账号身份")
        else:
            if not self.account_id or not self.profile_hash or self.config_version is None:
                raise ValueError("账号画像向量任务缺少账号版本标识")
            if (self.batch_id is None) == (self.preparation_id is None):
                raise ValueError("账号画像向量任务必须且只能携带一个批次或准备记录 ID")
            if self.topic_id or self.content_hash or self.tag_version is not None:
                raise ValueError("账号画像向量任务不能携带选题身份")
        if not self.profile:
            raise ValueError("画像不能为空")
        return self


@router.post("/api/internal/embedding-model")
def generate_embedding(payload: EmbeddingInput) -> dict:
    """Embed a frozen topic or account profile using the globally configured model."""
    try:
        return embed_profile(payload.profile)
    except DoubaoConfigurationError as exc:
        raise HTTPException(503, str(exc)) from None
    except DoubaoUnavailable as exc:
        LOG.warning("共享向量模型暂不可用：%s", exc)
        raise HTTPException(503, str(exc)) from None
    except DoubaoResponseError as exc:
        LOG.warning("共享向量模型响应校验失败：%s", exc)
        raise HTTPException(502, str(exc)) from None
