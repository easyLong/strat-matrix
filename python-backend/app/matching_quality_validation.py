"""Reject results that bypass V19 gates, even if submitted directly to the task API."""
from collections import Counter
import json
import math

from fastapi import HTTPException

from .core.matching_common import city_allowed,history_by_account,role_plan,stage_targets
from .matching_quality import precision_score,history_penalty,t3_score,valid_on
from .matching_quality_model import PairJudgment
from .matching_quality_snapshot import content_hash


def validate_quality_evaluation(cursor,task,result,inputs,document):
    cursor.execute('SELECT status,lease_id,report_json,report_hash FROM godp_matching_quality_run WHERE task_id=%s', (task['id'],))
    row=cursor.fetchone()
    if not row or row['status']!='ready' or row['lease_id']!=task['lease_id']:
        raise HTTPException(409,'V19精判过程尚未完成或租约不一致')
    report=json.loads(row['report_json'])
    if report.get('evaluation_only', True) != document.quality.evaluation_only:
        raise HTTPException(409,'V19精判依据的评估用途与策略不一致')
    if (content_hash(report)!=row['report_hash'] or report.get('policy_hash')!=task['policy_hash']
            or report.get('input_hash',task['input_hash'])!=task['input_hash']
            or result.stages[2].summary.get('quality_report_hash')!=row['report_hash']):
        raise HTTPException(409,'V19精判依据与提交结果未绑定')
    topics={t['topic_id']:t for t in inputs['topics']}
    accounts={a['account_id']:a for a in inputs['accounts']}
    roles={}
    targets=stage_targets(inputs)
    for identity,account in accounts.items():
        positions=[p for p in inputs['positions'] if p['account_id']==identity]
        roles.update(role_plan(account,positions,targets[account['profile']['lifecycle_stage']]))
    historical=history_by_account(inputs['supplemental'])
    per_account,global_uses=Counter(),Counter()
    limits=document.decisions['ALG-05'].parameters
    for position in result.positions:
        if position.outcome=='failed':continue
        if position.outcome!='matched':raise HTTPException(422,'V19验证阶段不允许绕过精判兜底')
        topic_id=position.topic_id
        account=accounts[position.account_id]
        topic=topics[topic_id]
        entry=report['accounts'][position.account_id]
        approved={p['topic_id']:p for p in entry['top30']}
        if topic_id not in approved:raise HTTPException(422,'选题不在该账号精判通过的Top30中')
        item=approved[topic_id]
        annotation=report['topic_annotations'][topic_id]
        mapping=entry['mapping']
        if t3_score(mapping,annotation)[1]:raise HTTPException(422,'选题未通过账号内容边界')
        capability={n['tag_id']:n for n in mapping['features']['T3']['leaves']}
        conditional=any(capability.get(t,{}).get('relation')=='CONDITIONAL' for t in [annotation['main_t3'],*annotation['related_t3']])
        history_titles=[h['source_payload'].get('title') or '' for h in
            inputs['supplemental']['history']['observed_records'] if h['account_id']==position.account_id]
        penalty,exact=history_penalty(topic['source_payload'].get('title') or '',history_titles)
        judged=PairJudgment.model_validate(item['judgment']).model_dump()
        expected=precision_score(judged,document.quality,conditional=conditional,
            adjacent=capability[annotation['main_t3']]['relation']=='ADJACENT',repeat_penalty=penalty,exact_duplicate=exact)
        if (not expected['accepted'] or not math.isclose(position.fit_score,expected['final_precision']*100,abs_tol=1e-6)
                or position.reason != judged['reason'][:500]):
            raise HTTPException(422,'精判未通过或提交评分与精判依据不一致')
        role=topic['tags']['T2'];role=role[0] if isinstance(role,list) and len(role)==1 else role
        if (not city_allowed(account,topic) or topic_id in historical.get(position.account_id,set())
                or not valid_on(topic,position.publish_date.isoformat())
                or role!=roles[(position.account_id,position.publish_date.isoformat())] or position.content_role!=role):
            raise HTTPException(422,'选题地域、历史、日期或当前经营作用不符合约束')
        per_account[(position.account_id,topic_id)]+=1;global_uses[topic_id]+=1
        if per_account[(position.account_id,topic_id)]>limits['same_account_topic_max'] or (
                limits['global_topic_max'] is not None and global_uses[topic_id]>limits['global_topic_max']):
            raise HTTPException(422,'提交结果超出选题复用容量')
