"""Compare the same five local test accounts under frozen V2 and V19 inputs."""
import argparse
from copy import deepcopy
from datetime import date
import json
from pathlib import Path

from .ai_preparation import create_preparation,advance_preparation,read_preparation,cancel_preparation
from .bank_bridge.factory import source_mode
from .db import connection
from .matching_contracts import MatchingQualityOptions,PolicyCreate,PolicyConfirmation,MatchingTaskCreate
from .matching_policy import create_policy,confirm_policy,select_policy,digest
from .matching_tasks import create_task,select_task,read_evaluation,read_task_inputs,task_summary
from .matching_executor_worker import run_once
from .matching_executor_v2 import execute_job_v2
from .matching_quality import IMPLEMENTATION_KEY,QUALITY_PARAMETERS
from .matching_quality_store import read_quality_report
from .planning_input_runner import prepare_inputs
from .account_profile import canonical_json

ACCOUNTS = ['E2E-ORD10-001','E2E-ORD10-003','E2E-ORD10-004','E2E-ORD10-005','E2E-ORD10-010']


def quality_policy():
    with connection() as db,db.cursor() as cursor:
        base = json.loads(select_policy(cursor,5)['document_json'])
        cursor.execute("SELECT * FROM godp_matching_policy WHERE policy_key='v19-quality-test' ORDER BY version DESC LIMIT 1")
        latest = cursor.fetchone()
    base['implementation_key'] = IMPLEMENTATION_KEY
    base['quality'] = MatchingQualityOptions(minimum_adjacent_topic_fit=.80).model_dump(mode='json')
    for key,parameters in QUALITY_PARAMETERS.items():
        base['decisions'][key]['parameters'] = parameters
        base['decisions'][key]['definition'] = 'V19适配质量阶段：账号受限映射、现有末级主关联标签、五路召回和模型配对精判；仅验证提案。'
        base['decisions'][key]['acceptance_examples'] = ['人工OFF不能被模型覆盖，条件不成立不得使用；模型DROP不能因排期缺题而恢复。']
    payload = PolicyCreate(policy_key='v19-quality-test',expected_latest_version=latest['version'] if latest else 0,document=base)
    expected = digest(canonical_json(payload.document.model_dump()))
    if latest and latest['document_hash']==expected:
        policy_id = latest['id']
    else:
        policy_id = create_policy(payload)['policy_id']
    confirm_policy(policy_id,PolicyConfirmation(expected_hash=expected,confirmed_by='local-v19-acceptance'))
    return policy_id


def run(cycle,output,new_test_run=False):
    if source_mode() != 'local_fixture': raise ValueError('仅允许本地开发夹具验收')
    report = {'cycle_start':str(cycle),'account_ids':ACCOUNTS,'evaluation_only':True,'steps':[]}
    def step(name,**values):
        report['steps'].append({'step':name,**values})
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2),encoding='utf-8')
        print(json.dumps(report['steps'][-1],ensure_ascii=True),flush=True)
    policy_id = quality_policy()
    report['policy_id'] = policy_id
    if new_test_run:
        with connection() as db,db.cursor() as cursor:
            cursor.execute("SELECT p.id,p.version,p.selection_json,t.status,t.production_batch_id,m.policy_key "
                           'FROM godp_ai_preparation p JOIN godp_matching_task t ON t.preparation_id=p.id '
                           'JOIN godp_matching_policy m ON m.id=t.policy_id '
                           "WHERE p.cycle_start=%s AND p.reservation_key IS NOT NULL AND p.del_flag='N'", (cycle,))
            previous=cursor.fetchone()
        if previous:
            if (previous['policy_key']!='v19-quality-test' or previous['production_batch_id'] is not None
                    or previous['status'] not in ('evaluated','failed','cancelled')
                    or sorted(json.loads(previous['selection_json']))!=sorted(ACCOUNTS)):
                raise ValueError('仅可归档本验收脚本已结束且未正式提交的五账号测试准备记录')
            cancel_preparation(previous['id'],previous['version'])
            step('archive_own_test_preparation',preparation_id=previous['id'])
    state = create_preparation(cycle,ACCOUNTS,planning_scope='ordinary_only')
    report['preparation_id'] = state['preparation_id']
    for number in range(10):
        state = advance_preparation(state['preparation_id'],state['version'])
        if state['status']=='inputs_frozen': break
        progress = prepare_inputs(state['preparation_id'],max_jobs=2)
        step('base_inputs',attempt=number+1,completed=progress.get('account_vectors'),failed=progress['failed'])
        if progress['failed']:raise RuntimeError('普通输入准备失败')
        state = read_preparation(state['preparation_id'])
    if state['status']!='inputs_frozen':raise RuntimeError('输入未就绪')
    task = create_task(MatchingTaskCreate(preparation_id=state['preparation_id'],expected_preparation_version=state['version'],policy_id=policy_id))
    report['task_id'] = task['task_id']
    for number in range(30):
        failures = run_once(task_id=task['task_id'],max_jobs=1)
        with connection() as db,db.cursor() as cursor:
            saved = select_task(cursor,task['task_id'])
        quality = read_quality_report(task['task_id'])
        step('quality_turn',attempt=number+1,status=saved['status'],phase=quality['phase'] if quality else None,
             worker_turn=quality['report'].get('worker_turn') if quality else None,
             error=quality['report'].get('error_message',quality['report'].get('error_type')) if quality else None)
        if saved['status']=='evaluated':break
        if failures or saved['status'] in ('failed','invalidated','cancelled'):raise RuntimeError('V19任务未完成，详见质量报告')
    if saved['status']!='evaluated':raise RuntimeError('已保留分批进度，尚未完成')
    report['quality'] = quality['report']
    report['evaluation'] = read_evaluation(saved)
    frozen = read_task_inputs(task['task_id'])
    policy = deepcopy(frozen['policy'])
    policy['implementation_key'] = 'builtin-cosine-portfolio-v2'
    policy['quality'] = None
    legacy = {'ALG-01':{'similarity':'cosine_unit_vectors'},
              'ALG-02':{'city_gate':'allow_empty_or_exact','history_gate':'exclude_observed_account_history'},
              'ALG-03':{'top_k':100,'min_cosine':0.0},'ALG-04':{'score_scale':'positive_cosine_0_100'},
              'ALG-09':{'no_candidate':'fallback_then_failed','system_error':'task_failure'}}
    for key,value in legacy.items():policy['decisions'][key]['parameters']=value
    job = {**task_summary(saved),'lease_id':saved['lease_id'],'inputs':frozen['inputs'],'policy':policy}
    report['baseline_same_inputs'] = execute_job_v2(job).model_dump(mode='json')
    report['titles'] = {t['topic_id']:t['source_payload']['title'] for t in frozen['inputs']['topics']}
    report['account_names'] = {a['account_id']:a['snapshot']['account_name'] for a in frozen['inputs']['accounts']}
    report['status'] = 'passed'
    step('comparison_ready',positions=len(report['evaluation']['positions']),summary=report['quality']['summary'])
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--cycle',type=date.fromisoformat,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--new-test-run',action='store_true')
    args=parser.parse_args()
    run(args.cycle,args.output,args.new_test_run)
