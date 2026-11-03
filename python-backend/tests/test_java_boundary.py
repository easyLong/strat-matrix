"""Exercise actual HTTP/Java boundaries and production-state projection semantics."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient

from app.bank_bridge import factory
from app.bank_bridge.contracts import AccountQuery, TopicQuery, ProductionQuery, ProductionRecord, MarketingProductionRecord
from app.bank_bridge.java_http import JavaHTTPClient, JavaHTTPSource, JavaProductionStatus
from app.bank_bridge.memory import fixture_source
from app.bank_bridge.ports import DataContractError, IntegrationUnavailable
from app.core.actor import current_actor
from app.main import app
from app.services import content_status
from app.system_config import override_config


@contextmanager
def http_fixture():
    source = fixture_source()
    state = SimpleNamespace(source=source, override=None, seen=[], records=[])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def body(self):
            if self.headers.get('Transfer-Encoding') == 'chunked':
                chunks = []
                while True:
                    size = int(self.rfile.readline().strip(), 16)
                    if not size:
                        self.rfile.readline()
                        return b''.join(chunks)
                    chunks.append(self.rfile.read(size))
                    self.rfile.read(2)
            return self.rfile.read(int(self.headers.get('Content-Length', '0')))

        def do_POST(self):
            body = self.body()
            state.seen.append((self.path, dict(self.headers), body))
            if self.path.startswith('/bank/'):
                if self.headers.get('X-Integration-Token') != 'query-secret':
                    self.send_error(401)
                    return
                query = json.loads(body)
                if self.path.endswith('/accounts/query'):
                    result = state.source.accounts(AccountQuery.model_validate(query)).model_dump(mode='json', by_alias=True)
                elif self.path.endswith('/topics/query'):
                    result = state.source.topics(TopicQuery.model_validate(query)).model_dump(mode='json', by_alias=True)
                else:
                    result = [r.model_dump(mode='json', by_alias=True) for r in state.records]
            else:
                result = {'operator': self.headers.get('X-Operator-Id'),
                          'token': self.headers.get('X-Integration-Token'), 'body': body.decode('utf-8')}
            if state.override is not None:
                result = state.override
            self.reply(json.dumps(result, ensure_ascii=False).encode('utf-8'))

        def do_GET(self):
            self.reply(b'\xef\xbb\xbfID,title\r\n1,example\r\n', 'text/csv; charset=utf-8')

        def reply(self, body, kind='application/json; charset=utf-8'):
            self.send_response(200)
            self.send_header('Content-Type', kind)
            if kind.startswith('text/csv'):
                self.send_header('Content-Disposition', 'attachment; filename="results.csv"')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port), state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class JavaReadTests(unittest.TestCase):
    def test_actor_is_trusted_only_with_the_java_service_token(self):
        original = list(app.router.routes)
        app.add_api_route('/api/boundary-actor-probe', lambda: {'actor': current_actor()}, methods=['GET'])
        try:
            with override_config({'BANK_SOURCE_MODE': 'local_fixture', 'INTEGRATION_TOKEN': 'gateway-secret'}):
                client = TestClient(app)
                spoofed = client.get('/api/boundary-actor-probe', headers={'x-operator-id': 'fake-user'})
                self.assertEqual(spoofed.json()['actor'], '运营人员')
                trusted = client.get('/api/boundary-actor-probe', headers={
                    'x-operator-id': 'BANKUM001', 'x-integration-token': 'gateway-secret'})
                self.assertEqual(trusted.json()['actor'], 'BANKUM001')
        finally:
            app.router.routes[:] = original

    def test_actual_http_paging_and_body_auth(self):
        with http_fixture() as (base, state):
            source = JavaHTTPSource(JavaHTTPClient(base + '/bank', 'query-secret'))
            first = source.accounts(AccountQuery(page_size=2))
            second = source.accounts(AccountQuery(page_size=2, page_no=2))
            self.assertEqual((first.total, len(first.items), len(second.items)), (3, 2, 1))
            self.assertNotEqual(first.items[0].account_id, second.items[0].account_id)
            self.assertEqual(json.loads(state.seen[0][2])['每页条数'], 2)

    def test_bad_page_scope_and_time_window_fail_closed(self):
        with http_fixture() as (base, state):
            source = JavaHTTPSource(JavaHTTPClient(base + '/bank', 'query-secret'))
            state.override = state.source.accounts(AccountQuery()).model_dump(mode='json', by_alias=True)
            with self.assertRaises(DataContractError):
                source.accounts(AccountQuery(account_ids=['not-requested']))
            with self.assertRaises(DataContractError):
                source.accounts(AccountQuery(updated_from=datetime.now(timezone.utc) + timedelta(days=1)))
            state.override = {'items': []}
            with self.assertRaises(DataContractError):
                source.accounts(AccountQuery())

    def test_http_failure_does_not_expose_upstream_or_fall_back(self):
        with http_fixture() as (base, state):
            with self.assertRaises(IntegrationUnavailable) as error:
                JavaHTTPSource(JavaHTTPClient(base + '/bank', 'wrong-secret')).accounts(AccountQuery())
            self.assertNotIn('wrong-secret', str(error.exception))
            self.assertNotIn(base, str(error.exception))
        for mode in ('bank_sql', 'local_sql'):
            with patch.object(factory, 'SOURCE_MODE', mode), self.assertRaises(IntegrationUnavailable):
                factory.get_source(None)

    def test_production_query_rejects_unrequested_and_duplicate_results(self):
        with http_fixture() as (base, state):
            status = JavaProductionStatus(JavaHTTPClient(base + '/bank', 'query-secret'))
            row = ProductionRecord(slot_id='S1', version=1, status='生产中', updated_at=datetime.now(timezone.utc))
            state.records = [row]
            self.assertEqual(status.production_results(ProductionQuery(slot_ids=['S1']))[0].status, '生产中')
            with self.assertRaises(DataContractError):
                status.production_results(ProductionQuery(slot_ids=['S2']))
            state.records = [row, row]
            with self.assertRaises(DataContractError):
                status.production_results(ProductionQuery(slot_ids=['S1']))

    def test_endpoint_auth_and_retired_production_routes(self):
        with override_config({'BANK_SOURCE_MODE': 'java_http', 'INTEGRATION_TOKEN': 'gateway-secret'}):
            client = TestClient(app)
            self.assertEqual(client.get('/api/accounts').status_code, 401)
            self.assertEqual(client.post('/api/internal/content-scanner/claim', json={}).status_code, 410)
            self.assertEqual(client.post('/api/integrations/bank/if01/accounts/query', json={},
                                        headers={'x-integration-token': 'gateway-secret'}).status_code, 410)


class ProductionProjectionTests(unittest.TestCase):
    def marketing_projection(self, completed, total):
        active = [0]
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'id': 9, 'task_code': 'M1'}]
        cursor.fetchone.return_value = dict(id=9, status='生产中', allocation_count=total, account_count=0,
            content_per_account=0, content_completed_count=0, production_reported_at=None)
        db = MagicMock()
        db.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def connection():
            active[0] += 1
            try:
                yield db
            finally:
                active[0] -= 1

        def marketing_results(query):
            self.assertEqual(active[0], 0)
            self.assertEqual(query.task_codes, ['M1'])
            return [MarketingProductionRecord(task_code='M1', status='已完成', completed_count=completed,
                failed_count=0, account_count=2, updated_at=datetime.now(timezone.utc))]

        with patch.object(content_status, 'connection', connection), patch.object(content_status, 'get_production',
                return_value=SimpleNamespace(marketing_results=marketing_results)):
            result = content_status.reconcile_marketing()
        return result, db, cursor

    def test_marketing_counts_are_read_without_holding_a_connection(self):
        result, db, cursor = self.marketing_projection(3, 3)
        self.assertEqual(result['applied'], 1)
        db.commit.assert_called_once()
        self.assertTrue(any('content_completed_count=%s' in call.args[0] for call in cursor.execute.call_args_list))

    def test_marketing_cannot_report_more_than_the_requested_quantity(self):
        with self.assertRaises(DataContractError):
            self.marketing_projection(4, 3)

    def slot(self):
        return dict(id=1, state_id=2, slot_id='S1', version=1, production_status='planned',
                    topic_id='T1', topic_title='Topic', slot_type='regular', topic_type='普通',
                    content_id=None, production_task_id=None, production_reported_at=None)

    def test_retry_after_failure_can_complete_and_duplicate_success_never_counts_again(self):
        cursor = MagicMock()
        cursor.rowcount = 1
        slot = self.slot() | {'production_status': 'failed'}
        result = content_status.apply_result(cursor, slot, 'generated', 'C1', datetime.now(), production_task_id='P1')
        self.assertTrue(result['accepted'])
        inserts = [call for call in cursor.execute.call_args_list if 'INSERT IGNORE INTO godp_topic_usage_fact' in call.args[0]]
        self.assertEqual(len(inserts), 1)
        cursor.reset_mock()
        content_status.apply_result(cursor, slot | {'production_status': 'generated', 'content_id': 'C1'},
                                    'generated', 'C1', datetime.now())
        cursor.execute.assert_not_called()

    def test_http_is_outside_db_connections_and_version_change_is_ignored(self):
        active = [0]
        slot = self.slot()
        cursor = MagicMock()
        cursor.fetchall.return_value = [slot]
        cursor.fetchone.return_value = slot | {'version': 2}
        db = MagicMock()
        db.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def connection():
            active[0] += 1
            try:
                yield db
            finally:
                active[0] -= 1

        def status(query):
            self.assertEqual(active[0], 0, 'remote query must not hold a DB connection')
            return [ProductionRecord(slot_id='S1', version=1, status='已完成', content_id='C1',
                                     updated_at=datetime.now(timezone.utc))]

        with patch.object(content_status, 'connection', connection), \
                patch.object(content_status, 'get_production', return_value=SimpleNamespace(production_results=status)), \
                patch.object(content_status, 'apply_result') as apply:
            result = content_status._reconcile_page(None, 10, 0)
            self.assertEqual(result['stale'], 1)
            apply.assert_not_called()
            db.commit.assert_called_once()

    def test_old_timestamp_does_not_regress_status(self):
        now = datetime.now()
        cursor = MagicMock()
        result = content_status.apply_result(cursor, self.slot() | {'production_status': 'ready', 'production_reported_at': now},
                                             'failed', None, now - timedelta(seconds=1))
        self.assertTrue(result['stale'])
        cursor.execute.assert_not_called()


class HostJavaHandoffTests(unittest.TestCase):
    def test_java_is_reference_material_not_an_application_module(self):
        root = Path(__file__).resolve().parents[2]
        self.assertFalse((root / 'java-access').exists())
        reference = root / 'docs/integration/java-host'
        templates = list((reference / 'templates').glob('*.java.example'))
        self.assertEqual(len(templates), 5)
        self.assertFalse(list(reference.rglob('*.java')))
        self.assertFalse(list(reference.rglob('pom.xml')))
        for path in templates:
            code = path.read_text(encoding='utf-8')
            for forbidden in ('HttpURLConnection', 'HttpServer', 'static void main', '@RestController'):
                self.assertNotIn(forbidden, code)
        for name in ('PendingPlanningGateway', 'PendingBankDataReader'):
            self.assertIn('UnsupportedOperationException',
                          (reference / 'templates' / (name + '.java.example')).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
