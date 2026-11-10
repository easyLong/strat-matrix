"""Read content-owned status and project it into the planner database atomically.

No production submission, claiming, lease ownership or content callbacks live here.
"""
from datetime import datetime, timezone
from hashlib import sha256

from ..db import connection
from ..bank_bridge.factory import get_production
from ..bank_bridge.contracts import ProductionQuery, MarketingStatusQuery
from ..bank_bridge.ports import DataContractError, IntegrationUnavailable
from .errors import ApplicationError as HTTPException

BASE = ("SELECT i.*,s.id state_id,s.slot_id,s.version,s.production_status,s.content_id,"
        "s.production_task_id,s.production_reported_at,b.batch_code,b.plan_type,b.cycle_start,b.cycle_end "
        "FROM godp_slot_state s JOIN godp_planning_item i ON i.id=s.item_id "
        "JOIN godp_planning_batch b ON b.id=i.batch_id "
        "WHERE s.del_flag='N' AND i.del_flag='N' AND b.del_flag='N' ")
ELIGIBLE = ("AND i.topic_id<>'' AND s.topic_id=i.topic_id "
            "AND COALESCE(i.topic_type,'普通')<>'营销' AND i.slot_type<>'marketing' ")
STATE = {'待生产':'planned','生产中':'ready','已完成':'generated','生产失败':'failed'}

def append_record(cursor, slot, reason):
    cursor.execute('INSERT INTO godp_planning_adjustment '
                   '(item_id,result_version,adjustment_source,old_topic_id,old_topic_title,'
                   'new_topic_id,new_topic_title,reason,create_by,update_by) '
                   "VALUES (%s,%s,'内容生产',%s,%s,%s,%s,%s,'status-reader','status-reader')",
                   (slot['id'], slot['version'], slot['topic_id'], slot['topic_title'],
                    slot['topic_id'], slot['topic_title'], reason[:500]))


def apply_result(cursor, slot, state, content_id, occurred_at, error='', production_task_id=None):
    if state not in STATE.values():
        raise HTTPException(422, '无效的内容生产状态')
    old = slot['production_status']
    if old in ('generated', 'published'):
        if state == old or old == 'published' and state == 'generated':
            if content_id and slot.get('content_id') and content_id != slot['content_id']:
                raise HTTPException(409, '重复结果的内容ID与已保存结果不一致')
            return {'accepted': True, 'reused': True}
        raise HTTPException(409, '当前版本已有终态，不能覆盖')
    last = slot.get('production_reported_at')
    if last and occurred_at < last or old == 'ready' and state == 'planned':
        return {'accepted': False, 'stale': True}
    if old == state and old == 'failed':
        return {'accepted': True, 'reused': True}
    task_id = production_task_id or slot.get('production_task_id') or 'STATUS-' + sha256(
        f"{slot['slot_id']}:{slot['version']}".encode()).hexdigest()[:40]
    cursor.execute('UPDATE godp_slot_state SET production_status=%s,content_id=COALESCE(%s,content_id),'
                   'generated_at=CASE WHEN %s=\'generated\' THEN %s ELSE generated_at END,'
                   'production_task_id=%s,production_reported_at=%s,production_error=%s,'
                   "production_lease_expires_at=CASE WHEN %s IN ('generated','failed') THEN NULL ELSE production_lease_expires_at END,"
                   "update_by='status-reader' WHERE id=%s",
                   (state, content_id, state, occurred_at, task_id, occurred_at,
                    (error or '内容生产失败')[:500] if state == 'failed' else '', state, slot['state_id']))
    cursor.execute("UPDATE godp_planning_item SET status=%s,update_by='status-reader' WHERE id=%s",
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
                           "source_name='content-production',update_by='status-reader',del_flag='N'", (kind, slot['topic_id']))
    if old != state:
        append_record(cursor, slot, next(label for label, value in STATE.items() if value == state))
    return {'accepted': True, 'reused': False}


def _reconcile_page(batch_id, limit, after_id):
    # Read and release the DB connection before any remote request. Java HTTP
    # cannot participate in a local transaction and must never run under row locks.
    with connection() as db, db.cursor() as cursor:
        query = BASE + ELIGIBLE + "AND s.production_status IN ('planned','ready','failed') AND s.id>%s "
        params = [after_id]
        if batch_id is not None:
            query += 'AND i.batch_id=%s '
            params.append(batch_id)
        cursor.execute(query + 'ORDER BY s.id LIMIT %s', [*params, limit])
        slots = cursor.fetchall()
    if not slots:
        return {'status': 'idle', 'applied': 0, 'scanned': 0}
    try:
        provider = get_production(None)
    except IntegrationUnavailable:
        return {'status': 'not_configured', 'applied': 0, 'scanned': 0}
    results = provider.production_results(ProductionQuery(slot_ids=[s['slot_id'] for s in slots]))
    expected = {slot['slot_id']: slot['version'] for slot in slots}
    seen = set()
    for record in results:
        if record.slot_id not in expected or record.slot_id in seen:
            raise DataContractError('生产状态返回未查询或重复的策划明细')
        seen.add(record.slot_id)

    applied, stale = 0, 0
    with connection() as db, db.cursor() as cursor:
        for record in results:
            cursor.execute(BASE + 'AND s.slot_id=%s FOR UPDATE', (record.slot_id,))
            slot = cursor.fetchone()
            if (not slot or slot['version'] != record.version
                    or record.version != expected[record.slot_id] or not slot['topic_id']):
                stale += 1
                continue
            result = apply_result(cursor, slot, STATE[record.status], record.content_id,
                                  record.updated_at.astimezone(timezone.utc).replace(tzinfo=None),
                                  record.error, record.production_task_id)
            applied += int(result['accepted'] and not result.get('reused'))
            stale += int(result.get('stale', False))
        db.commit()
    return {'status': 'reconciled', 'applied': applied, 'stale': stale,
            'scanned': len(slots), 'next_after_id': slots[-1]['state_id']}


def reconcile_results(batch_id=None, limit=500):
    """Read all pending/failed pages; absence of a result is not production failure."""
    size = max(1, min(limit, 500))
    report = {'status': 'idle', 'applied': 0, 'stale': 0, 'scanned': 0}
    after = 0
    while True:
        page = _reconcile_page(batch_id, size, after)
        if page['status'] == 'not_configured':
            return {**report, 'status': 'not_configured'}
        for field in ('applied', 'stale', 'scanned'):
            report[field] += page.get(field, 0)
        if page['status'] == 'reconciled':
            report['status'] = 'reconciled'
        if page.get('scanned', 0) < size:
            return report
        after = page['next_after_id']


def refresh_item_status(item_id):
    """Recheck the bank's current observation before replacement; this is not a distributed lock."""
    with connection() as db, db.cursor() as cursor:
        cursor.execute(BASE + 'AND i.id=%s', (item_id,))
        observed = cursor.fetchone()
    if not observed:
        raise HTTPException(404, '策划结果不存在')
    provider = get_production(None)
    rows = provider.production_results(ProductionQuery(slot_ids=[observed['slot_id']]))
    if any(row.slot_id != observed['slot_id'] for row in rows) or len(rows) > 1:
        raise DataContractError('Java状态查询返回范围不正确')
    with connection() as db, db.cursor() as cursor:
        cursor.execute(BASE + 'AND i.id=%s FOR UPDATE', (item_id,))
        current = cursor.fetchone()
        if not current or current['version'] != observed['version']:
            raise HTTPException(409, '策划版本已变化，请重新查询')
        if rows:
            record = rows[0]
            if record.version != current['version']:
                raise HTTPException(409, '内容生产版本与当前策划不一致，请稍后重试')
            apply_result(cursor, current, STATE[record.status], record.content_id,
                         record.updated_at.astimezone(timezone.utc).replace(tzinfo=None),
                         record.error, record.production_task_id)
        db.commit()


def reconcile_marketing(limit=500):
    """Project content-side marketing demand counts; do not allocate or produce."""
    try:
        provider = get_production(None)
    except IntegrationUnavailable:
        return {'status': 'not_configured', 'applied': 0}
    if not hasattr(provider, 'marketing_results'):
        return {'status': 'not_configured', 'applied': 0}
    size, after, applied = max(1, min(limit, 500)), 0, 0
    while True:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT id,task_code FROM godp_manual_marketing_task "
                           "WHERE del_flag='N' AND status<>'已完成' AND id>%s ORDER BY id LIMIT %s", (after, size))
            demands = cursor.fetchall()
        if not demands:
            return {'status': 'reconciled' if applied else 'idle', 'applied': applied}
        expected = {row['task_code'] for row in demands}
        rows = provider.marketing_results(MarketingStatusQuery(task_codes=sorted(expected)))
        if any(row.task_code not in expected for row in rows) or len({r.task_code for r in rows}) != len(rows):
            raise DataContractError('营销生产状态返回范围或编号不正确')
        with connection() as db, db.cursor() as cursor:
            for record in rows:
                cursor.execute("SELECT * FROM godp_manual_marketing_task WHERE task_code=%s AND del_flag='N' FOR UPDATE",
                               (record.task_code,))
                current = cursor.fetchone()
                if not current or current['status'] == '已完成':
                    continue
                updated = record.updated_at.astimezone(timezone.utc).replace(tzinfo=None)
                if current['production_reported_at'] and updated <= current['production_reported_at']:
                    continue
                total = current['allocation_count'] or current['account_count'] * current['content_per_account']
                if (record.completed_count + record.failed_count > total
                        or record.completed_count < current['content_completed_count']
                        or record.status == '已完成' and (record.completed_count != total or record.failed_count)):
                    raise DataContractError('Java营销生产数量与策划需求不一致')
                cursor.execute("UPDATE godp_manual_marketing_task SET status=%s,content_completed_count=%s,"
                               "content_failed_count=%s,account_count=%s,production_reported_at=%s,"
                               "update_by='status-reader' WHERE id=%s",
                               (record.status, record.completed_count, record.failed_count, record.account_count, updated, current['id']))
                applied += 1
            db.commit()
        after = demands[-1]['id']
        if len(demands) < size:
            return {'status': 'reconciled' if applied else 'idle', 'applied': applied}
