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
    topic_id: str = Field(min_length=1, max_length=64)
    allocation_count: int = Field(ge=1, le=1000, strict=True)

    @field_validator('task_name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('任务名称不能为空')
        return value.strip()

    @field_validator('topic_id')
    @classmethod
    def clean_topic_id(cls, value):
        if not value.strip():
            raise ValueError('选题 ID 不能为空')
        return value.strip()


def summary(row):
    allocation_count = int(row.get('allocation_count') or 0)
    is_external_allocation = allocation_count > 0
    content_total_count = allocation_count if is_external_allocation else row['account_count'] * row['content_per_account']
    return dict(
        id=-row['id'], task_code=row['task_code'], preview_code='', task_name=row['task_name'],
        batch_code=row['task_code'], publish_date=None, planned_account_count=row['account_count'],
        result_count=0, failure_count=0, topic_count=len(json.loads(row.get('topic_snapshot_json') or '[]')), status=row['status'], planning_status=row['status'],
        content_status='待分配' if is_external_allocation else '待生产', content_failed_count=0, content_completed_count=0,
        content_total_count=content_total_count,
        content_completed_account_count=0, failure_reason='', batch_id=None, last_error='',
        created_at=row['create_time'], created_by=row['create_by'], updated_at=row['update_time'],
        content_mode='marketing', content_per_account=row['content_per_account'], allocation_count=allocation_count,
    )


def database_error(exc):
    return HTTPException(status_code=503, detail='营销任务暂不可用，请检查数据库连接及营销任务表初始化状态')


@router.post('', response_model=ManualTaskSummary, status_code=201)
def create_marketing_task(payload: MarketingTaskInput):
    # 营销账号由外部系统后续分配；创建时仅固化一个选题和需要分配的内容数量。
    from .main import list_topics

    canonical = json.dumps({'task_name': payload.task_name, 'topic_id': payload.topic_id,
                            'allocation_count': payload.allocation_count}, sort_keys=True)
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
            topic_catalog = {row['topic_id']: row for row in list_topics(limit=1000)}
            topic = topic_catalog.get(payload.topic_id)
            if topic is None:
                raise HTTPException(status_code=409, detail='选题已停用或不存在，请重新选择')
            cursor.execute('INSERT INTO godp_manual_marketing_task '
                           '(task_code,request_id,request_hash,task_name,allocation_count,content_per_account,account_count,account_snapshot_json,topic_snapshot_json,status) '
                           'VALUES (%s,%s,%s,%s,%s,0,0,%s,%s,\'待分配\') ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)',
                           ('MAN-MKT-' + uuid4().hex.upper(), request_id, fingerprint, payload.task_name,
                            payload.allocation_count, json.dumps([], ensure_ascii=False), json.dumps([topic], ensure_ascii=False, default=str)))
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
