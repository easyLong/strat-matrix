"""Cheap necessary conditions before V19 model calls, using frozen inputs only."""
from .core.matching_common import ExecutorInputError,role_plan,stage_targets
from .matching_quality import valid_on


class InsufficientRoleCoverage(ExecutorInputError):
    pass


def role_coverage(inputs):
    targets=stage_targets(inputs)
    deficits=[]
    topics=inputs['topics']
    for account in inputs['accounts']:
        positions=[p for p in inputs['positions'] if p['account_id']==account['account_id']]
        roles=role_plan(account,positions,targets[account['profile']['lifecycle_stage']])
        for position in positions:
            role=roles[(account['account_id'],position['publish_date'])]
            def matches(topic):
                value=topic['tags'].get('T2',topic['tags'].get('t2'))
                if isinstance(value,list) and len(value)==1:value=value[0]
                return value==role and valid_on(topic,position['publish_date'])
            if not any(matches(t) for t in topics):
                deficits.append(dict(account_id=account['account_id'],publish_date=position['publish_date'],
                                     required_role=role,candidate_count=0))
    return dict(status='blocked' if deficits else 'passed',deficits=deficits)
