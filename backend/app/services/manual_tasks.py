"""Leased, restart-safe execution of accepted manual planning tasks."""
from datetime import timedelta
import json
import logging
from uuid import uuid4

from ..db import connection
from ..models import ManualItem, ManualPlanCreate
from .errors import ApplicationError

LOG = logging.getLogger('manual-task-worker')
MAX_ATTEMPTS = 4

def claim_task(task_id=None, *, lease_seconds=300):
    if not 30 <= lease_seconds <= 3600:
        raise ValueError('Invalid task lease duration')
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
        cursor.execute('SELECT UTC_TIMESTAMP(6) now')
        now=cursor.fetchone()['now']
        criterion = ("del_flag='N' AND status IN ('执行中','进行中') "
                     'AND (next_attempt_at IS NULL OR next_attempt_at<=%s) '
                     'AND (lease_expires_at IS NULL OR lease_expires_at<=%s) ')
        params = [now, now]
        if task_id is not None:
            criterion += 'AND id=%s '
            params.append(task_id)
        cursor.execute('SELECT * FROM godp_manual_task WHERE '+criterion+'ORDER BY id LIMIT 1 FOR UPDATE', params)
        task = cursor.fetchone()
        if not task:
            return None
        if task['batch_id']:
            state='执行失败' if task['failure_count'] else '已完成'
            cursor.execute("UPDATE godp_manual_task SET status=%s,execution_token=NULL,lease_expires_at=NULL,"
                           "next_attempt_at=NULL,update_by='manual-worker' WHERE id=%s",(state,task['id']))
            db.commit()
            return {'reconciled':True,'id':task['id'],'failed':bool(task['failure_count'])}
        if task['attempt_count'] >= MAX_ATTEMPTS:
            cursor.execute("UPDATE godp_manual_task SET status='执行失败',failure_count=planned_account_count,"
                           "failure_reason='执行重试次数已达上限',execution_token=NULL,lease_expires_at=NULL,"
                           "update_by='manual-worker' WHERE id=%s", (task['id'],))
            db.commit()
            return {'exhausted': True, 'id': task['id']}
        token = uuid4().hex
        cursor.execute('UPDATE godp_manual_task SET execution_token=%s,lease_expires_at=%s,'
                       "attempt_count=attempt_count+1,next_attempt_at=NULL,update_by='manual-worker' WHERE id=%s",
                       (token, now+timedelta(seconds=lease_seconds), task['id']))
        db.commit()
        return {**task, 'execution_token': token, 'attempt_count': task['attempt_count']+1}

def finish_claim(job):
    from .manual_planning import insert_manual_batch
    from .catalog import available_topics
    from ..bank_bridge.bridge import collect
    from ..bank_bridge.contracts import AccountQuery
    from ..bank_bridge.factory import get_source, use_adapters
    from ..bank_bridge.input_snapshot import freeze_inputs

    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT *,UTC_TIMESTAMP(6) database_now FROM godp_manual_task WHERE id=%s AND del_flag='N'", (job['id'],))
        candidate = cursor.fetchone()
        if (not candidate or candidate['status'] not in ('执行中', '进行中')
                or candidate['execution_token'] != job['execution_token']
                or not candidate['lease_expires_at'] or candidate['lease_expires_at'] <= candidate['database_now']):
            return {'status': 'stale', 'task_id': job['id']}
        cursor.execute("SELECT * FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N'",
                       (job['preview_code'],))
        prepared_preview = cursor.fetchone()
    if not prepared_preview:
        raise ApplicationError(409, '策划输入不存在，请重新创建任务')
    prepared_items = [ManualItem.model_validate(item) for item in json.loads(prepared_preview['allocations_json'])]
    if prepared_preview['status'] == 'submitted' and prepared_preview['batch_id']:
        from ..bank_bridge.memory import MemorySource
        source = MemorySource()  # Recovery of a committed batch needs no remote source.
    else:
        source = freeze_inputs([i.account_id for i in prepared_items], [i.topic_id for i in prepared_items])

    with use_adapters(source), connection() as db, db.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
        # Use the same preview -> task lock order as submission.
        cursor.execute("SELECT * FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N' FOR UPDATE",
                       (job['preview_code'],))
        preview = cursor.fetchone()
        cursor.execute("SELECT *,UTC_TIMESTAMP(6) database_now FROM godp_manual_task WHERE id=%s AND del_flag='N' FOR UPDATE", (job['id'],))
        current = cursor.fetchone()
        if (not current or current['status'] not in ('执行中','进行中')
                or current['execution_token'] != job['execution_token']
                or not current['lease_expires_at'] or current['lease_expires_at'] <= current['database_now']):
            return {'status':'stale','task_id':job['id']}
        if not preview:
            raise ApplicationError(409, '策划输入不存在，请重新创建任务')
        if preview['allocations_json'] != prepared_preview['allocations_json']:
            raise ApplicationError(409, '策划输入已变化，请重新创建任务')
        batch_id = preview['batch_id'] if preview['status']=='submitted' else None
        items = [ManualItem.model_validate(item) for item in json.loads(preview['allocations_json'])]
        if not batch_id:
            # Expiry applies before acceptance, not to a durable accepted request.
            accounts = list(collect(get_source(cursor),'accounts',
                            AccountQuery(account_ids=[item.account_id for item in items])))
            if len(accounts) != len(items):
                raise ApplicationError(409,'账号状态已变化，请重新创建任务')
            eligible={a.account_id:a.account_type=='认证' for a in accounts}
            topics=available_topics(cursor,list({item.topic_id for item in items}))
            if len(topics)!=len({item.topic_id for item in items}):
                raise ApplicationError(409,'选题状态已变化，请重新选择选题')
            if preview.get('content_mode')=='non_marketing' and any(t['is_marketing'] for t in topics.values()):
                raise ApplicationError(409,'选题已变为营销类型，请重新选择非营销选题')
            if any(topics[item.topic_id]['is_marketing'] and not eligible[item.account_id] for item in items):
                raise ApplicationError(409,'账号营销资格已变化，请重新提交')
            batch_id=insert_manual_batch(cursor,ManualPlanCreate(publish_date=preview['publish_date'],
                items=items,note=preview['note']),operator=current['create_by'],exclude_task_id=job['id'])
            cursor.execute("UPDATE godp_manual_preview SET status='submitted',batch_id=%s,update_by=%s WHERE id=%s",
                           (batch_id,current['create_by'],preview['id']))
        cursor.execute('SELECT UTC_TIMESTAMP(6) now')
        if current['lease_expires_at'] <= cursor.fetchone()['now']:
            db.rollback()
            return {'status':'stale','task_id':job['id']}
        cursor.execute("UPDATE godp_manual_task SET status='已完成',result_count=%s,failure_count=0,"
                       "failure_reason='',last_error='',batch_id=%s,execution_token=NULL,lease_expires_at=NULL,"
                       "next_attempt_at=NULL,update_by='manual-worker' WHERE id=%s AND execution_token=%s",
                       (len(items),batch_id,job['id'],job['execution_token']))
        db.commit()
        return {'status':'completed','task_id':job['id'],'batch_id':batch_id}

def record_failure(job, exc):
    permanent=400 <= getattr(exc,'status_code',500) < 500
    terminal=permanent or job['attempt_count']>=MAX_ATTEMPTS
    reason=exc.detail if permanent else '系统暂不可用，任务正在自动重试'
    if terminal and not permanent:
        reason='系统异常，执行重试次数已达上限'
    with connection() as db, db.cursor() as cursor:
        cursor.execute("UPDATE godp_manual_task SET status=%s,failure_reason=%s,last_error=%s,"
                       'failure_count=CASE WHEN %s THEN planned_account_count ELSE 0 END,'
                       "next_attempt_at=CASE WHEN %s THEN NULL ELSE TIMESTAMPADD(SECOND,%s,UTC_TIMESTAMP(6)) END,"
                       "execution_token=NULL,lease_expires_at=NULL,update_by='manual-worker' "
                       "WHERE id=%s AND execution_token=%s AND lease_expires_at>UTC_TIMESTAMP(6) AND status IN ('执行中','进行中')",
                       ('执行失败' if terminal else '执行中',str(reason)[:500],type(exc).__name__,terminal,
                        terminal,min(300,5*2**job['attempt_count']),
                        job['id'],job['execution_token']))
        accepted=cursor.rowcount>0
        db.commit()
    return {'status':('failed' if terminal else 'retrying') if accepted else 'stale','task_id':job['id']}

def run_once(task_id=None, *, limit=10):
    report={'status':'idle','completed':0,'failed':0,'retrying':0,'stale':0,'tasks':[]}
    for _ in range(max(1,min(limit,100))):
        job=claim_task(task_id)
        if not job:break
        if job.get('exhausted') or job.get('reconciled'):
            result={'status':'failed' if job.get('exhausted') or job.get('failed') else 'completed','task_id':job['id']}
        else:
            try:result=finish_claim(job)
            except Exception as exc:
                LOG.warning('Manual task %s attempt %s: %s',job['id'],job['attempt_count'],type(exc).__name__)
                result=record_failure(job,exc)
        report[result['status']]+=1
        report['tasks'].append(result)
        if task_id is not None:break
    report['status']='failed' if report['failed'] else 'retrying' if report['retrying'] else 'ok' if report['tasks'] else 'idle'
    return report
