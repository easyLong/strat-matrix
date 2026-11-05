"""Persist task input boundaries and resumable preparation progress, without model calls."""
import json
from hashlib import sha256

from .account_profile import canonical_json
from .source_discovery import source_signature
from .system_config import get_setting


def versions(cursor):
    cursor.execute("SELECT version FROM godp_strategy_config WHERE config_key='tag_taxonomy' AND del_flag='N'")
    taxonomy = cursor.fetchone()
    return {'taxonomy_version': taxonomy['version'] if taxonomy else None,
            'chat_model': get_setting('MODEL_NAME').strip(),
            'embedding_model': get_setting('EMBEDDING_MODEL_NAME').strip()}


def read_scope(cursor, preparation_id):
    cursor.execute("SELECT scope_json,scope_hash,progress_json FROM godp_ai_preparation_progress WHERE del_flag='N' AND preparation_id=%s", (preparation_id,))
    row = cursor.fetchone()
    if not row:
        return None
    scope = json.loads(row['scope_json'])
    if sha256(canonical_json(scope).encode()).hexdigest() != row['scope_hash']:
        raise ValueError('任务输入范围完整性校验失败')
    return scope, json.loads(row['progress_json'])


def ensure_scope(cursor, preparation, topics):
    saved = read_scope(cursor, preparation['id'])
    if saved:
        return saved
    scope = {'schema_version': 1,
             'account_ids': sorted(a['account_id'] for a in json.loads(preparation['account_snapshot_json'])),
             'topic_sources': {t['topic_id']: source_signature(t['payload_json']) for t in topics},
             **versions(cursor)}
    encoded = canonical_json(scope)
    progress = {'phase': 'labels', 'cursors': {}, 'rounds': 0}
    cursor.execute('INSERT INTO godp_ai_preparation_progress '
                   '(preparation_id,scope_json,scope_hash,progress_json) VALUES (%s,%s,%s,%s)',
                   (preparation['id'], encoded, sha256(encoded.encode()).hexdigest(), canonical_json(progress)))
    return scope, progress


def scope_reasons(scope, topics, current_versions):
    """Never silently expand the scope or regenerate ready vectors with a new model."""
    reasons = []
    for key, title in (('taxonomy_version', '标签字典'), ('chat_model', '文本模型'),
                       ('embedding_model', '向量模型')):
        if scope[key] != current_versions[key]:
            reasons.append({'code': key + '_changed', 'message': title + '已变化，需核查或重新创建准备任务',
                            'expected': scope[key], 'actual': current_versions[key]})
    current = {t['topic_id']: t for t in topics}
    for identity, signature in scope['topic_sources'].items():
        topic = current.get(identity)
        code = ('candidate_unavailable' if topic is None else 'candidate_source_changed'
                if source_signature(topic['payload_json']) != signature else None)
        if code:
            reasons.append({'code': code, 'topic_id': identity,
                            'message': '候选选题已不可用或内容已变化，需核查任务输入'})
    if not scope['topic_sources']:
        reasons.append({'code': 'empty_candidate_scope', 'message': '任务候选选题为空，需重新准备任务'})
    return reasons


def scoped_topics(cursor, preparation, topics):
    scope, _ = ensure_scope(cursor, preparation, topics)
    reasons = scope_reasons(scope, topics, versions(cursor))
    return [t for t in topics if t['topic_id'] in scope['topic_sources']], scope, reasons


def readiness_reasons(scope, topics, checked_at, expected_space=None):
    from .matching_readiness import topic_state
    from .ai_preparation import stable_tags
    reasons = []
    for topic in topics:
        state, space = topic_state(topic, checked_at)
        if state != 'ready':
            reasons.append({'code': 'topic_' + state, 'topic_id': topic['topic_id'],
                            'message': '候选选题输入尚未就绪：' + state})
        elif space[0] != scope['embedding_model']:
            reasons.append({'code': 'topic_vector_model_mismatch', 'topic_id': topic['topic_id'],
                            'message': '选题向量模型与任务绑定模型不一致'})
        elif topic.get('taxonomy_version') != scope['taxonomy_version']:
            reasons.append({'code': 'topic_taxonomy_mismatch', 'topic_id': topic['topic_id'],
                            'message': '选题标签字典版本与任务绑定版本不一致'})
        elif expected_space and space != (expected_space['vector_model'], expected_space['dimension']):
            reasons.append({'code': 'topic_vector_space_mismatch', 'topic_id': topic['topic_id'],
                            'message': '选题向量维度或模型与本次账号不一致'})
        elif not stable_tags(topic):
            reasons.append({'code': 'topic_label_ids_incomplete', 'topic_id': topic['topic_id'],
                            'message': '候选选题缺少完整的T1至T6稳定标签ID'})
    return reasons


def save_progress(cursor, preparation_id, progress):
    cursor.execute("UPDATE godp_ai_preparation_progress SET progress_json=%s WHERE del_flag='N' AND preparation_id=%s",
                   (canonical_json(progress), preparation_id))
