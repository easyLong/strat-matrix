"""Idempotently bind the approved V19 rules and retire executable legacy policies.

No facts, frozen inputs, proposals or formal business results are deleted.
Default mode is inspection; --apply is the explicit migration operation.
"""
import argparse
import json

from .account_profile import canonical_json
from .db import connection
from .matching_contracts import MatchingPolicyDocument, PolicyCreate, PolicyConfirmation
from .matching_policy import create_policy, confirm_policy, digest, intact_document, require_v19
from .matching_quality import IMPLEMENTATION_KEY
from .system_config import clear_cache, get_setting
from .system_config_catalog import CATALOG


ACTOR = 'v19-consolidation'
POLICY_KEY = 'ordinary-v19'


def production_document(source: dict) -> MatchingPolicyDocument:
    document = intact_document(source)
    require_v19(document)
    if source['status'] != 'approved' or document.quality.mapping_mode != 'reviewed':
        raise ValueError('须使用已批准、仅包含审核映射的V19策略')
    raw = document.model_dump(mode='json', exclude_none=True)
    raw['quality']['evaluation_only'] = False
    result = MatchingPolicyDocument.model_validate(raw)
    require_v19(result)
    return result


def inspect() -> dict:
    bound = int(get_setting('AUTO_PLANNING_POLICY_ID', '0'))
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_matching_policy WHERE status='approved' AND del_flag='N' ORDER BY id DESC")
        policies = cursor.fetchall()
        sources = [row for row in policies if intact_document(row).implementation_key == IMPLEMENTATION_KEY]
        if not sources:
            raise ValueError('未找到已批准的V19策略，不能自动用旧规则冒充V19')
        source = next((row for row in sources if row['id'] == bound), sources[0])
        document = production_document(source)
        legacy_ids = [row['id'] for row in policies if intact_document(row).implementation_key != IMPLEMENTATION_KEY]
        cursor.execute("SELECT COUNT(*) AS total FROM godp_matching_task t JOIN godp_matching_policy p ON p.id=t.policy_id "
                       "WHERE t.del_flag='N' AND t.status='processing' AND t.lease_expires_at>UTC_TIMESTAMP(6) "
                       "AND JSON_UNQUOTE(JSON_EXTRACT(p.document_json,'$.implementation_key'))<>%s", (IMPLEMENTATION_KEY,))
        active = cursor.fetchone()['total']
    return dict(bound_policy_id=bound, source_policy_id=source['id'], legacy_policy_ids=legacy_ids,
                active_legacy_leases=active, document=document)


def migrate(*, apply: bool = False) -> dict:
    plan = inspect()
    document = plan.pop('document')
    if not apply:
        return {**plan, 'applied': False, 'algorithm': 'V19'}
    if plan['active_legacy_leases']:
        raise ValueError('仍有旧算法有效租约，请先停止旧服务并等待租约结束后迁移')
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_matching_policy WHERE policy_key=%s ORDER BY version DESC LIMIT 1", (POLICY_KEY,))
        latest = cursor.fetchone()
    fingerprint = digest(canonical_json(document.model_dump()))
    if latest and latest['document_hash'] == fingerprint and latest['status'] in ('draft', 'approved'):
        target = latest['id']
    else:
        target = create_policy(PolicyCreate(policy_key=POLICY_KEY,
            expected_latest_version=latest['version'] if latest else 0, document=document))['policy_id']
    confirm_policy(target, PolicyConfirmation(expected_hash=fingerprint, confirmed_by=ACTOR))
    with connection() as db, db.cursor() as cursor:
        # Serializes with task claims, which also lock their bound policy row.
        cursor.execute("SELECT id FROM godp_matching_policy WHERE del_flag='N' "
                       "AND JSON_UNQUOTE(JSON_EXTRACT(document_json,'$.implementation_key'))<>%s FOR UPDATE", (IMPLEMENTATION_KEY,))
        cursor.fetchall()
        cursor.execute("SELECT COUNT(*) AS total FROM godp_matching_task t JOIN godp_matching_policy p ON p.id=t.policy_id "
                       "WHERE t.del_flag='N' AND t.status='processing' AND t.lease_expires_at>UTC_TIMESTAMP(6) "
                       "AND JSON_UNQUOTE(JSON_EXTRACT(p.document_json,'$.implementation_key'))<>%s", (IMPLEMENTATION_KEY,))
        if cursor.fetchone()['total']:
            raise ValueError('迁移期间出现旧算法有效租约，已停止切换，请重试')
        cursor.execute("SELECT config_value FROM godp_system_config WHERE config_key='AUTO_PLANNING_POLICY_ID' "
                       "AND enabled=1 AND del_flag='N' FOR UPDATE")
        row = cursor.fetchone()
        if not row or int(row['config_value']) != plan['bound_policy_id']:
            raise ValueError('自动策划绑定已变化，请重新检查后迁移')
        cursor.execute("UPDATE godp_system_config SET config_value=%s,config_name=%s,version=version+1,update_by=%s "
                       "WHERE config_key='AUTO_PLANNING_POLICY_ID' AND config_value<>%s",
                       (str(target), CATALOG['AUTO_PLANNING_POLICY_ID'].name, ACTOR, str(target)))
        cursor.execute("UPDATE godp_matching_policy SET status='disabled',update_by=%s WHERE del_flag='N' "
                       "AND status IN ('draft','approved') AND JSON_UNQUOTE(JSON_EXTRACT(document_json,'$.implementation_key'))<>%s",
                       (ACTOR, IMPLEMENTATION_KEY))
        retired = cursor.rowcount
        # End obsolete pending work explicitly. Keep immutable result/evidence rows.
        cursor.execute("UPDATE godp_matching_task t JOIN godp_matching_policy p ON p.id=t.policy_id "
                       "SET t.status='invalidated',t.error_code='algorithm_retired',t.version=t.version+1,t.update_by=%s "
                       "WHERE t.del_flag='N' AND t.status IN ('queued','failed','processing') "
                       "AND JSON_UNQUOTE(JSON_EXTRACT(p.document_json,'$.implementation_key'))<>%s",
                       (ACTOR, IMPLEMENTATION_KEY))
        invalidated = cursor.rowcount
        db.commit()
    clear_cache()
    return {**plan, 'applied': True, 'algorithm': 'V19', 'policy_id': target,
            'retired_policies': retired, 'invalidated_tasks': invalidated}


def main():
    parser = argparse.ArgumentParser(description='仅保留V19执行入口；历史结果不删除')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(migrate(apply=args.apply), ensure_ascii=True))
    except (ValueError, RuntimeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
