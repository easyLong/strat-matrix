"""Idempotent algorithm configuration commands issued by Java's configuration release."""
import json
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from .api.security import require_integration_token
from .account_profile import canonical_json
from .business_snapshot import BusinessConfigSnapshot
from .db import connection
from .models import StrategyConfig

BUSINESS_FIELDS = set(BusinessConfigSnapshot.model_fields)
router = APIRouter(prefix='/api/internal/algorithm-config', dependencies=[Depends(require_integration_token)])


class ConfigCommand(BaseModel):
    command_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=0)
    algorithm_config: dict
    actor: str = Field(min_length=1, max_length=64)


@router.get('')
def read_algorithm_config():
    from .services.configuration import get_config
    return get_config()


@router.post('/commands')
def apply_config_command(payload: ConfigCommand):
    allowed = set(StrategyConfig.model_fields) - BUSINESS_FIELDS
    if set(payload.algorithm_config) != allowed:
        raise HTTPException(422, '算法配置字段不完整或包含业务字段')
    digest = sha256(canonical_json(payload.model_dump()).encode()).hexdigest()
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT config_json,version FROM godp_strategy_config WHERE config_key='operations' FOR UPDATE")
        current = cursor.fetchone()
        cursor.execute('SELECT * FROM godp_algorithm_config_command WHERE command_id=%s', (payload.command_id,))
        previous = cursor.fetchone()
        if previous:
            if previous['request_hash'] != digest: raise HTTPException(409, '配置命令编号已被其他请求使用')
            return json.loads(previous['result_json'])
        version = current['version'] if current else 0
        if payload.expected_version != version: raise HTTPException(409, '算法配置版本已变化')
        base = StrategyConfig.model_validate_json(current['config_json']) if current else StrategyConfig()
        try:
            config = StrategyConfig.model_validate({**base.model_dump(), **payload.algorithm_config})
        except ValueError as exc: raise HTTPException(422, '算法配置校验失败') from exc
        if current:
            cursor.execute("UPDATE godp_strategy_config SET config_json=%s,version=%s,update_by=%s WHERE config_key='operations'",
                           (config.model_dump_json(), version+1, payload.actor))
        else:
            cursor.execute("INSERT INTO godp_strategy_config(config_key,config_json,version,create_by,update_by) VALUES('operations',%s,1,%s,%s)",
                           (config.model_dump_json(), payload.actor, payload.actor))
        cursor.execute("INSERT INTO godp_strategy_config_version(config_key,version,config_json,action,create_by,update_by) VALUES('operations',%s,%s,'保存',%s,%s)",
                       (version+1, config.model_dump_json(), payload.actor, payload.actor))
        result = dict(version=version+1, config=config.model_dump(mode='json'))
        cursor.execute('INSERT INTO godp_algorithm_config_command(command_id,request_hash,result_json) VALUES(%s,%s,%s)',
                       (payload.command_id, digest, canonical_json(result)))
        db.commit()
        return result
