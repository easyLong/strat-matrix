"""Run a real-model, real-MySQL single-account acceptance flow through public services.

Creates explicitly named E2E fixtures via incremental sync, never copies existing
vectors or patches preparation snapshots. Content generation uses the local mock.
"""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import time
from unittest.mock import patch

from fastapi import HTTPException

from .db import connection
from .integration import sync_accounts, sync_topics, official_topic_usage
from .integration_models import AccountSync, TopicSync, OfficialUsageQuery
from .matching_contracts import MatchingPolicyDocument, PolicyCreate, PolicyConfirmation
from .matching_policy import create_policy, confirm_policy
from .planning_pipeline import create_pipeline, read_pipeline
from .planning_workflow_worker import run_once
from .content_production import batch_flow, enqueue_batch, mock_worker_once, receive_result


ACCOUNT = 'E2E-ORD-ACCOUNT-001'


def seed_sources(start):
    now = datetime.now(timezone.utc)
    account = {
        'account_id': ACCOUNT, 'account_name': '普通策划闭环验收账号', 'um_no': 'E2EUM001',
        'account_persona': '零售银行服务顾问，面向上班族与年轻家庭，擅长工资资金安排、信用卡账单管理和家庭保障需求梳理，以清单和教程表达。',
        'persona': '家庭金融服务顾问', 'followers': 80, 'enabled': True,
        'platform': '视频号', 'organization': '测试分行', 'business_line': '零售', 'city': '深圳',
        'target_audience': ['青年人群', '有娃家庭'], 'interests': ['存款', '信用卡', '家庭规划'],
        'marketing_eligible': False, 'updated_at': now.isoformat(),
        'interaction_data': [{'content_id': f'E2E-POST-{i}', 'published_at': (now-timedelta(days=i)).isoformat(),
                              'title': f'家庭账单与储蓄安排第{i}篇', 'red_star_count': 2,
                              'favorite_count': 1, 'comment_count': 1} for i in range(1, 7)],
    }
    topics = [
        ('工资到账后，如何列出每月固定支出清单', '用日常生活案例说明工资、账单与应急储备的关系，分享可执行的收支清单，帮助读者理解资金分层。'),
        ('家庭账单整理的三个常见遗漏', '从房租、生活缴费和还款日入手，解释如何避免漏记账单，提供一张可收藏的核对清单。'),
        ('信用卡账单日和还款日有什么区别', '解释账单生成与还款时间的区别，用简单示例帮助读者理解账期和按时还款，不推介具体产品。'),
        ('工资储蓄计划怎么办理：官方服务查询与设置步骤', '面向已有储蓄需求的用户，列明开通工资储蓄计划服务前需要确认的期限、支取安排和办理条件，引导通过官方渠道预约咨询和办理，不承诺收益。'),
        ('信用卡账单提醒怎么开通：三步完成服务设置', '面向已有信用卡用户，介绍通过发卡行官方渠道开通账单提醒、确认提醒渠道和检查设置结果的操作，引导完成服务开通。'),
        ('预约家庭保障咨询前，需要准备哪些信息', '面向已有家庭保障需求的用户，整理家庭成员、已有保障、预算和责任信息，说明通过官方渠道预约需求咨询的流程与注意事项。'),
    ]
    records = [dict(topic_id=f'E2E-ORD-TOPIC-{i:03d}', title=title, outline=outline,
                    summary=outline, source='单账号普通策划闭环验收', category='家庭金融',
                    content_type='图文', topic_type='normal', is_marketing=False,
                    approval_status='approved', enabled=True, updated_at=now.isoformat(),
                    valid_from=(now-timedelta(days=1)).isoformat(),
                    valid_to=datetime.combine(start+timedelta(days=90), datetime.min.time(), timezone.utc).isoformat())
               for i, (title, outline) in enumerate(topics, 1)]
    sync_accounts(AccountSync(source_batch_id=f'E2E-ACCOUNT-{now:%Y%m%d%H%M%S}', records=[account]))
    sync_topics(TopicSync(source_batch_id=f'E2E-TOPICS-{now:%Y%m%d%H%M%S}', records=records))
    return [record['topic_id'] for record in records]


def demo_policy():
    key = 'ordinary-e2e-demo'
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT * FROM godp_matching_policy WHERE policy_key=%s ORDER BY version DESC LIMIT 1', (key,))
        latest = cursor.fetchone()
    if latest and latest['status'] == 'approved':
        return latest['id']
    path = Path(__file__).resolve().parents[2] / 'docs/examples/matching-policy-ordinary-main-v2-candidate.json'
    raw = json.loads(path.read_text(encoding='utf-8'))
    document = MatchingPolicyDocument.model_validate(raw.get('document', raw))
    policy = create_policy(PolicyCreate(policy_key=key, expected_latest_version=latest['version'] if latest else 0,
                                        document=document))
    confirm_policy(policy['policy_id'], PolicyConfirmation(expected_hash=policy['document_hash'],
                                                          confirmed_by='local-e2e-verification'))
    return policy['policy_id']


def verify(batch_id):
    flow = batch_flow(batch_id)
    tasks = flow['tasks']
    assert tasks, 'content tasks missing'
    first = tasks[0]
    rollback_verified = False
    if first['status'] == 'accepted':
        with patch('app.content_production.record_success', side_effect=RuntimeError('injected usage persistence failure')):
            try:
                receive_result(first['production_task_id'], 'completed')
                raise AssertionError('callback should roll back when usage persistence fails')
            except HTTPException as exc:
                assert exc.status_code == 503
        with connection() as db, db.cursor() as cursor:
            cursor.execute('SELECT production_status FROM godp_slot_state WHERE slot_id=%s', (first['slot_id'],))
            assert cursor.fetchone()['production_status'] == 'ready', 'callback transaction did not roll back'
            cursor.execute('SELECT COUNT(*) n FROM godp_topic_usage_fact WHERE production_task_id=%s', (first['production_task_id'],))
            assert cursor.fetchone()['n'] == 0
            # Emulate a process dying after it acquired the job. A fresh worker
            # must reclaim the expired lease, without rebuilding the request.
            cursor.execute("UPDATE godp_content_production_task SET status='processing',lease_id=%s,"
                           'lease_expires_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND) WHERE production_task_id=%s',
                           ('0'*32, first['production_task_id']))
            db.commit()
        rollback_verified = True
    mock_worker_once()
    tasks = batch_flow(batch_id)['tasks']
    assert all(t['status'] == 'completed' for t in tasks)
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM godp_topic_usage_fact WHERE production_task_id IN ('+
                       ','.join(['%s']*len(tasks))+')', [t['production_task_id'] for t in tasks])
        before = cursor.fetchone()['n']
    for task in tasks:
        receive_result(task['production_task_id'], 'completed')
        receive_result(task['production_task_id'], 'completed')
        receive_result(task['production_task_id'], 'failed')  # late failure cannot undo success
    duplicate = enqueue_batch(batch_id, 'local_mock')
    assert duplicate['accepted'] == 0 and duplicate['reused'] == len(tasks)
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM godp_topic_usage_fact WHERE production_task_id IN ('+
                       ','.join(['%s']*len(tasks))+')', [t['production_task_id'] for t in tasks])
        assert cursor.fetchone()['n'] == before == len(tasks), 'duplicate callback changed usage facts'
        cursor.execute('SELECT production_status,COUNT(*) n FROM godp_slot_state s JOIN godp_planning_item i '
                       "ON i.id=s.item_id WHERE i.batch_id=%s AND s.del_flag='N' GROUP BY production_status", (batch_id,))
        slots = cursor.fetchall()
        assert slots == [{'production_status': 'generated', 'n': len(tasks)}]
    usage = official_topic_usage(OfficialUsageQuery(topic_ids=sorted({task['topic_id'] for task in tasks})))
    expected = Counter(task['topic_id'] for task in tasks)
    assert all(row['official_use_count'] >= expected[row['topic_id']] for row in usage['topic_results'])
    return {'slot_count': len(tasks), 'usage_fact_count': before,
            'callback_rollback_and_expired_lease_recovery': rollback_verified,
            'duplicate_callback_and_submission': 'passed', 'late_failure_after_success': 'ignored',
            'usage': usage, 'tasks': [{'task_id': t['production_task_id'], 'topic_id': t['topic_id'],
                                     'status': t['status'], 'provider': t['provider']} for t in tasks]}


def main():
    parser = argparse.ArgumentParser(description='使用真实模型验收单账号普通策划及本地模拟内容闭环')
    parser.add_argument('--cycle-start', type=date.fromisoformat, required=True)
    parser.add_argument('--output', type=Path, default=Path('artifacts/ordinary-workflow-report.json'))
    args = parser.parse_args()
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT id,selection_json FROM godp_planning_pipeline_run WHERE cycle_start=%s "
                       "AND planning_scope='ordinary_only' AND status<>'cancelled' ORDER BY id DESC LIMIT 1", (args.cycle_start,))
        existing = cursor.fetchone()
    if existing:
        if json.loads(existing['selection_json']) != [ACCOUNT]:
            raise RuntimeError('cycle is reserved by another account selection')
        pipeline = read_pipeline(existing['id'])
    else:
        seed_sources(args.cycle_start)
        pipeline = create_pipeline(args.cycle_start, [ACCOUNT], demo_policy(), 'ordinary_only', 'local_mock')
    started = time.monotonic()
    while pipeline['status'] not in ('succeeded', 'failed', 'cancelled') and time.monotonic()-started < 600:
        run_once(pipeline['pipeline_id'], process_content=False)
        pipeline = read_pipeline(pipeline['pipeline_id'])
        if pipeline['status'] != 'succeeded':
            time.sleep(1)
    if pipeline['status'] != 'succeeded':
        print(json.dumps(pipeline, ensure_ascii=True, default=str, indent=2))
        return 1
    result = verify(pipeline['production_batch_id'])
    # A second reconciliation pass must reuse the same committed batch.
    run_once(pipeline['pipeline_id'])
    assert read_pipeline(pipeline['pipeline_id'])['production_batch_id'] == pipeline['production_batch_id']
    report = {'account_id': ACCOUNT, 'pipeline': pipeline, 'verification': result,
              'elapsed_seconds': round(time.monotonic()-started, 2),
              'review_path': f"/results?batch={pipeline['production_batch_id']}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    print(json.dumps({'pipeline_id': pipeline['pipeline_id'], 'batch_id': pipeline['production_batch_id'],
                      'status': pipeline['status'], 'verification': result, 'report': str(args.output)}, ensure_ascii=True, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
