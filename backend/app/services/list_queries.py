"""Paged read use cases; editing filter drafts remains a front-end concern."""
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..db import connection
from ..models import ManualTaskSummary
from ..planning_progress import planning_status_label
from ..adapters.mysql.task_queries import MANUAL_BASE
from .errors import ApplicationError


class PageQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    filters: dict[str, Any] = Field(default_factory=dict)


def validate_dates(start, end):
    try:
        first = date.fromisoformat(start) if start else None
        last = date.fromisoformat(end) if end else None
    except (TypeError, ValueError) as exc:
        raise ApplicationError(422, '请输入有效的起止日期') from exc
    if first and last and first > last:
        raise ApplicationError(422, '开始日期不能晚于结束日期')
    return first, last


def task_list_query(query: PageQuery):
    filters = query.filters
    start, end = validate_dates(filters.get('dateStart'), filters.get('dateEnd'))
    normal = ("SELECT q.*,0 AS content_per_account,0 AS allocation_count,CONCAT('manual:',q.id) AS task_key "
              'FROM (' + MANUAL_BASE + ') q')
    columns = ['id','task_code','preview_code','task_name','publish_date','planned_account_count',
               'result_count','failure_count','topic_count','status','failure_reason','batch_id','content_mode',
               'content_status','content_failed_count','content_completed_count','content_total_count',
               'content_completed_account_count','batch_code','last_error','created_at','created_by','updated_at',
               'content_per_account','allocation_count','task_key']
    total = '(CASE WHEN m.allocation_count>0 THEN m.allocation_count ELSE m.account_count*m.content_per_account END)'
    values = dict(id='-m.id', task_code='m.task_code', preview_code="''", task_name='m.task_name',
        publish_date='NULL', planned_account_count='m.account_count', result_count='0', failure_count='0',
        topic_count='COALESCE(JSON_LENGTH(m.topic_snapshot_json),0)', status='m.status', failure_reason="''", batch_id='NULL',
        content_mode="'marketing'", content_status="CASE WHEN m.status IN ('已完成','生产中','生产失败','待生产') THEN m.status WHEN m.allocation_count>0 THEN '待分配' ELSE '待生产' END",
        content_failed_count='m.content_failed_count', content_completed_count="CASE WHEN m.status='已完成' THEN "+total+' ELSE m.content_completed_count END',
        content_total_count=total, content_completed_account_count="CASE WHEN m.status='已完成' THEN m.account_count ELSE 0 END",
        batch_code='m.task_code', last_error="''", created_at='m.create_time', created_by='m.create_by', updated_at='m.update_time',
        content_per_account='m.content_per_account', allocation_count='m.allocation_count', task_key="CONCAT('marketing:',m.id)")
    marketing = 'SELECT '+','.join(values[key]+' AS '+key for key in columns)+" FROM godp_manual_marketing_task m WHERE m.del_flag='N'"
    union = '('+normal+' UNION ALL '+marketing+') q'
    where, params = ["1=1"], []
    for key, fields in [('batch', ('task_name', 'batch_code')), ('creator', ('created_by',))]:
        value = str(filters.get(key) or '').strip().lower()
        if value:
            where.append('('+' OR '.join('LOCATE(%s,LOWER(q.'+field+'))>0' for field in fields)+')')
            params.extend([value]*len(fields))
    for value, operator in ((start, '>='), (end, '<=')):
        if value:
            where.append('q.publish_date'+operator+'%s')
            params.append(value)
    status = filters.get('contentStatus')
    if status:
        expression = ("CASE WHEN q.content_completed_count>0 AND q.content_failed_count>0 THEN '部分失败' "
            "WHEN q.content_failed_count>0 THEN '生成失败' "
            "WHEN q.content_status IN ('待生产','待生成','未生成') THEN '待生成' "
            "WHEN q.content_status IN ('生产中','生成中','上传中') THEN '生成中' "
            "WHEN q.content_status IN ('已完成','已生成','已发布') THEN '已完成' "
            "WHEN q.content_status IN ('失败','异常','错误','生成失败','生产失败') THEN '生成失败' "
            "ELSE q.content_status END")
        where.append('('+expression+')=%s')
        params.append(status)
    suffix = ' FROM '+union+' WHERE '+' AND '.join(where)
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) total'+suffix, params)
        count = cursor.fetchone()['total']
        cursor.execute('SELECT q.*'+suffix+' ORDER BY q.created_at DESC,q.task_code DESC,q.task_key DESC LIMIT %s OFFSET %s',
                       [*params, query.page_size, (query.page-1)*query.page_size])
        rows = cursor.fetchall()
    for row in rows:
        row['planning_status'] = planning_status_label(row['status'], row['failure_count'])
    return {'items': [ManualTaskSummary.model_validate(row).model_dump() | {'task_key':row['task_key']} for row in rows],
            'total': count, 'page': query.page, 'page_size': query.page_size}
