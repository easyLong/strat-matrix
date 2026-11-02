"""Translate application failures only at the HTTP boundary."""
from fastapi import HTTPException
from ..services.errors import ApplicationError

def invoke(handler, *args, **kwargs):
    try:
        return handler(*args, **kwargs)
    except ApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None

def db_error(exc):
    return HTTPException(status_code=503, detail='数据库暂不可用')
