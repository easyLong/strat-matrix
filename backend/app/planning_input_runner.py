"""Prepare pending pipeline inputs through the existing leased/validated services."""

import logging
from .db import connection
from .doubao_labeling import LabelInput, label_topic, embed_profile
from .services.labels import (TopicTagsInput, claim_topic_label_job, list_topic_label_jobs, put_topic_tags)
from .services.topic_vectors import TopicVectorResult, topic_vector_jobs, save_topic_vector
from .services.account_vectors import AccountVectorResult
from .services.preparations import preparation_account_jobs, save_preparation_account_vector
from .preparation_batches import InputBatch, BatchLimit, open_scope, inspect_scope

LOG = logging.getLogger('planning-input-runner')


def _execute_input(counts, kind, identity, operation, record_failure, progress):
    """A stale lease/input is not a model failure and must never be downgraded."""
    try:
        operation()
        counts[kind] += 1
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        concurrent_claim = getattr(exc, 'detail', None) in (
            '任务已被领取、完成或取消', '选题内容已变化，等待重新准备任务')
        if status == 404 or status == 409 and (progress['writing'] or concurrent_claim):
            counts['conflicts'] += 1
            return
        counts['failed'] += 1
        LOG.warning('Input %s %s: %s', kind, identity, type(exc).__name__)
        if len(counts['errors']) < 50:
            counts['errors'].append({'kind': kind, 'identity': identity, 'error_type': type(exc).__name__})
        try:
            record_failure(exc)
        except Exception as save_error:
            if getattr(save_error, 'status_code', None) in (404, 409):
                counts['conflicts'] += 1
            else:
                counts['failure_record_errors'] += 1
                LOG.warning('Input failure record %s %s: %s', kind, identity, type(save_error).__name__)


def retry_due(table, key, identity):
    # Names are internal constants, never user-controlled SQL identifiers.
    with connection() as db, db.cursor() as cursor:
        cursor.execute(f'SELECT status, TIMESTAMPDIFF(SECOND,update_time,CURRENT_TIMESTAMP()) age '
                       f'FROM {table} WHERE {key}=%s', (identity,))
        row = cursor.fetchone()
    return row and (row['status'] != 'failed' or row['age'] >= 60)


def prepare_inputs(preparation_id=None, *, max_jobs=24, max_seconds=30):
    if not 1 <= max_jobs <= 200 or max_seconds <= 0:
        raise ValueError('输入准备批次预算无效')
    if preparation_id is None:
        return _prepare_batch(None, None, max_jobs, max_seconds)
    # Serializes direct callers as well as the workflow worker. A process restart
    # releases this lock; results and cursors survive in the planner database.
    with connection() as db, db.cursor() as cursor:
        key = f'godp:prepare-inputs:{preparation_id}'
        cursor.execute('SELECT GET_LOCK(%s,0) acquired', (key,))
        if cursor.fetchone()['acquired'] != 1:
            return {'failed': 0, 'busy': True, 'has_more': True}
        try:
            state = open_scope(preparation_id)
            if state is None:
                return {'failed': 0, 'skipped': True, 'has_more': False}
            return _prepare_batch(preparation_id, state, max_jobs, max_seconds)
        finally:
            cursor.execute('SELECT RELEASE_LOCK(%s)', (key,))


def _prepare_batch(preparation_id, state, max_jobs, max_seconds):
    counts = {'labels': 0, 'topic_vectors': 0, 'account_vectors': 0,
              'failed': 0, 'conflicts': 0, 'deferred': 0,
              'failure_record_errors': 0, 'errors': []}
    scope, progress, waiting = state if state else (None, {'phase': 'labels', 'cursors': {}}, [])
    batch = InputBatch(preparation_id, scope, progress, max_jobs, max_seconds)
    if waiting:
        counts.update(has_more=True, waiting_reasons=waiting)
        batch.persist(counts)
        return counts
    try:
        _run_jobs(preparation_id, counts, batch)
        counts['has_more'] = bool(counts['failed'] or counts['deferred'] or counts['conflicts'])
    except BatchLimit:
        counts['has_more'] = True
        counts['budget_exhausted'] = True
    counts['checkpoint'] = {'phase': progress['phase'], 'cursors': dict(progress['cursors'])}
    if scope:
        counts['scope'] = {'preparation_id': preparation_id, 'accounts': len(scope['account_ids']),
                           'candidate_topics': len(scope['topic_sources'])}
        counts['readiness'] = inspect_scope(preparation_id, scope)
        counts['has_more'] = bool(counts['has_more'] or counts['readiness']['waiting_reasons'])
    batch.persist(counts)
    return counts


def _run_jobs(preparation_id, counts, batch):
    scoped = {'topic_ids': sorted(batch.scope['topic_sources'])} if batch.scope else {}
    after = batch.cursor('labels')
    while batch.enter('labels'):
        batch.before()
        jobs = list_topic_label_jobs(limit=100, after_id=after, **scoped)['jobs']
        if not jobs:
            batch.finish('labels', counts)
            break
        for job in jobs:
            if job['id'] <= after:
                raise ValueError('打标任务分页游标未推进')
            batch.before()
            if not retry_due('godp_topic_label_job', 'topic_id', job['topic_id']):
                counts['deferred'] += 1
                batch.checkpoint('labels', job['id'], counts)
                continue
            claim = {}
            progress = {'writing': False}

            def label():
                claim.update(claim_topic_label_job(job['topic_id']))
                result = label_topic(LabelInput(topic_id=job['topic_id'], topic=claim['topic'],
                                               taxonomy=claim['taxonomy'], taxonomy_version=claim['taxonomy_version']))
                if batch.scope and (claim['taxonomy_version'] != batch.scope['taxonomy_version']
                                    or result['t6_embedding_model'] != batch.scope['embedding_model']):
                    raise ValueError('打标结果与任务绑定版本不一致')
                progress['writing'] = True
                put_topic_tags(job['topic_id'], TopicTagsInput(
                    tags={d: [name] for d, name in result['labels'].items()}, label_status='已完成',
                    lease_id=claim['lease_id'], taxonomy_version=claim['taxonomy_version'],
                    t6_embedding=result['t6_embedding'], t6_embedding_model=result['t6_embedding_model']))

            def label_failure(exc):
                if claim:
                    put_topic_tags(job['topic_id'], TopicTagsInput(
                        tags={}, label_status='失败', label_error=f'模型准备失败：{type(exc).__name__}',
                        lease_id=claim['lease_id']))

            _execute_input(counts, 'labels', job['topic_id'], label, label_failure, progress)
            batch.checkpoint('labels', job['id'], counts)
        next_after = jobs[-1]['id']
        if next_after <= after:
            raise ValueError('打标任务分页游标未推进')
        after = next_after
    after = batch.cursor('topic_vectors')
    while batch.enter('topic_vectors'):
        batch.before()
        page = topic_vector_jobs(limit=100, after_id=after, **scoped)
        for job in page['jobs']:
            if job['id'] <= after:
                raise ValueError('选题向量任务分页游标未推进')
            batch.before()
            if not retry_due('godp_topic_profile', 'topic_id', job['topic_id']):
                counts['deferred'] += 1
                batch.checkpoint('topic_vectors', job['id'], counts)
                continue
            identity = {'content_hash': job['content_hash'], 'tag_version': job['tag_version']}
            progress = {'writing': False}

            def topic_vector():
                result = embed_profile(job['profile'])
                if batch.scope and result['vector_model'] != batch.scope['embedding_model']:
                    raise ValueError('选题向量模型与任务绑定版本不一致')
                progress['writing'] = True
                save_topic_vector(job['topic_id'], TopicVectorResult(**identity, **result))

            def topic_failure(exc):
                save_topic_vector(job['topic_id'], TopicVectorResult(
                    **identity, status='failed', error=f'向量准备失败：{type(exc).__name__}'))

            _execute_input(counts, 'topic_vectors', job['topic_id'], topic_vector, topic_failure, progress)
            batch.checkpoint('topic_vectors', job['id'], counts)
        if page['next_after_id'] <= after:
            if page['jobs']:
                raise ValueError('选题向量任务分页游标未推进')
            batch.finish('topic_vectors', counts)
            break
        after = page['next_after_id']
    if preparation_id is None:
        return
    after = batch.cursor('account_vectors')
    while batch.enter('account_vectors'):
        batch.before()
        page = preparation_account_jobs(after_id=after, limit=100, preparation_id=preparation_id)
        for job in page['jobs']:
            if job['id'] <= after:
                raise ValueError('账号向量任务分页游标未推进')
            batch.before()
            if not retry_due('godp_ai_preparation_account', 'id', job['id']):
                counts['deferred'] += 1
                batch.checkpoint('account_vectors', job['id'], counts)
                continue
            progress = {'writing': False}

            def account_vector():
                result = embed_profile(job['profile'])
                if batch.scope and result['vector_model'] != batch.scope['embedding_model']:
                    raise ValueError('账号向量模型与任务绑定版本不一致')
                progress['writing'] = True
                save_preparation_account_vector(preparation_id, job['account_id'], AccountVectorResult(
                    profile_hash=job['profile_hash'], **result))

            def account_failure(exc):
                save_preparation_account_vector(preparation_id, job['account_id'], AccountVectorResult(
                    profile_hash=job['profile_hash'], status='failed', error=f'向量准备失败：{type(exc).__name__}'))

            _execute_input(counts, 'account_vectors', job['account_id'], account_vector, account_failure, progress)
            batch.checkpoint('account_vectors', job['id'], counts)
        if page['next_after_id'] <= after:
            if page['jobs']:
                raise ValueError('账号向量任务分页游标未推进')
            batch.finish('account_vectors', counts)
            break
        after = page['next_after_id']
