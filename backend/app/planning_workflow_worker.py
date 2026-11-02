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

LOG = logging.getLogger('planning-workflow-worker')


def run_once(pipeline_id=None, *, process_content=True):
    report = {'pipelines': [], 'mock_completed': 0}
    # Multiple application instances may run this worker. The named lock serializes
    # reconciliation; underlying services retain their own leases/version guards.
    with connection() as lock_db, lock_db.cursor() as lock_cursor:
        lock_cursor.execute("SELECT GET_LOCK('godp:planning-workflow-worker',0) acquired")
        if lock_cursor.fetchone()['acquired'] != 1:
            return {**report, 'busy': True}
        try:
            report['source_discovery'] = discover_topics()
            with connection() as db, db.cursor() as cursor:
                query = ("SELECT id FROM godp_planning_pipeline_run p WHERE del_flag='N' "
                         "AND status IN ('pending','waiting','running') ")
                args = []
                if pipeline_id is not None:
                    query += 'AND id=%s '
                    args.append(pipeline_id)
                cursor.execute(query + 'ORDER BY id LIMIT 100', args)
                identifiers = [row['id'] for row in cursor.fetchall()]
            if not identifiers:
                report['input_preparation'] = prepare_inputs()
            for identity in identifiers:
                try:
                    state = read_pipeline(identity)
                    if state['status'] != 'succeeded':
                        state = advance_pipeline_to_commit(identity, state['version'])
                        if state['preparation_id'] and state['status'] not in ('failed', 'succeeded', 'cancelled'):
                            prepare_inputs(state['preparation_id'])
                            state = advance_pipeline_to_commit(identity, state['version'])
                        if state['matching_task_id'] and state['status'] not in ('failed', 'succeeded', 'cancelled'):
                            execute_matching(task_id=state['matching_task_id'], max_jobs=1)
                            state = advance_pipeline_to_commit(identity, state['version'])
                    # Content generation is owned by the bank's table scanner.
                    report['pipelines'].append({'pipeline_id': identity, 'status': state['status'],
                                                'batch_id': state['production_batch_id']})
                except HTTPException as exc:
                    LOG.warning('Pipeline %s: HTTP %s', identity, exc.status_code)
                    report['pipelines'].append({'pipeline_id': identity, 'http_error': exc.status_code})
                except Exception as exc:
                    LOG.exception('Pipeline %s reconciliation failed: %s', identity, type(exc).__name__)
                    report['pipelines'].append({'pipeline_id': identity, 'error': type(exc).__name__})
            if process_content:
                report['production_results'] = reconcile_results()
                report['marketing_results'] = reconcile_marketing()
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
                return int(any('error' in row or 'http_error' in row or row.get('status') == 'failed'
                               for row in report['pipelines']))
        except Exception as exc:
            LOG.exception('Workflow worker: %s', type(exc).__name__)
            if args.once:
                return 1
        time.sleep(10)


if __name__ == '__main__':
    raise SystemExit(main())
