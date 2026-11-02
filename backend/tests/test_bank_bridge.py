"""Bank contracts must be usable without bank schemas, database writes or models."""

from contextlib import contextmanager, ExitStack
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pymysql

from app.bank_bridge import api, factory, operations
from app.bank_bridge.bank_sql import BankSQLSource
from app.bank_bridge.bridge import collect, planning_accounts
from app.bank_bridge.contracts import (AccountQuery, TopicQuery, MarketingQuery, AccountPlanningQuery,
    EffectivePlacementQuery, Page, Account, UsageQuery, TopicIdentity, LabelTestQuery, MarketingDemand)
from app.bank_bridge.memory import fixture_source, MemorySource, MemoryProduction
from app.bank_bridge.ports import DataContractError, IntegrationUnavailable
from app.bank_bridge.selfcheck import fixture_check
from app.models import StrategyConfig, AccountOption, TopicOption
from app.system_config import override_config
from app.main import app, list_accounts, list_topics, available_topics, topic_detail
from app.ordinary_planning import load_accounts, load_topics
from app.matching_inputs import load_matching_topics


class Cursor:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.calls = []
        self.current = []
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self.current = next((value for key, value in self.rows.items() if key in sql), [])
    def fetchall(self):
        return self.current
    def fetchone(self):
        return self.current[0] if self.current else None


@contextmanager
def database(cursor):
    db = Mock()
    db.cursor.return_value.__enter__ = Mock(return_value=cursor)
    db.cursor.return_value.__exit__ = Mock(return_value=False)
    with ExitStack() as stack:
        for module in ('catalog', 'configuration'):
            connect = stack.enter_context(patch(f'app.services.{module}.connection'))
            connect.return_value.__enter__.return_value = db
        connect = stack.enter_context(patch.object(api, 'connection'))
        connect.return_value.__enter__.return_value = db
        yield db


class ContractTests(unittest.TestCase):
    def test_chinese_entities_and_unknown_vs_zero(self):
        account = fixture_source().account_rows[0].model_copy(update={'followers': None})
        account._local_payload = {'private_test': 'not exported'}
        output = account.model_dump(by_alias=True)
        self.assertIsNone(output['粉丝量'])
        self.assertNotIn('_local_payload', output)
        self.assertNotIn('private_test', str(output))
        self.assertNotIn('业务线', output)
        self.assertNotIn('地域', output)
        self.assertEqual(Account.model_validate(output).account_id, account.account_id)

    def test_update_times_are_beijing_half_open(self):
        account = fixture_source().account_rows[0]
        instant = account.updated_at
        source = MemorySource(accounts=[account])
        self.assertEqual(source.accounts(AccountQuery(updated_from=instant)).total, 1)
        self.assertEqual(source.accounts(AccountQuery(updated_to=instant)).total, 0)
        query = AccountQuery(updated_from=datetime(2026, 10, 1))
        self.assertEqual(query.updated_from.utcoffset(), timedelta(hours=8))
        with self.assertRaises(ValidationError):
            AccountQuery(updated_from=instant, updated_to=instant)

    def test_unavailable_accounts_are_excluded_from_total(self):
        source = fixture_source()
        source.account_rows[1].eligible = False
        page = source.accounts(AccountQuery(page_size=1))
        self.assertEqual((page.total, len(page.items)), (2, 1))
        self.assertEqual(source.accounts(AccountQuery(page_no=3, page_size=1)).items, [])

    def test_parent_pagination_and_ids(self):
        source = fixture_source()
        rows = list(collect(source, 'accounts', AccountQuery(page_size=2)))
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r.account_id for r in rows}), 3)
        self.assertEqual(source.accounts(AccountQuery(account_ids=[])).total, 0)

    def test_page_rejects_wrong_counts_and_duplicates(self):
        account = fixture_source().account_rows[0]
        with self.assertRaises(ValidationError):
            Page[Account](total=2, page_no=1, page_size=2, items=[account])
        with self.assertRaises(ValidationError):
            Page[Account](total=2, page_no=1, page_size=2, items=[account, account])

    def test_collector_rejects_changed_total(self):
        rows = fixture_source().account_rows
        source = Mock()
        source.accounts.side_effect = [Page[Account](total=3, page_no=1, page_size=2, items=rows[:2]),
                                       Page[Account](total=4, page_no=2, page_size=2, items=rows[1:])]
        with self.assertRaises(DataContractError):
            list(collect(source, 'accounts', AccountQuery(page_size=2)))

    def test_collector_rejects_repeated_cross_page_ids(self):
        rows = fixture_source().account_rows
        source = Mock()
        source.accounts.side_effect = [Page[Account](total=3, page_no=1, page_size=2, items=rows[:2]),
                                       Page[Account](total=3, page_no=2, page_size=2, items=[rows[0]])]
        with self.assertRaises(DataContractError):
            list(collect(source, 'accounts', AccountQuery(page_size=2)))

    def test_topic_source_type_and_validity_are_distinct(self):
        source = fixture_source()
        self.assertEqual(source.topics(TopicQuery(source='热点')).total, 1)
        self.assertEqual(source.topics(TopicQuery(topic_type='营销')).total, 1)
        source.topic_rows[0].valid_to = datetime.now(timezone.utc) - timedelta(days=1)
        self.assertEqual(source.topics(TopicQuery(available_only=True, valid_at=datetime.now(timezone.utc))).total, 2)

    def test_production_acceptance_does_not_fabricate_completion(self):
        production = MemoryProduction()
        demand = MarketingDemand(request_id='R', task_code='M', topic=fixture_source().topic_rows[0], quantity=12)
        self.assertTrue(production.submit_marketing(demand).accepted)
        production.submit_marketing(demand)
        self.assertEqual(len(production.requests), 1)
        self.assertEqual(production.results, [])
        with self.assertRaises(DataContractError):
            production.submit_marketing(demand.model_copy(update={'quantity': 13}))


class SQLAdapterTests(unittest.TestCase):
    def site(self):
        return SimpleNamespace(ACCOUNT_COUNT='COUNT', ACCOUNT_ROWS='ROWS {{account_ids}}', ACCOUNT_POSTS='POSTS {{account_ids}}',
                               map_account=lambda r: r, map_interaction=lambda r: r)

    def test_unfilled_sql_is_not_empty_success(self):
        site = self.site()
        site.ACCOUNT_COUNT = None
        with self.assertRaises(IntegrationUnavailable):
            BankSQLSource(Cursor(), site).accounts(AccountQuery())

    def test_ids_are_bound_and_posts_are_batched(self):
        account = fixture_source().account_rows[0]
        identity = "A' OR 1=1 --"
        account.account_id = identity
        cursor = Cursor({'COUNT': [{'总数': 1}], 'ROWS': [account.model_dump()], 'POSTS': []})
        result = BankSQLSource(cursor, self.site()).accounts(AccountQuery(account_ids=[identity]))
        self.assertEqual(result.total, 1)
        self.assertEqual(len(cursor.calls), 3)
        for sql, params in cursor.calls:
            self.assertNotIn(identity, sql)
        self.assertIn(identity, cursor.calls[1][1].values())

    def test_invalid_fields_and_unfiltered_accounts_fail(self):
        account = fixture_source().account_rows[0]
        account.eligible = False
        cursor = Cursor({'COUNT': [{'total': 1}], 'ROWS': [account.model_dump()], 'POSTS': []})
        with self.assertRaises(DataContractError):
            BankSQLSource(cursor, self.site()).accounts(AccountQuery())
        cursor.rows['ROWS'] = [{'account_id': 'A'}]
        with self.assertRaises(DataContractError):
            BankSQLSource(cursor, self.site()).accounts(AccountQuery())

    def test_unknown_provider_does_not_fall_back(self):
        with patch.object(factory, 'SOURCE_MODE', 'unknown'), self.assertRaises(IntegrationUnavailable):
            factory.get_source(Cursor())


class ExistingReadPathTests(unittest.TestCase):
    def test_account_topic_pages_and_ordinary_inputs_use_same_source(self):
        source = fixture_source()
        cursor = Cursor()
        with factory.use_adapters(source), database(cursor):
            accounts = list_accounts(limit=10)
            topics = list_topics(limit=10)
            for row in accounts:
                AccountOption(**row)
            for row in topics:
                TopicOption(**row)
            self.assertEqual(len(accounts), 3)
            self.assertEqual(len(topics), 3)
            self.assertEqual(topic_detail('FIXTURE-T001')['topic_id'], 'FIXTURE-T001')
            self.assertEqual(len(available_topics(cursor, ['FIXTURE-T001'])), 1)
            self.assertEqual(len(load_accounts(cursor, 'live', StrategyConfig())), 3)
            self.assertEqual(len(load_topics(cursor, 'live')), 1)
            self.assertEqual(len(load_matching_topics(cursor, datetime.now(timezone.utc))), 1)
        for sql, _ in cursor.calls:
            self.assertNotIn('godp_account_source', sql)
            self.assertNotIn('godp_topic_source', sql)

    def test_unknown_follower_count_blocks_algorithm(self):
        source = fixture_source()
        source.account_rows[0].followers = None
        with factory.use_adapters(source), self.assertRaises(DataContractError):
            planning_accounts(Cursor(), 'live', StrategyConfig())

    def test_offline_smoke_has_no_model_or_database_dependencies(self):
        with patch('app.db.connection', side_effect=AssertionError('no DB')):
            self.assertTrue(all(c['status'] == 'passed' for c in fixture_check()))


class OperationsTests(unittest.TestCase):
    def test_unknown_usage_is_not_silently_zero(self):
        with factory.use_adapters(fixture_source()), self.assertRaises(DataContractError):
            operations.topic_usage(Cursor(), UsageQuery(topic_ids=['missing']))

    def test_known_unused_topics_return_zero_in_input_order(self):
        with factory.use_adapters(fixture_source()):
            result = operations.topic_usage(Cursor(), UsageQuery(topic_ids=['FIXTURE-T002', 'FIXTURE-T001']))
        self.assertEqual([r.topic_id for r in result.topic_results], ['FIXTURE-T002', 'FIXTURE-T001'])
        self.assertEqual([r.official_use_count for r in result.topic_results], [0, 0])

    def test_usage_time_range_binds_utc_and_does_not_write(self):
        cursor = Cursor({'godp_topic_official_usage': [{'topic_id': 'T', 'topic_type': '普通', 'official_use_count': 4}],
                         'godp_topic_usage_fact': [{'topic_id': 'T', 'n': 2}]})
        start = datetime(2026, 10, 1)
        result = operations.topic_usage(cursor, UsageQuery(topic_ids=['T'], started_at=start))
        self.assertEqual(result.topic_results[0].official_use_count, 2)
        self.assertEqual(cursor.calls[-1][1][-1], datetime(2026, 9, 30, 16))
        self.assertTrue(all(sql.startswith('SELECT') for sql, _ in cursor.calls))

    def test_no_plans_is_empty_page_and_date_range_is_validated(self):
        result = operations.account_planning(Cursor({'COUNT(*)': [{'total': 0}]}), AccountPlanningQuery(account_id='A'))
        self.assertEqual((result.total_count, result.planning_results), (0, []))
        with self.assertRaises(ValidationError):
            AccountPlanningQuery(account_id='A', date_from=date(2026, 10, 2), date_to=date(2026, 10, 1))

    def test_pending_label_is_success_not_completed(self):
        with factory.use_adapters(fixture_source()):
            result = operations.topic_labels(Cursor(), TopicIdentity(topic_id='FIXTURE-T001'))
        self.assertEqual(result.topic_result.label_status, '待打标')
        self.assertEqual(result.topic_result.labels, {})

    def test_full_label_path_and_ambiguous_name(self):
        tree = {'T3': [{'id': 'group', 'name': '金融', 'node_type': 'group'},
                       {'id': 'leaf', 'name': '理财', 'parent_id': 'group'}]}
        result = operations.label_paths({'T3': ['理财']}, {'T3': 'leaf'}, tree)
        self.assertEqual([n['id'] for n in result['T3'][0]['path']], ['group', 'leaf'])
        with self.assertRaises(DataContractError):
            operations.label_paths({'T3': ['未定义']}, {}, tree)

    def test_test_labels_is_read_only_and_preserves_per_topic_errors(self):
        from app.doubao_labeling import DoubaoUnavailable
        tree = {f'T{i}': [{'id': f'T{i}-1', 'name': f'L{i}', 'enabled': True}] for i in range(1, 6)}
        cursor = Cursor({'godp_strategy_config': [{'version': 1, 'config_json': __import__('json').dumps(tree)}]})
        labeler = Mock(side_effect=[{'labels': {**{f'T{i}': f'L{i}' for i in range(1, 6)}, 'T6': '需求'}}, DoubaoUnavailable('unavailable')])
        query = LabelTestQuery(topics=[{'topic_id': f'T{i}', 'title': '标题', 'outline': '大纲'} for i in range(2)])
        result = operations.test_labels(cursor, query, labeler)
        self.assertEqual([r.label_status for r in result.topic_results], ['已完成', '打标失败'])
        self.assertTrue(all(sql.startswith('SELECT') for sql, _ in cursor.calls))


class HTTPTests(unittest.TestCase):
    def test_auth_and_chinese_dto_match_direct_method(self):
        source = fixture_source()
        with override_config({'INTEGRATION_TOKEN': 'bridge-test'}), factory.use_adapters(source), database(Cursor()):
            client = TestClient(app)
            url = '/api/integrations/bank/if01/accounts/query'
            self.assertEqual(client.post(url, json={}).status_code, 401)
            response = client.post(url, headers={'x-integration-token': 'bridge-test'}, json={'页码': 1, '每页条数': 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), source.accounts(AccountQuery(page_size=2)).model_dump(mode='json', by_alias=True))

    def test_missing_mapping_and_sql_errors_do_not_expose_bank_schema(self):
        broken = Mock()
        for error, code in [(IntegrationUnavailable('not implemented'), 503),
                            (DataContractError('private fields'), 502),
                            (pymysql.ProgrammingError('PRIVATE_BANK_TABLE'), 503)]:
            broken.accounts.side_effect = error
            with override_config({'INTEGRATION_TOKEN': 'bridge-test'}), factory.use_adapters(broken), database(Cursor()):
                response = TestClient(app).post('/api/integrations/bank/if01/accounts/query', json={},
                                              headers={'x-integration-token': 'bridge-test'})
                self.assertEqual(response.status_code, code)
                self.assertNotIn('PRIVATE_BANK_TABLE', response.text)


if __name__ == '__main__':
    unittest.main()
