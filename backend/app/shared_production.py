"""Legacy local acceptance simulator. Not registered as production HTTP APIs.

Production status is read by services.content_status; Java owns content execution.
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException

from .db import connection
from .bank_bridge.contracts import ProductionQuery
from .bank_bridge.factory import get_production
from .bank_bridge.ports import DataContractError, IntegrationUnavailable
from .adapters.bank.catalog import source_maps

BASE = ('SELECT i.*,s.id state_id,s.slot_id,s.version,s.production_status,s.content_id,'
        's.production_task_id,s.production_lease_expires_at,s.production_attempt_count,'
        's.production_error,s.production_reported_at,b.batch_code,b.plan_type,b.cycle_start,b.cycle_end '
        'FROM godp_slot_state s JOIN godp_planning_item i ON i.id=s.item_id '
        'JOIN godp_planning_batch b ON b.id=i.batch_id '
        "WHERE s.del_flag='N' AND i.del_flag='N' AND b.del_flag='N' ")
ELIGIBLE = ("AND i.topic_id<>'' AND s.topic_id=i.topic_id "
            "AND COALESCE(i.topic_type,'普通')<>'营销' AND i.slot_type<>'marketing' ")
STATE = {'待生产': 'planned', '生产中': 'ready', '已完成': 'generated', '生产失败': 'failed'}


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def append_record(cursor, slot, reason):
    cursor.execute('INSERT INTO godp_planning_adjustment '
                   '(item_id,result_version,adjustment_source,old_topic_id,old_topic_title,'
                   'new_topic_id,new_topic_title,reason,create_by,update_by) '
                   "VALUES (%s,%s,'内容生产',%s,%s,%s,%s,%s,'content-scanner','content-scanner')",
                   (slot['id'], slot['version'], slot['topic_id'], slot['topic_title'],
                    slot['topic_id'], slot['topic_title'], reason[:500]))


def production_input(slot, accounts, topics):
    account, topic = accounts.get(slot['account_id']), topics.get(slot['topic_id'])
    if account is None or topic is None or not topic.available:
        raise DataContractError('生产关联的账号或选题已不可用')
    if topic.topic_type != '非营销':
        raise DataContractError('当前选题已变为营销类型，须重新确认策划')
    content_type = slot.get('content_type') or topic.content_type
    if not content_type:
        raise DataContractError('选题缺少内容类型，无法选择内容Agent')
    return {
        'production_task_id': slot['production_task_id'],
        'planning': {key: slot.get(key) for key in ('slot_id', 'version', 'batch_id', 'batch_code',
            'plan_type', 'cycle_start', 'cycle_end', 'publish_date', 'content_role', 'lifecycle_stage')},
        'account': account.model_dump(mode='json', by_alias=True),
        'topic': {**topic.model_dump(mode='json', by_alias=True),
                  '选题标题': slot['topic_title'], '选题大纲': slot.get('outline') or topic.outline},
        'content_agent': {'content_type': content_type},
        'lease_expires_at': slot['production_lease_expires_at'],
    }


def claim_tasks(batch_id=None, limit=20, lease_seconds=600):
    from .bank_bridge.factory import source_mode
    if source_mode() == 'java_http':
        raise HTTPException(410, '内容生产由行内内容侧负责')
    if not 1 <= limit <= 100 or not 30 <= lease_seconds <= 7200:
        raise HTTPException(422, '生产领取数量或有效时长不合法')
    now = now_utc()
    with connection() as db, db.cursor() as cursor:
        query = BASE + ELIGIBLE + ("AND (s.production_status='planned' OR (s.production_status='ready' "
                'AND s.production_lease_expires_at<=%s)) ')
        params = [now]
        if batch_id is not None:
            query += 'AND i.batch_id=%s '
            params.append(batch_id)
        cursor.execute(query + 'ORDER BY i.publish_date,i.id LIMIT %s FOR UPDATE', [*params, limit])
        slots = cursor.fetchall()
        accounts, topics = source_maps(cursor, slots)
        tasks, errors = [], []
        for slot in slots:
            slot['production_task_id'] = 'PROD-' + uuid4().hex.upper()
            slot['production_lease_expires_at'] = now + timedelta(seconds=lease_seconds)
            try:
                payload = production_input(slot, accounts, topics)
            except DataContractError as exc:
                cursor.execute("UPDATE godp_slot_state SET production_status='failed',production_error=%s,"
                               "production_reported_at=%s,update_by='content-scanner' WHERE id=%s",
                               (str(exc), now, slot['state_id']))
                cursor.execute("UPDATE godp_planning_item SET status='生产失败',update_by='content-scanner' WHERE id=%s",
                               (slot['id'],))
                append_record(cursor, slot, str(exc))
                errors.append({'slot_id': slot['slot_id'], 'account_id': slot['account_id'], 'reason': str(exc)})
                continue
            cursor.execute("UPDATE godp_slot_state SET production_status='ready',production_task_id=%s,"
                           'production_lease_expires_at=%s,production_attempt_count=production_attempt_count+1,'
                           "production_error='',production_reported_at=%s,update_by='content-scanner' WHERE id=%s",
                           (slot['production_task_id'], slot['production_lease_expires_at'], now, slot['state_id']))
            cursor.execute("UPDATE godp_planning_item SET status='生产中',update_by='content-scanner' WHERE id=%s", (slot['id'],))
            append_record(cursor, slot, '内容侧已领取生产')
            tasks.append(payload)
        db.commit()
        return {'tasks': tasks, 'errors': errors}


def apply_result(cursor, slot, state, content_id, occurred_at, error=''):
    if state not in STATE.values():
        raise HTTPException(422, '无效的内容生产状态')
    old = slot['production_status']
    if old in ('generated', 'published', 'failed'):
        if state == old or old == 'published' and state == 'generated':
            if content_id and slot.get('content_id') and content_id != slot['content_id']:
                raise HTTPException(409, '重复结果的内容ID与已保存结果不一致')
            return {'accepted': True, 'reused': True}
        raise HTTPException(409, '当前版本已有终态，不能覆盖')
    last = slot.get('production_reported_at')
    if last and occurred_at < last or old == 'ready' and state == 'planned':
        return {'accepted': False, 'stale': True}
    task_id = slot.get('production_task_id') or 'SQL-' + sha256(
        f"{slot['slot_id']}:{slot['version']}".encode()).hexdigest()[:40]
    cursor.execute('UPDATE godp_slot_state SET production_status=%s,content_id=COALESCE(%s,content_id),'
                   'generated_at=CASE WHEN %s=\'generated\' THEN %s ELSE generated_at END,'
                   'production_task_id=%s,production_reported_at=%s,production_error=%s,'
                   "production_lease_expires_at=CASE WHEN %s IN ('generated','failed') THEN NULL ELSE production_lease_expires_at END,"
                   "update_by='content-scanner' WHERE id=%s",
                   (state, content_id, state, occurred_at, task_id, occurred_at,
                    (error or '内容生产失败')[:500] if state == 'failed' else '', state, slot['state_id']))
    cursor.execute("UPDATE godp_planning_item SET status=%s,update_by='content-scanner' WHERE id=%s",
                   ({'planned': '待生产', 'ready': '生产中', 'generated': '已生成', 'failed': '生产失败'}[state], slot['id']))
    if state == 'generated':
        kind = slot.get('topic_type') or ('热点' if slot['slot_type'] == 'hotspot' else '普通')
        cursor.execute('INSERT IGNORE INTO godp_topic_usage_fact '
                       '(production_task_id,slot_id,result_version,topic_id,topic_type,content_id,occurred_at) '
                       'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                       (task_id, slot['slot_id'], slot['version'], slot['topic_id'], kind, content_id, occurred_at))
        if cursor.rowcount == 1:
            cursor.execute('INSERT INTO godp_topic_official_usage '
                           '(topic_type,topic_id,official_use_count,source_revision,source_name) '
                           "VALUES (%s,%s,1,1,'content-production') ON DUPLICATE KEY UPDATE "
                           'official_use_count=official_use_count+1,source_revision=source_revision+1,'
                           "source_name='content-production',update_by='content-scanner',del_flag='N'", (kind, slot['topic_id']))
    if old != state:
        append_record(cursor, slot, next(label for label, value in STATE.items() if value == state))
    return {'accepted': True, 'reused': False}


def finish_task(production_task_id, status, content_id=None, error=''):
    from .bank_bridge.factory import source_mode
    if source_mode() == 'java_http':
        raise HTTPException(410, '策划侧不接收内容生产回调，只读取Java状态')
    if status not in ('已完成', '生产失败'):
        raise HTTPException(422, '生产结果必须是已完成或生产失败')
    now = now_utc()
    with connection() as db, db.cursor() as cursor:
        cursor.execute(BASE + 'AND s.production_task_id=%s FOR UPDATE', (production_task_id,))
        slot = cursor.fetchone()
        if not slot:
            raise HTTPException(409, '生产任务不存在或已被重新领取')
        if slot['production_status'] not in ('generated', 'published', 'failed') and (
                not slot['production_lease_expires_at'] or slot['production_lease_expires_at'] <= now):
            raise HTTPException(409, '生产领取已过期，请重新领取')
        result = apply_result(cursor, slot, STATE[status], content_id, now, error)
        db.commit()
        return result


def _reconcile_page(batch_id, limit, after_id):
    with connection() as db, db.cursor() as cursor:
        query = BASE + ELIGIBLE + "AND s.production_status IN ('planned','ready') AND s.id>%s "
        params = [after_id]
        if batch_id is not None:
            query += 'AND i.batch_id=%s '
            params.append(batch_id)
        cursor.execute(query + 'ORDER BY s.id LIMIT %s', [*params, limit])
        slots = cursor.fetchall()
        if not slots:
            return {'status': 'idle', 'applied': 0}
        try:
            provider = get_production(cursor)
            results = provider.production_results(ProductionQuery(slot_ids=[s['slot_id'] for s in slots]))
        except IntegrationUnavailable:
            return {'status': 'not_configured', 'applied': 0}
        expected = {s['slot_id'] for s in slots}
        seen, applied, stale = set(), 0, 0
        for record in results:
            if record.slot_id not in expected or record.slot_id in seen:
                raise DataContractError('生产结果包含未查询或重复的策划明细')
            seen.add(record.slot_id)
            cursor.execute(BASE + 'AND s.slot_id=%s FOR UPDATE', (record.slot_id,))
            slot = cursor.fetchone()
            if not slot or slot['version'] != record.version:
                stale += 1
                continue
            result = apply_result(cursor, slot, STATE[record.status], record.content_id,
                                  record.updated_at.astimezone(timezone.utc).replace(tzinfo=None))
            applied += int(result['accepted'] and not result.get('reused'))
            stale += int(result.get('stale', False))
        db.commit()
        return {'status': 'reconciled', 'applied': applied, 'stale': stale,
                'scanned': len(slots), 'next_after_id': slots[-1]['state_id']}


def reconcile_results(batch_id=None, limit=500):
    """Read every pending page, including records after old rows with no bank result."""
    size = max(1, min(limit, 500))
    report = {'status': 'idle', 'applied': 0, 'stale': 0, 'scanned': 0}
    after = 0
    while True:
        page = _reconcile_page(batch_id, size, after)
        if page['status'] == 'not_configured':
            return {**report, 'status': 'not_configured'}
        report['applied'] += page['applied']
        report['stale'] += page.get('stale', 0)
        report['scanned'] += page.get('scanned', 0)
        if page['status'] == 'reconciled':
            report['status'] = 'reconciled'
        if page.get('scanned', 0) < size:
            return report
        after = page['next_after_id']


def mock_scan_once(batch_id, limit=100):
    """Explicit local acceptance only. No production worker calls this automatically."""
    claimed = claim_tasks(batch_id, limit)
    for task in claimed['tasks']:
        finish_task(task['production_task_id'], '已完成',
                    'MOCK-' + sha256(task['production_task_id'].encode()).hexdigest()[:24])
    return {'completed': len(claimed['tasks']), 'errors': claimed['errors']}
