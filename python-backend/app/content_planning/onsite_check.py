"""Bounded on-site preflight: read only; no task creation, schema writes or timers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .algorithm_schema import inspect_schema
from .deployment_environment import require_ready, resolve
from .system_config import snapshot, override_config


def check(name, passed, reason='', **detail):
    return dict(name=name,status='passed' if passed else 'not_ready',reason=reason,**detail)


def configuration_checks(values):
    checks=[]
    try:
        require_ready(values)
        checks.append(check('deployment',True))
    except ValueError:
        checks.append(check('deployment',False,'检查PLANNING_ENV、Java地址、内部鉴权及模拟内容开关'))
    token=values.get('INTEGRATION_TOKEN')
    valid_token=(isinstance(token,str) and bool(token.strip()) and token==token.strip()
                 and not any(c in token for c in '\r\n\x00'))
    checks.append(check('service_authentication',valid_token,'内部接口需配置有效的INTEGRATION_TOKEN'))
    try:
        from .doubao_labeling import read_config
        with override_config(values):
            read_config()
        checks.append(check('model_configuration',True,protocol='ark',network_verified=False))
    except Exception:
        checks.append(check('model_configuration',False,'检查MODEL_BASE_URL、ARK_API_KEY及两个模型名称'))
    return checks


def algorithm_checks(cursor, values):
    from .models import StrategyConfig
    from .taxonomy import selectable_tags
    from .services.account_mapping import load_taxonomy
    from .matching_policy import intact_document, implementation_approval_errors
    checks=[]
    version,valid=None,False
    try:
        version,taxonomy=load_taxonomy(cursor)
        valid=all(selectable_tags(taxonomy.get(d,[])) for d in ('T1','T2','T3','T4','T5'))
        checks.append(check('taxonomy',bool(valid),'T1–T5均需有启用末级标签',version=version))
    except Exception:
        checks.append(check('taxonomy',False,'标签词表尚未发布或结构无效'))
    cursor.execute("SELECT config_json FROM godp_strategy_config WHERE config_key='operations' AND del_flag='N'")
    row=cursor.fetchone()
    try:
        if not row:raise ValueError()
        StrategyConfig.model_validate_json(row['config_json'])
        checks.append(check('algorithm_configuration',True))
    except (ValueError,TypeError):
        checks.append(check('algorithm_configuration',False,'算法配置尚未发布或校验未通过'))
    try:
        policy_id=int(values.get('AUTO_PLANNING_POLICY_ID') or '0')
        if policy_id<1:raise ValueError()
        cursor.execute("SELECT * FROM godp_matching_policy WHERE id=%s AND del_flag='N'",(policy_id,))
        policy=cursor.fetchone()
        if not policy or policy['status']!='approved':raise ValueError()
        document=intact_document(policy)
        if implementation_approval_errors(document) or document.quality.evaluation_only:
            raise ValueError()
        if document.vector_space.vector_model!=values.get('EMBEDDING_MODEL_NAME'):
            raise ValueError()
        checks.append(check('v19_policy',True,policy_id=policy_id,
                            dimension=document.vector_space.dimension))
        cursor.execute("SELECT COUNT(*) n FROM godp_account_mapping_rule WHERE mapping_version=%s "
                       "AND taxonomy_version=%s AND status='active' AND del_flag='N'",
                       (document.quality.mapping_version,version if valid else 0))
        count=cursor.fetchone()['n']
        # Restricted model mapping may be intentionally used with no active
        # rules, so expose the review gap without declaring it a runtime failure.
        restricted=document.quality.unknown_persona=='restricted_model'
        checks.append(dict(name='reviewed_mapping',
                           status='passed' if count else 'needs_confirmation' if restricted else 'not_ready',
                           active_rules=count,
                           reason=('无已审核规则时使用受限模型映射；上线前需确认此口径' if restricted
                                   else '无已审核规则时策略禁止模型补足，需先完成映射审核')))
    except Exception:
        checks.append(check('v19_policy',False,'需绑定完整、已批准且非评估用途的V19策略，向量模型须一致'))
    return checks


def java_probe():
    from .bank_bridge.java_http import JavaHTTPClient,JavaHTTPSource
    from .bank_bridge.contracts import AccountQuery,TopicQuery
    source=JavaHTTPSource(JavaHTTPClient.from_settings())
    accounts=source.accounts(AccountQuery(page_size=1))
    topics=source.topics(TopicQuery(page_size=1))
    return check('java_sample',bool(accounts.items and topics.items),
                 '仅检查一页账号及选题；空数据不能证明字段对接成功',
                 account_samples=len(accounts.items),topic_samples=len(topics.items))


def model_probe():
    """Only synthetic public text; no business records, labels or vectors saved."""
    from .doubao_labeling import read_config,embed_text
    from .matching_quality_model import chat
    calls=0
    try:
        cfg=read_config()
        context=dict(chat_model=cfg.chat_model,embedding_model=cfg.embedding_model)
        calls+=1
        value=chat(context,'只返回JSON对象{"ok":true}。',{'probe':'synthetic-connectivity-only'},max_tokens=32)
        if value!={'ok':True}:raise ValueError()
        calls+=1
        embedded=embed_text('技术连通性测试：不含账号、客户或选题信息',cfg)
        return check('model_sample',True,attempted_calls=calls,dimension=len(embedded['vector']),
                     vector_model=embedded['vector_model'])
    except Exception:
        return check('model_sample',False,'模型网关连通或协议校验失败；未输出上游响应或配置值',attempted_calls=calls)


def run_check(*,target=None,check_java=False,probe_models=False):
    checks=[]
    report=dict(status='not_ready',checked_at=datetime.now(timezone.utc).isoformat(),
                checks=checks,database_writes=0,model_calls=0,
                bank_acceptance=False)
    try:
        values=snapshot(force=True)
        if target:
            values={**values,'PLANNING_ENV':target}
        report['target']=resolve(values)['PLANNING_ENV']
        checks.extend(configuration_checks(values))
        from .db import connection
        with connection() as db,db.cursor() as cursor:
            schema=inspect_schema(cursor)
            checks.append(dict(name='algorithm_schema',**schema))
            if schema['status']=='passed':
                checks.extend(algorithm_checks(cursor,values))
            else:
                checks.append(dict(name='algorithm_assets',status='not_checked',reason='先补齐算法表字段及中文注释'))
        with override_config(values):
            if check_java:
                try:checks.append(java_probe())
                except Exception:checks.append(check('java_sample',False,'Java资料查询或契约校验失败'))
            if probe_models:
                model=model_probe()
                report['model_calls']=model['attempted_calls']
                checks.append(model)
                policy=next((c for c in checks if c['name']=='v19_policy' and c['status']=='passed'),None)
                if policy and model['status']=='passed':
                    checks.append(check('model_vector_space',
                        policy['dimension']==model['dimension'] and model['vector_model']==values['EMBEDDING_MODEL_NAME'],
                        '实际向量维度与模型标识须和已批准策略一致'))
        report['status']=('local_checks_passed' if checks and all(c['status']=='passed' for c in checks)
                          else 'needs_confirmation' if checks and all(c['status'] in ('passed','needs_confirmation') for c in checks)
                          else 'not_ready')
    except Exception:
        checks.append(check('preflight',False,'配置或算法库读取失败，请核对连接、权限及初始化状态'))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Python驻场只读预检；默认不调用Java或模型，不修改环境')
    parser.add_argument('--target',choices=('outside','inside'),help='只校验目标环境，不保存切换')
    parser.add_argument('--java',action='store_true',help='额外读取一页Java账号和选题，不触发任务')
    parser.add_argument('--probe-models',action='store_true',help='显式调用文本和向量模型各一次，可能产生费用')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    report=run_check(target=args.target,check_java=args.java,probe_models=args.probe_models)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report['status']=='local_checks_passed' else 2


if __name__=='__main__':raise SystemExit(main())
