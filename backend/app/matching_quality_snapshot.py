"""Freeze V19 rule/model inputs with the existing task snapshot; no model calls here."""
from hashlib import sha256
import json

from .account_profile import canonical_json
from .account_mapping import MappingRule
from .services.account_mapping import load_taxonomy
from .system_config import get_setting


def content_hash(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def quality_context(cursor, inputs, document):
    versions = {t['taxonomy_version'] for t in inputs['topics']}
    if len(versions) != 1:
        raise ValueError('V19输入必须使用同一词表版本')
    version, taxonomy = load_taxonomy(cursor, next(iter(versions)))
    options = document.quality
    cursor.execute("SELECT * FROM godp_account_mapping_rule WHERE mapping_version=%s "
                   "AND taxonomy_version=%s AND del_flag='N' ORDER BY id", (options.mapping_version, version))
    allowed = ('active','draft') if options.mapping_mode == 'draft_preview' else ('active',)
    rules = [MappingRule.model_validate(r).model_dump(mode='json') for r in cursor.fetchall() if r['status'] in allowed]
    identifiers = sorted({t['t6_tag_id'] for t in inputs['topics']})
    needs = {}
    for start in range(0, len(identifiers), 500):
        group = identifiers[start:start+500]
        cursor.execute('SELECT id,name,embedding_model,embedding_json FROM godp_t6_tag '
                       "WHERE del_flag='N' AND id IN (" + ','.join(['%s']*len(group)) + ')', group)
        for row in cursor.fetchall():
            vector = json.loads(row['embedding_json']) if row['embedding_json'] else None
            needs[str(row['id'])] = {'name': row['name'], 'model': row['embedding_model'],
                                      'vector_hash': content_hash(vector) if vector else None}
    context = {'schema_version': 1, 'taxonomy_version': version, 'taxonomy': taxonomy, 'mapping_rules': rules,
            'chat_model': get_setting('MODEL_NAME').strip(),
            'embedding_model': get_setting('EMBEDDING_MODEL_NAME').strip(),
            'topic_needs': needs, 'options': options.model_dump(mode='json',exclude_none=True)}
    if options.prompt_version == 'v19-quality-2':
        context['prompt_contracts'] = {'topic_annotation':'v19-quality-1','need_vector':'v19-quality-1',
                                       'account_mapping':'v19-quality-2','pair_precision':'v19-quality-1'}
    return context


def topic_need_vectors(context):
    """Reuse existing T6 vectors, validating the frozen signature; no base-table copies."""
    from .db import connection
    from .vector_utils import normalized_vector
    result = {}
    ids = sorted(context['topic_needs'])
    with connection() as db, db.cursor() as cursor:
        for start in range(0, len(ids), 500):
            group = ids[start:start+500]
            cursor.execute('SELECT id,embedding_model,embedding_json FROM godp_t6_tag '
                           "WHERE del_flag='N' AND id IN (" + ','.join(['%s']*len(group)) + ')', group)
            for row in cursor.fetchall():
                expected = context['topic_needs'][str(row['id'])]
                vector = json.loads(row['embedding_json']) if row['embedding_json'] else None
                if vector and row['embedding_model'] == context['embedding_model']:
                    if content_hash(vector) != expected['vector_hash']:
                        raise ValueError('T6需求向量已变化')
                    result[str(row['id'])] = normalized_vector(vector, row['embedding_model'], 'T6需求')
    return result
