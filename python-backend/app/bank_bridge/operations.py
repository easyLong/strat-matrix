"""OP-01..04: bank-facing methods over planner-owned results and extensions."""

from datetime import datetime, timezone
import json

from .bridge import collect
from .contracts import TopicQuery, PlanningOutput, UsageOutput, LabelOutput, LabelTestOutput
from .factory import get_source
from .ports import DataContractError, IntegrationUnavailable


def queried_at():
    return datetime.now(timezone.utc).isoformat()


def account_planning(cursor, query):
    from ..planning_progress import PRODUCTION_STATUS_SQL, planning_status_label, production_status
    from ..services.result_scope import ResultQuery, compile_scope
    normalized=ResultQuery(mode='account',account_id=query.account_id,filters={
        'start':str(query.date_from) if query.date_from else '',
        'end':str(query.date_to) if query.date_to else ''})
    clauses,params,_,_=compile_scope(normalized)
    where="i.del_flag='N' AND b.del_flag='N' AND "+' AND '.join(clauses)
    join = 'FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id '
    cursor.execute('SELECT COUNT(*) AS total ' + join + 'WHERE ' + where, params)
    total = cursor.fetchone()['total']
    cursor.execute(
        'SELECT i.*,b.batch_code,b.plan_type,b.status AS batch_status,'
        "b.cycle_start,b.cycle_end,COALESCE((SELECT mt.task_name FROM godp_manual_task mt "
        "WHERE mt.batch_id=b.id AND mt.del_flag='N' ORDER BY mt.id DESC LIMIT 1),"
        "CONCAT(IF(b.plan_type='auto','Auto-','Manual-'),DATE_FORMAT(b.cycle_start,'%%Y%%m%%d'))) AS batch_name,"
        's.content_id,' + PRODUCTION_STATUS_SQL + ' AS production_status '
        + join + 'LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag=\'N\' WHERE ' + where
        + ' ORDER BY i.publish_date DESC,b.id DESC,i.id DESC LIMIT %s OFFSET %s',
        [*params, query.page_size, query.offset])
    rows = []
    nickname = ''
    for row in cursor.fetchall():
        nickname = nickname or row.get('account_name') or ''
        state = production_status(row)
        rows.append(dict(batch_name=row.get('batch_name') or '', batch_code=row['batch_code'],
                         plan_type=row['plan_type'], slot_type=row['slot_type'],
                         cycle_start=row['cycle_start'], cycle_end=row['cycle_end'],
                         publish_date=row['publish_date'], weekday=row['publish_date'].isoweekday() if row['publish_date'] else None,
                         planning_status=planning_status_label(row['batch_status']),
                         content_status='待定题' if not row['topic_id'] else {
                             'planned': '待生产', 'ready': '生产中', 'generated': '已完成',
                             'published': '已完成', 'failed': '生产失败'}[state],
                         topic_info={'选题ID': row['topic_id'], '选题标题': row['topic_title'],
                                     '选题大纲': row['outline'] or '', '选题二级分类': row['content_type'] or ''} if row['topic_id'] else None,
                         marketing_content_info={'内容ID': row['content_id']} if row['content_id'] and row['topic_type'] == '营销' else None,
                         updated_at=row['update_time']))
    return PlanningOutput(queried_at=queried_at(), status='success', account_id=query.account_id, nickname=nickname,
                total_count=total, page_no=query.page_no, page_size=query.page_size, planning_results=rows)


def topic_usage(cursor, query):
    placeholders = ','.join(['%s'] * len(query.topic_ids))
    cursor.execute('SELECT topic_id,topic_type,official_use_count FROM godp_topic_official_usage '
                   'WHERE del_flag=\'N\' AND topic_id IN (' + placeholders + ')', query.topic_ids)
    counts = {}
    for row in cursor.fetchall():
        if row['topic_id'] in counts:
            raise DataContractError('选题ID跨来源重复，须先明确统一ID映射')
        counts[row['topic_id']] = row['official_use_count']
    missing = [x for x in query.topic_ids if x not in counts]
    if missing:
        known = {t.topic_id for t in collect(get_source(cursor), 'topics', TopicQuery(topic_ids=missing))}
        if set(missing) - known:
            raise DataContractError('部分选题不存在，不能返回0次使用')
        counts.update({x: 0 for x in missing})
    if query.started_at or query.ended_at:
        where = 'del_flag=\'N\' AND topic_id IN (' + placeholders + ')'
        params = list(query.topic_ids)
        if query.started_at:
            where += ' AND occurred_at>=%s'
            params.append(query.started_at.astimezone(timezone.utc).replace(tzinfo=None))
        if query.ended_at:
            where += ' AND occurred_at<%s'
            params.append(query.ended_at.astimezone(timezone.utc).replace(tzinfo=None))
        cursor.execute('SELECT topic_id,COUNT(*) AS n FROM godp_topic_usage_fact WHERE ' + where + ' GROUP BY topic_id', params)
        ranged = {row['topic_id']: row['n'] for row in cursor.fetchall()}
        counts = {identity: ranged.get(identity, 0) for identity in query.topic_ids}
    return UsageOutput(queried_at=queried_at(), status='success',
                topic_results=[{'选题ID': identity, 'official_use_count': counts[identity]} for identity in query.topic_ids])


def label_paths(labels, ids, taxonomy):
    result = {}
    for dimension in ('T1', 'T2', 'T3', 'T4', 'T5'):
        values = labels.get(dimension, [])
        values = values if isinstance(values, list) else [values]
        nodes = {n['id']: n for n in taxonomy.get(dimension, [])}
        stable = ids.get(dimension, [])
        stable = stable if isinstance(stable, list) else [stable]
        paths = []
        for index, value in enumerate(values):
            if isinstance(value, dict):
                paths.append(value)
                continue
            node = nodes.get(stable[index]) if index < len(stable) else None
            if node is None:
                matches = [n for n in nodes.values() if n['name'] == value and n.get('node_type') != 'group']
                node = matches[0] if len(matches) == 1 else None
            if node is None:
                raise DataContractError('标签字典快照缺失或同名歧义，不能构造完整标签路径')
            chain, seen = [], set()
            while node is not None:
                if node['id'] in seen:
                    raise DataContractError('标签分类包含循环关联')
                seen.add(node['id'])
                chain.insert(0, {'id': node['id'], 'name': node['name']})
                parent = node.get('parent_id')
                node = nodes.get(parent) if parent else None
                if parent and node is None:
                    raise DataContractError('标签缺少父分类')
            paths.append({'id': chain[-1]['id'], 'name': chain[-1]['name'], 'path': chain})
        result[dimension] = paths
    result['T6'] = labels.get('T6', '')
    return result


def taxonomy_snapshot(cursor, version=None):
    from ..taxonomy import normalize_taxonomy
    if version is None:
        cursor.execute("SELECT version,config_json FROM godp_strategy_config WHERE config_key='tag_taxonomy' AND del_flag='N'")
    else:
        cursor.execute("SELECT version,config_json FROM godp_strategy_config_version WHERE config_key='tag_taxonomy' "
                       "AND version=%s AND del_flag='N'", (version,))
    row = cursor.fetchone()
    if not row:
        raise IntegrationUnavailable('标签字典版本尚未准备')
    return row['version'], normalize_taxonomy(json.loads(row['config_json']))


def topic_labels(cursor, query):
    cursor.execute('SELECT tags_json,tag_ids_json,label_status,taxonomy_version FROM godp_topic_tag '
                   'WHERE topic_id=%s AND del_flag=\'N\'', (query.topic_id,))
    row = cursor.fetchone()
    if not row:
        known = list(collect(get_source(cursor), 'topics', TopicQuery(topic_ids=[query.topic_id])))
        if not known:
            raise DataContractError('选题不存在')
        status, labels = '待打标', {}
    else:
        status = {'处理中': '打标中', '失败': '打标失败'}.get(row['label_status'], row['label_status'])
        labels = {}
        if status == '已完成':
            if row['taxonomy_version'] is None:
                raise DataContractError('历史标签缺少字典版本，不能按当前字典伪造历史路径')
            _, taxonomy = taxonomy_snapshot(cursor, row['taxonomy_version'])
            labels = label_paths(json.loads(row['tags_json'] or '{}'), json.loads(row['tag_ids_json'] or '{}'), taxonomy)
    return LabelOutput(queried_at=queried_at(), status='success',
                topic_result={'选题ID': query.topic_id, 'label_status': status, 'labels': labels})


def test_labels(cursor, query, labeler=None):
    from ..doubao_labeling import LabelInput, label_topic, DoubaoError
    from ..taxonomy import active_tag_names
    version, taxonomy = taxonomy_snapshot(cursor)
    result = []
    for topic in query.topics:
        try:
            output = (labeler or label_topic)(LabelInput(topic_id=topic.topic_id,
                topic={'title': topic.title, 'outline': topic.outline},
                taxonomy_version=version, taxonomy=active_tag_names(taxonomy)))
            labels = label_paths(output['labels'], {}, taxonomy)
            result.append({'选题ID': topic.topic_id, 'label_status': '已完成', 'labels': labels, 'label_error': ''})
        except (DoubaoError, DataContractError):
            result.append({'选题ID': topic.topic_id, 'label_status': '打标失败', 'labels': {}, 'label_error': '模型调用或标签结构校验失败'})
    return LabelTestOutput(tested_at=queried_at(), status='success' if any(r['label_status'] == '已完成' for r in result) else 'failed',
                topic_results=result)
