"""Pure manual allocation over frozen inputs. Never writes formal business tables.

Manual selection keeps the existing random eligible-topic allocation semantics;
the seed makes retries deterministic. This is NOT the automatic V19 matcher.
"""
import hashlib
import json
import random
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import APIRouter, Depends, HTTPException, Request
from .api.security import require_integration_token
from .db import connection


class ComputeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^JMAN-[A-Za-z0-9-]+$', max_length=64)
    accounts: list[dict] = Field(min_length=1, max_length=1000)
    topics: list[dict] = Field(min_length=1, max_length=100)
    algorithm_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def valid_entities(self):
        ids = [a.get('account_id') for a in self.accounts]
        if any(not i for i in ids) or len(ids) != len(set(ids)):
            raise ValueError('账号不可为空或重复')
        if any(not t.get('topic_id') or t.get('is_marketing') for t in self.topics):
            raise ValueError('普通人工计算仅支持非营销选题')
        return self


def allocate(payload: ComputeInput):
    rng = random.Random(payload.request_id)
    return {'algorithm_version': payload.algorithm_version, 'items': [
        {'account_id': account['account_id'], 'topic_id': rng.choice(payload.topics)['topic_id'],
         'lifecycle_stage': account.get('lifecycle_stage'), 'method': 'manual-selected-random-v1'}
        for account in payload.accounts]}


def accept(payload):
    frozen = json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(frozen.encode()).hexdigest()
    with connection() as db, db.cursor() as cursor:
        cursor.execute('INSERT IGNORE INTO godp_manual_compute(request_id,input_hash,input_json) VALUES(%s,%s,%s)',
                       (payload.request_id, digest, frozen))
        cursor.execute("SELECT input_hash FROM godp_manual_compute WHERE del_flag='N' AND request_id=%s", (payload.request_id,))
        if cursor.fetchone()['input_hash'] != digest:
            raise HTTPException(409, '同一计算任务不可更改输入')
        db.commit()
    return read(payload.request_id)


def read(request_id):
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT request_id,status,result_json,error_message FROM godp_manual_compute WHERE del_flag='N' AND request_id=%s", (request_id,))
        row = cursor.fetchone()
    if not row:
        raise HTTPException(404, '计算任务不存在')
    return {'request_id': row['request_id'], 'status': row['status'],
            'result': json.loads(row['result_json']) if row['result_json'] else None, 'error': row['error_message']}


def run_once(limit=10):
    completed = 0
    for _ in range(limit):
        token = uuid4().hex
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT request_id,input_json FROM godp_manual_compute WHERE del_flag='N' AND (status='pending' OR (status='running' AND lease_until<UTC_TIMESTAMP(6))) ORDER BY created_at LIMIT 1 FOR UPDATE")
            row = cursor.fetchone()
            if not row:
                break
            cursor.execute("UPDATE godp_manual_compute SET status='running',execution_token=%s,lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 2 MINUTE) WHERE del_flag='N' AND request_id=%s", (token,row['request_id']))
            db.commit()
        try:
            result = allocate(ComputeInput.model_validate_json(row['input_json']))
            status, error = 'succeeded', ''
        except Exception:
            result, status, error = None, 'failed', '冻结输入无法完成计算，请检查账号和选题'
        with connection() as db, db.cursor() as cursor:
            cursor.execute("UPDATE godp_manual_compute SET status=%s,result_json=%s,error_message=%s,execution_token=NULL,lease_until=NULL WHERE del_flag='N' AND request_id=%s AND execution_token=%s AND lease_until>UTC_TIMESTAMP(6)",
                           (status,json.dumps(result,ensure_ascii=False),error,row['request_id'],token))
            db.commit()
        completed += 1
    return {'processed': completed}


router = APIRouter(prefix='/api/internal/manual-computations', dependencies=[Depends(require_integration_token)])


@router.post('', status_code=202)
def submit(payload: ComputeInput, request: Request):
    receipt = accept(payload)
    executor = getattr(request.app.state, 'background_executor', None)
    if executor:
        try:
            executor.wake(['manual_compute'])
        except RuntimeError:
            pass  # Persisted; Java retries the same request after restart.
    return receipt


@router.post('/{request_id}/query')
def status(request_id: str):
    return read(request_id)
