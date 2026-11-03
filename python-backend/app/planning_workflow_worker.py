"""Reconcile source changes and V2 pipelines; content production stays content-owned."""

import argparse
import json
import logging
import time

from fastapi import HTTPException

from .db import connection
from .planning_pipeline import read_pipeline
from .planning_pipeline_runner import advance_pipeline_to_commit
from .planning_input_runner import prepare_inputs
from .matching_executor_worker import run_once as execute_matching
from .source_discovery import discover_topics
from .services.content_status import reconcile_results, reconcile_marketing
from .services.errors import ApplicationError

LOG = logging.getLogger('planning-workflow-worker')


def _run_phase(report, name, handler):
    """Report one phase without letting its failure suppress other phases."""
    try:
        result = handler()
        report[name] = result
        if name == 'input_preparation':
            report['failed'] += result.get('failed', 0)
        return result
    except Exception as exc:
        failure = {'phase': name, 'error_type': type(exc).__name__}
        if isinstance(exc, (HTTPException, ApplicationError)):
            failure['http_error'] = exc.status_code
        report[name] = {'status': 'failed', **failure}
        report['errors'].append(failure)
        report['failed'] += 1
        LOG.warning('Workflow phase %s: %s', name, type(exc).__name__)
        return None


def _pending_pipelines(pipeline_id):
    with connection() as db, db.cursor() as cursor:
        query = ("SELECT id FROM godp_planning_pipeline_run p WHERE del_flag='N' "
                 "AND status IN ('pending','waiting','running') ")
        args = []
        if pipeline_id is not None:
            query += 'AND id=%s '
            args.append(pipeline_id)
        cursor.execute(query + 'ORDER BY id LIMIT 100', args)
        return [row['id'] for row in cursor.fetchall()]


def _advance_pipeline(identity):
    state = read_pipeline(identity)
    inputs = None
    matching_failures = 0
    terminal = ('failed', 'succeeded', 'cancelled')
    if state['status'] not in terminal:
        state = advance_pipeline_to_commit(identity, state['version'])
        # Queued matching already has frozen inputs. Do not sweep unrelated
        # labeling/vector queues again while merely waiting for its execution.
        if state['preparation_id'] and not state['matching_task_id'] and state['status'] not in terminal:
            inputs = prepare_inputs(state['preparation_id'])
            state = advance_pipeline_to_commit(identity, state['version'])
        if state['matching_task_id'] and state['status'] not in terminal:
            matching_failures = execute_matching(task_id=state['matching_task_id'], max_jobs=1)
            state = advance_pipeline_to_commit(identity, state['version'])
    result = {'pipeline_id': identity, 'status': state['status'],
              'batch_id': state['production_batch_id']}
    if inputs is not None:
        result['input_preparation'] = inputs
    if matching_failures:
        result['matching_failures'] = matching_failures
    return result


def run_once(pipeline_id=None, *, process_content=True):
    report = {'pipelines': [], 'mock_completed': 0, 'failed': 0, 'conflicts': 0, 'errors': []}
    # Multiple application instances may run this worker. The named lock serializes
    # reconciliation; underlying services retain their own leases/version guards.
    with connection() as lock_db, lock_db.cursor() as lock_cursor:
        lock_cursor.execute("SELECT GET_LOCK('godp:planning-workflow-worker',0) acquired")
        if lock_cursor.fetchone()['acquired'] != 1:
            return {**report, 'busy': True}
        try:
            discovery = _run_phase(report, 'source_discovery', discover_topics)
            # No stale-source computation after a failed or busy discovery;
            # production status reads below remain independent.
            identifiers = []
            if discovery is not None and not discovery.get('busy'):
                identifiers = _run_phase(report, 'task_scan', lambda: _pending_pipelines(pipeline_id))
                # No active planning task means no task-scoped model work.
                # Explicit labeling/vector workers remain available separately.
            identifiers = identifiers or []
            for identity in identifiers:
                try:
                    result = _advance_pipeline(identity)
                    report['pipelines'].append(result)
                    report['failed'] += (result.get('input_preparation') or {}).get('failed', 0)
                    report['failed'] += max(result.get('matching_failures', 0), int(result['status'] == 'failed'))
                except (HTTPException, ApplicationError) as exc:
                    if exc.status_code == 409 and str(exc.detail).startswith('Pipeline版本已变化'):
                        report['conflicts'] += 1
                        report['pipelines'].append({'pipeline_id': identity, 'status': 'conflict'})
                        continue
                    LOG.warning('Pipeline %s: HTTP %s', identity, exc.status_code)
                    report['pipelines'].append({'pipeline_id': identity, 'http_error': exc.status_code})
                    report['failed'] += 1
                except Exception as exc:
                    LOG.warning('Pipeline %s reconciliation failed: %s', identity, type(exc).__name__)
                    report['pipelines'].append({'pipeline_id': identity, 'error': type(exc).__name__})
                    report['failed'] += 1
            if process_content:
                _run_phase(report, 'production_results', reconcile_results)
                _run_phase(report, 'marketing_results', reconcile_marketing)
            return report
        finally:
            lock_cursor.execute("SELECT RELEASE_LOCK('godp:planning-workflow-worker')")


def main():
    parser = argparse.ArgumentParser(description='发现选题变化并推进持久化 V2 策划流程')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--pipeline-id', type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    while True:
        try:
            report = run_once(args.pipeline_id)
            if args.once:
                print(json.dumps(report, ensure_ascii=True))
                return int(bool(report['failed']))
        except Exception as exc:
            LOG.exception('Workflow worker: %s', type(exc).__name__)
            if args.once:
                return 1
        time.sleep(10)


if __name__ == '__main__':
    raise SystemExit(main())
