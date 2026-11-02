"""Run a small explicit local-fixture V2 proposal; never commit production results."""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from .ai_preparation import create_preparation, advance_preparation, read_preparation, select_preparation
from .bank_bridge.factory import source_mode
from .db import connection
from .matching_contracts import MatchingTaskCreate
from .matching_executor_worker import run_once
from .matching_tasks import create_task, read_evaluation, select_task
from .planning_input_runner import prepare_inputs


def run(cycle, account_ids, policy_id, output):
    if source_mode() != 'local_fixture' or not 3 <= len(account_ids) <= 5 \
            or any(not identity.startswith('E2E-') for identity in account_ids):
        raise ValueError('验收仅允许本地夹具中的3至5个E2E测试账号')
    report = {'cycle_start': cycle.isoformat(), 'account_ids': account_ids, 'policy_id': policy_id,
              'production_results_committed': False, 'steps': []}

    def step(name, **values):
        report['steps'].append({'step': name, **values})
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
        print(json.dumps(report['steps'][-1], ensure_ascii=True), flush=True)

    state = create_preparation(cycle, account_ids, planning_scope='ordinary_only')
    identity = state['preparation_id']
    report['preparation_id'] = identity
    state = advance_preparation(identity, state['version'])
    for number in range(10):
        if state['status'] == 'inputs_frozen':
            break
        batch = prepare_inputs(identity, max_jobs=2, max_seconds=30)
        step('input_batch', number=number + 1,
             completed={k: batch.get(k, 0) for k in ('labels', 'topic_vectors', 'account_vectors')},
             failed=batch['failed'], has_more=batch.get('has_more'), checkpoint=batch.get('checkpoint'))
        if batch['failed'] or batch.get('waiting_reasons'):
            raise RuntimeError('测试输入准备失败或绑定版本变化，详见准备记录')
        state = read_preparation(identity)
        state = advance_preparation(identity, state['version'])
    if state['status'] != 'inputs_frozen':
        raise RuntimeError('测试输入尚未就绪，已保留断点和等待原因')
    step('inputs_frozen', candidate_topics=state['frozen_topic_count'], input_hash=state['input_hash'])
    task = create_task(MatchingTaskCreate(preparation_id=identity,
        expected_preparation_version=state['version'], policy_id=policy_id))
    report['task_id'] = task['task_id']
    if run_once(task_id=task['task_id'], max_jobs=1):
        raise RuntimeError('测试匹配执行失败')
    with connection() as db, db.cursor() as cursor:
        evaluation = read_evaluation(select_task(cursor, task['task_id']))
        preparation = select_preparation(cursor, identity)
        accounts = json.loads(preparation['account_snapshot_json'])
        cursor.execute('SELECT topic_id,snapshot_json FROM godp_ai_preparation_topic WHERE preparation_id=%s',
                       (identity,))
        topics = {t['topic_id']: json.loads(t['snapshot_json']) for t in cursor.fetchall()}
    report['accounts'] = {a['account_id']: a for a in accounts}
    report['evaluation'] = evaluation
    report['positions'] = [{**p, 'title': topics.get(p.get('topic_id'), {}).get('source_payload', {}).get('title'),
                            'explanation': (f"向量适配分 {p['fit_score']:.2f}，满足经营作用约束后由V2组合分配"
                                            if p['outcome'] == 'matched' else p['reason'])}
                           for p in evaluation['positions']]
    report['status'] = 'passed'
    step('matched', positions=len(evaluation['positions']),
         outcomes=dict(Counter(p['outcome'] for p in evaluation['positions'])))
    return report


def main():
    parser = argparse.ArgumentParser(description='按任务范围分批准备3至5个测试账号并执行V2匹配提案')
    parser.add_argument('--cycle', required=True, type=date.fromisoformat)
    parser.add_argument('--accounts', required=True, nargs='+')
    parser.add_argument('--policy', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.cycle, args.accounts, args.policy, args.output)


if __name__ == '__main__':
    main()
