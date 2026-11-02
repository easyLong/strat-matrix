"""Offline contracts and read-only on-site checks. Does not call models or write DB."""

import argparse
import json
from pathlib import Path

from . import contracts
from .contracts import AccountQuery, TopicQuery, MarketingQuery, EffectivePlacementQuery, ProductionQuery
from .memory import fixture_source, MemoryProduction
from .ports import DataContractError, IntegrationUnavailable


def schemas():
    names = ('AccountQuery', 'Account', 'Interaction', 'TopicQuery', 'Topic', 'MarketingQuery',
             'MarketingContent', 'EffectivePlacementQuery', 'EffectivePlacement', 'MarketingDemand',
             'DemandReceipt', 'ProductionQuery', 'ProductionRecord', 'MarketingStatusQuery', 'MarketingProductionRecord', 'AccountPlanningQuery',
             'PlanningOutput', 'UsageQuery', 'UsageOutput', 'TopicIdentity', 'LabelOutput',
             'LabelTestQuery', 'LabelTestOutput')
    return {name: getattr(contracts, name).model_json_schema(by_alias=True) for name in names}


def inspect_source(source):
    from datetime import datetime
    from .bridge import collect
    from .contracts import BEIJING
    accounts = list(collect(source, 'accounts', AccountQuery(page_size=2)))
    topics = list(collect(source, 'topics', TopicQuery(page_size=2)))
    checks = [{'capability': 'IF-01', 'status': 'passed', 'records': len(accounts)},
              {'capability': 'IF-02', 'status': 'passed', 'records': len(topics)}]
    if accounts:
        query = MarketingQuery(account_id=accounts[0].account_id, page_size=2)
        contents = source.marketing_contents(query)
        checks.append({'capability': 'IF-03', 'status': 'passed', 'total': contents.total})
        placements = source.effective_marketing(EffectivePlacementQuery(
            account_id=accounts[0].account_id, publish_date=datetime.now(BEIJING).date()))
        checks.append({'capability': 'IF-04 effective marketing', 'status': 'passed', 'records': len(placements)})
    else:
        checks.append({'capability': 'IF-03 / IF-04', 'status': 'not_exercised', 'reason': 'no eligible accounts'})
    return checks


def fixture_check():
    from .bridge import planning_accounts, planning_topics
    from .factory import use_adapters
    from ..models import StrategyConfig
    from ..account_profile import profile_from_preparation
    source = fixture_source()
    checks = inspect_source(source)

    class EmptyExtensions:
        def execute(self, *args):
            pass
        def fetchall(self):
            return []

    with use_adapters(source):
        accounts = planning_accounts(EmptyExtensions(), 'live', StrategyConfig())
        topics = planning_topics(EmptyExtensions(), 'live')
        for account in accounts:
            profile_from_preparation(account, 1, 1)
    checks.append({'capability': 'ordinary planning inputs / frozen account profiles', 'status': 'passed',
                   'accounts': len(accounts), 'topics': len(topics)})
    production = MemoryProduction()
    assert production.production_results(ProductionQuery(slot_ids=['FIXTURE-SLOT'])) == []
    checks.append({'capability': 'read-only production status', 'status': 'passed',
                   'note': 'an absent status never means production completed'})
    return checks


def main():
    parser = argparse.ArgumentParser(description='驻场契约自检；默认离线模拟，不调用模型，不写数据库')
    parser.add_argument('--provider', choices=('fixture', 'local_fixture', 'java_http'), default='fixture')
    parser.add_argument('--schemas-out', type=Path)
    parser.add_argument('--report-out', type=Path)
    args = parser.parse_args()
    try:
        if args.schemas_out:
            args.schemas_out.parent.mkdir(parents=True, exist_ok=True)
            args.schemas_out.write_text(json.dumps(schemas(), ensure_ascii=False, indent=2), encoding='utf-8')
        if args.provider == 'fixture':
            checks = fixture_check()
        else:
            from .java_http import JavaHTTPClient, JavaHTTPSource
            from .local_fixture import load_fixture
            source = JavaHTTPSource(JavaHTTPClient.from_settings()) if args.provider == 'java_http' else load_fixture()
            checks = inspect_source(source)
        complete = all(check['status'] == 'passed' for check in checks)
        report = {'provider': args.provider, 'status': 'passed' if complete else 'partial', 'checks': checks,
                  'writes': 0, 'model_calls': 0, 'schema_count': len(schemas())}
        code = 0 if complete else 2
    except (IntegrationUnavailable, DataContractError) as exc:
        report = {'provider': args.provider, 'status': 'not_ready', 'reason': str(exc)}
        code = 2
    except Exception:
        # Never print DB exceptions that might contain private SQL or source values.
        report = {'provider': args.provider, 'status': 'failed', 'reason': '查询或字段校验失败，请在行内核对实现'}
        code = 2
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
