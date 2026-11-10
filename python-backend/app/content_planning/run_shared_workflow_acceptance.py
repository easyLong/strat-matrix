"""Explicit real-MySQL/model acceptance with one development account and mock content."""

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import shutil
import time as clock

from fastapi.testclient import TestClient

from .db import connection
from .bank_bridge.contracts import BEIJING, Topic, UsageQuery
from .bank_bridge.factory import source_mode
from .bank_bridge.local_fixture import FIXTURE_PATH, load_fixture
from .bank_bridge.operations import topic_usage
from .ordinary_scheduler import run_due
from .planning_pipeline import read_pipeline
from .planning_workflow_worker import run_once
from .shared_production import claim_tasks, finish_task, BASE
from .system_config import snapshot, override_config

TOPIC = 'E2E-SHARED-20261030-001'


def seed_development_topic(cycle):
    if source_mode() != 'local_fixture':
        raise RuntimeError('验收种子仅允许写入显式开发夹具，禁止修改行内基础表')
    raw = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
    if any(row['data']['topic_id'] == TOPIC for row in raw['topics']):
        return
    backup = FIXTURE_PATH.parent / 'backups' / f'shared-workflow-{datetime.now():%Y%m%d%H%M%S}'
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(FIXTURE_PATH, backup / 'bank-source-fixture.before.json')
    now = datetime.now(timezone.utc)
    topic = Topic(topic_id=TOPIC, source='普通', topic_type='非营销',
        title='家庭账单整理：工资到账后的三项核对',
        outline='面向上班族和年轻家庭，整理固定账单、还款日和应急储备；用可收藏的核对清单讲解日常收支安排，不推荐具体产品。',
        content_type='金融科普', heat=20, available=True, updated_at=now,
        valid_from=now-timedelta(days=1),
        valid_to=datetime.combine(cycle+timedelta(days=90), time(), timezone.utc))
    raw['topics'].append({'data': topic.model_dump(mode='json'), 'local_payload': {}})
    temporary = FIXTURE_PATH.with_suffix('.shared.tmp')
    temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(FIXTURE_PATH)


def check_no_retired_sql():
    """Fail before execution if any service reaches a retired table."""
    import re
    from pymysql.cursors import DictCursor
    from .retired_tables import RETIRED_TABLES
    original = DictCursor.execute
    pattern = re.compile(r'\b(?:' + '|'.join(sorted(RETIRED_TABLES)) + r')\b', re.I)
    def execute(cursor, query, args=None):
        if pattern.search(query):
            raise AssertionError('验收禁止访问旧同步或投递表')
        return original(cursor, query, args)
    return execute


def run(cycle, policy_id, account_id, output):
    from unittest.mock import patch
    report = {'cycle_start': str(cycle), 'account_id': account_id, 'policy_id': policy_id,
              'source': source_mode(), 'content_provider': 'explicit_local_mock', 'steps': []}
    def step(name, **values):
        report['steps'].append({'name': name, **values})
        print(json.dumps(report['steps'][-1], ensure_ascii=True, default=str), flush=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    seed_development_topic(cycle)
    assert any(a.account_id == account_id for a in load_fixture().account_rows), '验收账号不存在'
    config = dict(snapshot())
    config.update(AUTO_PLANNING_POLICY_ID=str(policy_id), AUTO_PLANNING_ACCOUNT_IDS=json.dumps([account_id]))
    with override_config(config), patch('pymysql.cursors.DictCursor.execute', new=check_no_retired_sql()):
        # Simulate the due time for the requested future cycle through the real scheduler.
        trigger_at = datetime.combine(cycle-timedelta(days=1), time(23, 59), BEIJING)
        state = run_due(trigger_at)
        identity = state['pipeline_id']
        step('scheduler', pipeline_id=identity, status=state['status'])
        for attempt in range(12):
            result = run_once(identity, process_content=False)
            state = read_pipeline(identity)
            step('pipeline', attempt=attempt+1, status=state['status'],
                 current_stage=state['current_stage'], discovery=result.get('source_discovery'))
            if state['status'] in ('failed', 'cancelled'):
                raise AssertionError(json.dumps(state, ensure_ascii=True, default=str))
            if state['status'] == 'succeeded':
                break
            clock.sleep(1)
        assert state['status'] == 'succeeded', 'V19流程未在本轮完成'
        batch_id = state['production_batch_id']
        with connection() as db, db.cursor() as cursor:
            cursor.execute(BASE + 'AND i.batch_id=%s ORDER BY i.id', (batch_id,))
            slots = cursor.fetchall()
            assert slots and {s['account_id'] for s in slots} == {account_id}
            assert all(s['topic_id'] for s in slots)
            before = topic_usage(cursor, UsageQuery(topic_ids=sorted({s['topic_id'] for s in slots})))
        claims = claim_tasks(batch_id)
        assert not claims['errors'], claims['errors']
        assert len(claims['tasks']) == len(slots), '待生产明细未全部被内容扫描器领取'
        assert not claim_tasks(batch_id)['tasks'], '同一明细被重复领取'
        step('content_scan', batch_id=batch_id, claimed=len(claims['tasks']), duplicate_claims=0)
        for task in claims['tasks']:
            content_id = 'MOCK-' + task['production_task_id'][-24:]
            assert finish_task(task['production_task_id'], '已完成', content_id)['accepted']
            assert finish_task(task['production_task_id'], '已完成', content_id)['reused']
        with connection() as db, db.cursor() as cursor:
            cursor.execute(BASE + 'AND i.batch_id=%s ORDER BY i.id', (batch_id,))
            completed = cursor.fetchall()
            assert all(s['production_status'] == 'generated' for s in completed)
            after = topic_usage(cursor, UsageQuery(topic_ids=sorted({s['topic_id'] for s in slots})))
            delta = Counter(s['topic_id'] for s in slots)
            before_counts = {r.topic_id: r.official_use_count for r in before.topic_results}
            after_counts = {r.topic_id: r.official_use_count for r in after.topic_results}
            assert all(after_counts[k]-before_counts[k] == n for k, n in delta.items()), '重复回传造成计数不正确'
            cursor.execute('SELECT COUNT(*) n FROM godp_topic_usage_fact WHERE slot_id IN (' +
                           ','.join(['%s']*len(slots)) + ')', [s['slot_id'] for s in slots])
            assert cursor.fetchone()['n'] == len(slots)
        step('content_results', completed=len(completed), usage_delta=dict(delta), duplicate_results_counted=0)
        from .main import app
        client = TestClient(app)
        detail = client.get(f'/api/batches/{batch_id}')
        assert detail.status_code == 200, detail.text[:500]
        accounts = client.get('/api/planning-accounts')
        assert accounts.status_code == 200, accounts.text[:500]
        assert any(a['account_id'] == account_id for a in accounts.json())
        paged = client.post('/api/query/plans', json={'mode':'batch','batch_id':batch_id,'page_size':1})
        assert paged.status_code == 200, paged.text[:500]
        assert len(paged.json()['items']) == len(slots)
        assert paged.json()['summary']['accounts'] == 1
        pages = [client.post('/api/query/plans', json={'mode':'account','account_id':account_id,
                 'page_size':1,'page':page}).json() for page in (1,2)]
        assert pages[0]['summary'] == pages[1]['summary']
        assert pages[0]['distribution'] == pages[1]['distribution']
        assert not ({r['id'] for r in pages[0]['items']} & {r['id'] for r in pages[1]['items']})
        tasks = client.post('/api/query/manual-tasks', json={'page_size':2})
        assert tasks.status_code == 200 and len(tasks.json()['items']) <= 2
        step('frontend_read', batch_detail=detail.status_code, account_list=accounts.status_code,
             paged_detail=paged.status_code, task_page=tasks.status_code,
             page_stats_consistent=True, page_items_overlap=False)
        report.update(status='passed', batch_id=batch_id, pipeline_id=identity, slot_count=len(slots))
        output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key != 'steps'}, ensure_ascii=True), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description='单账号同库普通策划验收：真实模型、真实MySQL、显式模拟内容侧')
    parser.add_argument('--cycle-start', type=date.fromisoformat, required=True)
    parser.add_argument('--policy-id', type=int, required=True)
    parser.add_argument('--account-id', default='E2E-ORD-ACCOUNT-001')
    parser.add_argument('--output', type=Path, default=Path('../run/shared-workflow-report.json'))
    args = parser.parse_args()
    run(args.cycle_start, args.policy_id, args.account_id, args.output)


if __name__ == '__main__':
    main()
