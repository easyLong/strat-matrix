"""Persist undated marketing production requests separately from scheduled slots."""

import hashlib
import json
from uuid import UUID, uuid4

import pymysql
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .db import connection
from .models import ManualTaskSummary

router = APIRouter(prefix='/api/manual-plans/marketing-tasks')


class MarketingTaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    task_name: str = Field(min_length=1, max_length=120)
    account_ids: list[str] = Field(min_length=1, max_length=1000)
    topic_ids: list[str] = Field(min_length=1, max_length=100)
    content_per_account: int = Field(ge=1, le=100, strict=True)

    @field_validator('task_name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('任务名称不能为空')
        return value.strip()

    @field_validator('account_ids')
    @classmethod
    def clean_ids(cls, values):
        if any(not value.strip() for value in values) or len(set(values)) != len(values):
            raise ValueError('账号 ID 不能为空或重复')
        return values


def summary(row):
    return dict(
        id=-row['id'], task_code=row['task_code'], preview_code='', task_name=row['task_name'],
        batch_code=row['task_code'], publish_date=None, planned_account_count=row['account_count'],
        result_count=0, failure_count=0, topic_count=len(json.loads(row.get('topic_snapshot_json') or '[]')), status=row['status'], planning_status=row['status'],
        content_status='待生产', content_failed_count=0, content_completed_count=0,
        content_total_count=row['account_count'] * row['content_per_account'],
        content_completed_account_count=0, failure_reason='', batch_id=None, last_error='',
        created_at=row['create_time'], created_by=row['create_by'], updated_at=row['update_time'],
        content_mode='marketing', content_per_account=row['content_per_account'],
    )


def database_error(exc):
    return HTTPException(status_code=503, detail='营销任务暂不可用，请检查数据库连接及营销任务表初始化状态')


@router.post('', response_model=ManualTaskSummary, status_code=201)
def create_marketing_task(payload: MarketingTaskInput):
    # Import at call time: the account catalog applies the existing source eligibility rules.
    from .main import list_accounts, list_topics

    canonical = json.dumps({'task_name': payload.task_name, 'account_ids': sorted(payload.account_ids),
                            'topic_ids': payload.topic_ids, 'content_per_account': payload.content_per_account}, sort_keys=True)
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    request_id = str(payload.request_id)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT * FROM godp_manual_marketing_task WHERE request_id=%s', (request_id,))
            existing = cursor.fetchone()
            if existing:
                if existing['request_hash'] != fingerprint or existing['del_flag'] != 'N':
                    raise HTTPException(status_code=409, detail='该提交标识已使用，请重新创建任务')
                return summary(existing)
            catalog = {row['account_id']: row for row in list_accounts(limit=1000)}
            selected = [catalog.get(account_id) for account_id in payload.account_ids]
            if any(row is None for row in selected):
                raise HTTPException(status_code=409, detail='部分账号已停用或不存在，请重新选择')
            topic_catalog = {row['topic_id']: row for row in list_topics(limit=1000) if not row.get('is_marketing')}
            topics = [topic_catalog.get(topic_id) for topic_id in payload.topic_ids]
            if any(topic is None for topic in topics):
                raise HTTPException(status_code=409, detail='部分选题已停用或不存在，请重新选择')
            if any((row.get('account_type') or ('认证' if row.get('certified') is True else '')) != '认证'
                   for row in selected):
                raise HTTPException(status_code=422, detail='营销内容仅支持认证账号，请重新选择')
            # Lock the account rows and recheck activation before persisting the request.
            cursor.execute('SELECT account_code FROM godp_account WHERE del_flag=\'N\' AND status=\'启用\' '
                           'AND account_code IN (' + ','.join(['%s'] * len(selected)) + ') '
                           'ORDER BY account_code FOR UPDATE', sorted(payload.account_ids))
            if len(cursor.fetchall()) != len(selected):
                raise HTTPException(status_code=409, detail='账号状态已变化，请重新选择')
            cursor.execute('INSERT INTO godp_manual_marketing_task '
                           '(task_code,request_id,request_hash,task_name,content_per_account,account_count,account_snapshot_json,topic_snapshot_json) '
                           'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)',
                           ('MAN-MKT-' + uuid4().hex.upper(), request_id, fingerprint, payload.task_name,
                            payload.content_per_account, len(selected), json.dumps(selected, ensure_ascii=False), json.dumps(topics, ensure_ascii=False, default=str)))
            cursor.execute('SELECT * FROM godp_manual_marketing_task WHERE request_id=%s', (request_id,))
            row = cursor.fetchone()
            if row['request_hash'] != fingerprint:
                raise HTTPException(status_code=409, detail='提交内容已变化，请重新创建任务')
            db.commit()
            return summary(row)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error(exc) from exc


@router.get('', response_model=list[ManualTaskSummary])
def list_marketing_tasks(limit: int = 20):
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT * FROM godp_manual_marketing_task WHERE del_flag=\'N\' ORDER BY id DESC LIMIT %s',
                           (max(1, min(limit, 100)),))
            return [summary(row) for row in cursor.fetchall()]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error(exc) from exc


@router.get('/{task_code}')
def marketing_task_details(task_code: str):
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT * FROM godp_manual_marketing_task WHERE task_code=%s AND del_flag=\'N\'', (task_code,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='营销任务不存在')
            return {'task': summary(row), 'accounts': json.loads(row['account_snapshot_json']), 'topics': json.loads(row.get('topic_snapshot_json') or '[]')}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error(exc) from exc
