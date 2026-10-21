"""Internal Doubao model service used by the existing labeling worker."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from .doubao_labeling import (DoubaoConfigurationError, DoubaoResponseError,
                              DoubaoUnavailable, LabelInput, label_topic)
from .integration import require_integration_token


router = APIRouter(dependencies=[Depends(require_integration_token)])
LOG = logging.getLogger("topic-label-model")


@router.post("/api/internal/topic-label-model")
def generate_topic_labels(payload: LabelInput) -> dict:
    """Infer labels without modifying topics or claiming/completing a job."""
    try:
        return label_topic(payload)
    except DoubaoConfigurationError as exc:
        raise HTTPException(503, str(exc)) from None
    except DoubaoUnavailable as exc:
        LOG.warning("豆包打标服务暂不可用：%s", exc)
        raise HTTPException(503, str(exc)) from None
    except DoubaoResponseError as exc:
        LOG.warning("豆包打标响应校验失败：%s", exc)
        raise HTTPException(502, str(exc)) from None
