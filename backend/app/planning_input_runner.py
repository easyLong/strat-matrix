"""Prepare pending pipeline inputs through the existing leased/validated services."""

import logging
from .db import connection
from .doubao_labeling import LabelInput, label_topic, embed_profile
from .integration import (TopicTagsInput, claim_topic_label_job, list_topic_label_jobs, put_topic_tags)
from .topic_vector_api import TopicVectorResult, topic_vector_jobs, save_topic_vector
from .account_vector_api import AccountVectorResult
from .ai_preparation_api import preparation_account_jobs, save_preparation_account_vector

LOG = logging.getLogger('planning-input-runner')


def retry_due(table, key, identity):
    # Names are internal constants, never user-controlled SQL identifiers.
    with connection() as db, db.cursor() as cursor:
        cursor.execute(f'SELECT status, TIMESTAMPDIFF(SECOND,update_time,CURRENT_TIMESTAMP()) age '
                       f'FROM {table} WHERE {key}=%s', (identity,))
        row = cursor.fetchone()
    return row and (row['status'] != 'failed' or row['age'] >= 60)


def prepare_inputs(preparation_id):
    counts = {'labels': 0, 'topic_vectors': 0, 'account_vectors': 0}
    after = 0
    while True:
        jobs = list_topic_label_jobs(limit=100, after_id=after)['jobs']
        if not jobs:
            break
        for job in jobs:
            if not retry_due('godp_topic_label_job', 'topic_id', job['topic_id']):
                continue
            claim = None
            try:
                claim = claim_topic_label_job(job['topic_id'])
                result = label_topic(LabelInput(topic_id=job['topic_id'], topic=claim['topic'],
                                               taxonomy=claim['taxonomy'], taxonomy_version=claim['taxonomy_version']))
                put_topic_tags(job['topic_id'], TopicTagsInput(
                    tags={d: [name] for d, name in result['labels'].items()}, label_status='已完成',
                    lease_id=claim['lease_id'], taxonomy_version=claim['taxonomy_version'],
                    t6_embedding=result['t6_embedding'], t6_embedding_model=result['t6_embedding_model']))
                counts['labels'] += 1
            except Exception as exc:
                LOG.warning('Topic label %s: %s', job['topic_id'], type(exc).__name__)
                if claim:
                    put_topic_tags(job['topic_id'], TopicTagsInput(
                        tags={}, label_status='失败', label_error=f'模型准备失败：{type(exc).__name__}',
                        lease_id=claim['lease_id']))
        after = jobs[-1]['id']
    after = 0
    while True:
        page = topic_vector_jobs(limit=100, after_id=after)
        for job in page['jobs']:
            if not retry_due('godp_topic_profile', 'topic_id', job['topic_id']):
                continue
            identity = {'content_hash': job['content_hash'], 'tag_version': job['tag_version']}
            try:
                result = embed_profile(job['profile'])
                save_topic_vector(job['topic_id'], TopicVectorResult(**identity, **result))
                counts['topic_vectors'] += 1
            except Exception as exc:
                save_topic_vector(job['topic_id'], TopicVectorResult(
                    **identity, status='failed', error=f'向量准备失败：{type(exc).__name__}'))
        if page['next_after_id'] <= after:
            break
        after = page['next_after_id']
    after = 0
    while True:
        page = preparation_account_jobs(after_id=after, limit=100, preparation_id=preparation_id)
        for job in page['jobs']:
            if not retry_due('godp_ai_preparation_account', 'id', job['id']):
                continue
            try:
                result = embed_profile(job['profile'])
                save_preparation_account_vector(preparation_id, job['account_id'], AccountVectorResult(
                    profile_hash=job['profile_hash'], **result))
                counts['account_vectors'] += 1
            except Exception as exc:
                save_preparation_account_vector(preparation_id, job['account_id'], AccountVectorResult(
                    profile_hash=job['profile_hash'], status='failed', error=f'向量准备失败：{type(exc).__name__}'))
        if page['next_after_id'] <= after:
            break
        after = page['next_after_id']
    return counts
