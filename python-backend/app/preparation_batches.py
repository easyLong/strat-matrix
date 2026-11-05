"""Bounded input work with a durable cursor; model results remain in existing extension tables."""
from datetime import datetime, timezone
from time import monotonic

from .db import connection
from .bank_bridge.input_snapshot import frozen_java_inputs
from .matching_inputs import load_matching_topics
from .preparation_scope import ensure_scope, read_scope, scope_reasons, versions, save_progress

PHASES = ('labels', 'topic_vectors', 'account_vectors')


class BatchLimit(Exception):
    pass


class InputModelBlocked(Exception):
    def __init__(self, error_type, counts=None):
        self.error_type, self.counts = error_type, counts
        super().__init__('模型配置或访问异常，修复后显式重试')


def block_model_preparation(preparation_id, error_type):
    """Stop this preparation only; never overwrite a frozen/cancelled result."""
    import json
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT status,last_report_json FROM godp_ai_preparation "
                       "WHERE id=%s AND del_flag='N' FOR UPDATE", (preparation_id,))
        row = cursor.fetchone()
        if row and row['status'] in ('waiting_inputs', 'blocked'):
            report = json.loads(row['last_report_json']) if row['last_report_json'] else {}
            report.update(inputs_ready=False, status='blocked', blocking_reasons=[{
                'code': 'model_access_blocked', 'error_type': error_type,
                'message': '模型配置或访问异常，请检查配置、授权与账户余额，修复后显式重试'}])
            cursor.execute("UPDATE godp_ai_preparation SET status='blocked',version=version+1, last_report_json=%s,update_by='planning-input-runner', updated_by=update_by WHERE del_flag='N' AND id=%s AND reservation_key IS NOT NULL", (json.dumps(report,ensure_ascii=False),preparation_id))
        db.commit()


def open_scope(preparation_id):
    from .ai_preparation import select_preparation, today
    with connection() as db, db.cursor() as cursor:
        preparation = select_preparation(cursor, preparation_id)
        if (preparation['status'] not in ('waiting_inputs', 'blocked')
                or preparation['cycle_end'] < today() or not preparation['reservation_key']):
            return None
        saved = read_scope(cursor, preparation_id)
    identifiers = sorted(saved[0]['topic_sources']) if saved else None
    with frozen_java_inputs(topic_ids=identifiers), connection() as db, db.cursor() as cursor:
        preparation = select_preparation(cursor, preparation_id, lock=True)
        if preparation['status'] not in ('waiting_inputs', 'blocked') or not preparation['reservation_key']:
            return None
        topics = load_matching_topics(cursor, datetime.now(timezone.utc), topic_ids=identifiers)
        scope, progress = ensure_scope(cursor, preparation, topics)
        reasons = scope_reasons(scope, topics, versions(cursor))
        db.commit()
    return scope, progress, reasons


def inspect_scope(preparation_id, scope):
    from .ai_preparation import select_preparation, load_preparation_accounts
    from .account_profile import profile_from_preparation
    from .matching_readiness import evaluate_readiness
    from .preparation_scope import readiness_reasons
    now = datetime.now(timezone.utc)
    ids = sorted(scope['topic_sources'])
    with frozen_java_inputs(topic_ids=ids), connection() as db, db.cursor() as cursor:
        preparation = select_preparation(cursor, preparation_id)
        topics = load_matching_topics(cursor, now, topic_ids=ids)
        profiles = load_preparation_accounts(cursor, preparation_id)
        report = evaluate_readiness(
            {**preparation, 'batch_id': preparation_id, 'batch_code': preparation['preparation_code'],
             'batch_account_count': preparation['account_count']},
            [{**p, 'batch_id': preparation_id} for p in profiles], topics, now,
            profile_builder=profile_from_preparation)
        reasons = (scope_reasons(scope, topics, versions(cursor))
                   + readiness_reasons(scope, topics, now, report['vector_space'])
                   + report['blocking_reasons'])
    return {'accounts': report['accounts'], 'topics': report['topics'], 'waiting_reasons': reasons}


class InputBatch:
    def __init__(self, preparation_id, scope, progress, max_jobs, max_seconds):
        self.preparation_id, self.scope, self.progress = preparation_id, scope, progress
        self.max_jobs, self.max_seconds = max_jobs, max_seconds
        self.started, self.visited = monotonic(), 0
        self.progress.setdefault('cursors', {})
        self.progress.setdefault('phase', PHASES[0])

    def enter(self, phase):
        return self.progress['phase'] == phase

    def cursor(self, phase):
        return self.progress['cursors'].get(phase, 0)

    def before(self):
        # This is an admission budget, not cancellation of an in-flight model request.
        if self.visited >= self.max_jobs or monotonic() - self.started >= self.max_seconds:
            raise BatchLimit()

    def checkpoint(self, phase, cursor, counts):
        self.visited += 1
        self.progress['cursors'][phase] = cursor
        self.persist(counts)

    def finish(self, phase, counts):
        self.progress['cursors'][phase] = 0
        self.progress['phase'] = PHASES[(PHASES.index(phase) + 1) % len(PHASES)]
        if phase == PHASES[-1]:
            self.progress['rounds'] = self.progress.get('rounds', 0) + 1
        self.persist(counts)

    def persist(self, counts):
        self.progress.update(last_batch=dict(counts), updated_at=datetime.now(timezone.utc).isoformat())
        if self.preparation_id is not None:
            with connection() as db, db.cursor() as cursor:
                save_progress(cursor, self.preparation_id, self.progress)
                db.commit()
