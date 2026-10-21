"""Durable local content-provider adapter and exactly-once topic use facts."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException

from .account_profile import canonical_json
from .db import connection
from .system_config import get_setting


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _object(raw):
    value = json.loads(raw) if raw else {}
    return value if isinstance(value, dict) else {}


def production_snapshot(cursor, batch, slot):
    cursor.execute('SELECT snapshot_json FROM godp_account_profile WHERE batch_id=%s '
                   "AND account_id=%s AND del_flag='N'", (batch['id'], slot['account_id']))
    frozen = cursor.fetchone()
    if frozen:
        account = _object(frozen['snapshot_json']).get('source_payload', {})
    else:
        cursor.execute("SELECT payload_json FROM godp_account_source WHERE account_id=%s AND del_flag='N'",
                       (slot['account_id'],))
        source = cursor.fetchone()
        account = _object(source['payload_json']) if source else {}
    account = {**account, 'account_id': slot['account_id'], 'account_name': slot['account_name']}
    kind = slot['topic_type'] or ('热点' if slot['slot_type'] == 'hotspot' else '普通')
    table = {'普通': 'godp_topic_source', '营销': 'godp_marketing_topic_source',
             '热点': 'godp_hotspot_topic_source'}[kind]
    query = f"SELECT payload_json FROM {table} WHERE topic_id=%s AND del_flag='N'"
    args = [slot['topic_id']]
    if kind == '营销':
        query += ' AND account_id=%s'
        args.append(slot['account_id'])
    cursor.execute(query, args)
    row = cursor.fetchone()
    topic = _object(row['payload_json']) if row else {}
    cursor.execute("SELECT tags_json FROM godp_topic_tag WHERE topic_id=%s AND del_flag='N'",
                   (slot['topic_id'],))
    tags = cursor.fetchone() if kind == '普通' else None
    topic = {**topic, 'topic_id': slot['topic_id'], 'title': slot['topic_title'],
             'outline': slot['outline'] or topic.get('outline', ''),
             'content_type': slot['content_type'] or topic.get('content_type', ''),
             'topic_type': kind, 'tags': _object(tags['tags_json']) if tags else {}}
    return {
        'production_task_id': f"{slot['slot_id']}-v{slot['version']}",
        'planning': {'batch_id': batch['id'], 'batch_code': batch['batch_code'],
                     'cycle_start': str(batch['cycle_start']), 'cycle_end': str(batch['cycle_end']),
                     'slot_id': slot['slot_id'], 'result_version': slot['version'],
                     'publish_date': str(slot['publish_date']),
                     'lifecycle_stage': slot['lifecycle_stage'], 'content_role': slot['content_role']},
        'account': account, 'topic': topic,
        'content_agent': {'agent_id': 'local-mock-content-agent',
                          'content_type': topic['content_type'], 'provider': 'local_mock'},
    }


def enqueue_batch(batch_id: int, provider: str | None = None, *, slot_id=None, agent_input=None):
    provider = provider or get_setting('CONTENT_PRODUCTION_MODE', 'disabled')
    if provider != 'local_mock':
        raise HTTPException(503, '内容生产方尚未配置')
    accepted = reused = waiting = 0
    task_ids = []
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_planning_batch WHERE id=%s AND del_flag='N'", (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            raise HTTPException(404, '策划批次不存在')
        query = ("SELECT i.*,s.slot_id,s.version,s.production_status FROM godp_planning_item i "
                       "JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                       "WHERE i.batch_id=%s AND i.del_flag='N' ")
        params = [batch_id]
        if slot_id is not None:
            query += 'AND s.slot_id=%s '
            params.append(slot_id)
        cursor.execute(query + 'ORDER BY i.id FOR UPDATE', params)
        slots = cursor.fetchall()
        if not slots:
            raise HTTPException(409, '该批次没有可生产的策划槽位')
        for slot in slots:
            if not slot['topic_id']:
                if slot_id is not None:
                    raise HTTPException(409, '占位槽尚未绑定真实选题')
                waiting += 1
                continue
            task_id = f"{slot['slot_id']}-v{slot['version']}"
            cursor.execute('SELECT provider FROM godp_content_production_task WHERE production_task_id=%s', (task_id,))
            existing = cursor.fetchone()
            if existing:
                if existing['provider'] != provider:
                    raise HTTPException(409, '该策划版本已绑定其他内容生产方')
                reused += 1
                task_ids.append(task_id)
                continue
            if slot['production_status'] != 'planned':
                raise HTTPException(409, '该策划版本已经开始或结束生产，不能重复提交')
            request = production_snapshot(cursor, batch, slot)
            if agent_input:
                request['content_agent'] = {'agent_id': agent_input['agent_type'], 'provider': provider,
                                            'input': agent_input['content_agent_input']}
                request['fit_score'] = agent_input.get('fit_score')
            # The durable row is the local mock provider's inbox. Commit means accepted,
            # while actual generation/callback occurs in a later worker tick.
            cursor.execute('INSERT INTO godp_content_production_task '
                           '(production_task_id,slot_id,result_version,batch_id,topic_id,topic_type,'
                           'provider,request_json,accepted_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (task_id, slot['slot_id'], slot['version'], batch_id, slot['topic_id'],
                            request['topic']['topic_type'], provider, canonical_json(request), utc_now()))
            cursor.execute("UPDATE godp_slot_state SET production_status='ready',update_by='content-production' "
                           'WHERE slot_id=%s AND version=%s', (slot['slot_id'], slot['version']))
            accepted += 1
            task_ids.append(task_id)
        db.commit()
    return {'batch_id': batch_id, 'provider': provider, 'accepted': accepted,
            'reused': reused, 'waiting_topic_count': waiting, 'production_task_ids': task_ids}


def record_success(cursor, payload, slot):
    """Called only inside the callback transaction, after slot/version validation."""
    kind = slot.get('topic_type') or ('热点' if slot.get('slot_type') == 'hotspot' else '普通')
    cursor.execute('INSERT IGNORE INTO godp_topic_usage_fact '
                   '(production_task_id,slot_id,result_version,topic_id,topic_type,content_id,occurred_at) '
                   'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   (payload.production_task_id, payload.slot_id, payload.version, slot['topic_id'],
                    kind, payload.content_id, payload.occurred_at.astimezone(timezone.utc).replace(tzinfo=None)))
    if cursor.rowcount == 1:
        cursor.execute('INSERT INTO godp_topic_official_usage '
                       '(topic_type,topic_id,official_use_count,source_revision,source_name) '
                       "VALUES (%s,%s,1,1,'content-production') ON DUPLICATE KEY UPDATE "
                       'official_use_count=official_use_count+1,source_revision=source_revision+1,'
                       "source_name='content-production',update_by='production-callback',del_flag='N'",
                       (kind, slot['topic_id']))


def apply_task_result(cursor, payload):
    cursor.execute('UPDATE godp_content_production_task SET status=%s,content_id=COALESCE(%s,content_id),'
                   'completed_at=COALESCE(completed_at,%s),lease_id=NULL,lease_expires_at=NULL,last_error=%s '
                   "WHERE production_task_id=%s AND del_flag='N' AND status<>'completed'",
                   ('failed' if payload.status == 'failed' else 'completed', payload.content_id,
                    utc_now(), (payload.failure_reason or '内容方回传生产失败')[:500] if payload.status == 'failed' else '',
                    payload.production_task_id))


def receive_result(task_id: str, status: str):
    """Minimal public contract: task identity + result; all slot fields stay server-side."""
    from .integration import receive_content_status
    from .integration_models import ContentStatusCallback
    mapped = {'completed': 'generated', '已完成': 'generated', '生产失败': 'failed',
              'generated': 'generated', 'failed': 'failed'}
    if status not in mapped:
        raise HTTPException(422, '内容结果状态必须为已完成或生产失败')
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_content_production_task WHERE production_task_id=%s AND del_flag='N'", (task_id,))
        task = cursor.fetchone()
    if not task:
        raise HTTPException(404, '内容生产任务不存在')
    result = receive_content_status(ContentStatusCallback(
        event_id=f'PROD-{uuid4().hex}', production_task_id=task_id,
        slot_id=task['slot_id'], version=task['result_version'], status=mapped[status],
        content_id=task['content_id'], occurred_at=datetime.now(timezone.utc)))
    return {'success': bool(result['accepted'])}


def mock_worker_once(limit=50):
    completed = 0
    for _ in range(limit):
        lease = uuid4().hex
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM godp_content_production_task WHERE del_flag='N' AND provider='local_mock' "
                           "AND (status='accepted' OR (status='processing' AND lease_expires_at<=UTC_TIMESTAMP(6))) "
                           'AND (next_attempt_at IS NULL OR next_attempt_at<=UTC_TIMESTAMP(6)) '
                           'ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED')
            task = cursor.fetchone()
            if not task:
                break
            cursor.execute("UPDATE godp_content_production_task SET status='processing',lease_id=%s,"
                           'lease_expires_at=%s,attempt_count=attempt_count+1 WHERE id=%s',
                           (lease, utc_now() + timedelta(minutes=2), task['id']))
            db.commit()
        try:
            request = _object(task['request_json'])
            content_id = 'MOCK-' + sha256(task['production_task_id'].encode()).hexdigest()[:24]
            response = {'provider': 'local_mock', 'content_id': content_id,
                        'title': request['topic']['title'], 'body': request['topic']['outline']}
            with connection() as db, db.cursor() as cursor:
                cursor.execute('UPDATE godp_content_production_task SET content_id=%s,response_json=%s '
                               "WHERE id=%s AND lease_id=%s AND status='processing' AND lease_expires_at>UTC_TIMESTAMP(6)",
                               (content_id, canonical_json(response), task['id'], lease))
                applied = cursor.rowcount
                db.commit()
            if applied:
                receive_result(task['production_task_id'], 'completed')
                completed += 1
        except Exception as exc:
            with connection() as db, db.cursor() as cursor:
                cursor.execute("UPDATE godp_content_production_task SET status='accepted',next_attempt_at=%s,"
                               'last_error=%s,lease_id=NULL,lease_expires_at=NULL '
                               "WHERE id=%s AND lease_id=%s AND status='processing'",
                               (utc_now() + timedelta(seconds=min(600, 30 * (task['attempt_count'] + 1))),
                                f'local_mock: {type(exc).__name__}', task['id'], lease))
                db.commit()
    return completed


def batch_flow(batch_id):
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT production_task_id,slot_id,result_version,topic_id,topic_type,provider,status,'
                       'request_json,response_json,content_id,attempt_count,last_error,accepted_at,completed_at '
                       "FROM godp_content_production_task WHERE batch_id=%s AND del_flag='N' ORDER BY id", (batch_id,))
        tasks = cursor.fetchall()
    for task in tasks:
        task['request'] = _object(task.pop('request_json'))
        task['response'] = _object(task.pop('response_json'))
        for field in ('accepted_at', 'completed_at'):
            if task[field] is not None:
                task[field] = task[field].replace(tzinfo=timezone.utc).isoformat()
    return {'batch_id': batch_id, 'tasks': tasks}
