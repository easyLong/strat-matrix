"""Protect extracted boundaries and externally visible paging behavior."""
import ast
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pymysql

from app.bootstrap import app
from app.jobs.worker import run_once
from app.matching_contracts import ClaimTask
from app.matching_tasks import claim_task
from app.services.errors import ApplicationError
from app.services.list_queries import PageQuery, validate_dates
from app.services.plan_queries import PlanQuery, plan_page

APP = Path(__file__).resolve().parents[1] / 'app'


class DependencyTests(unittest.TestCase):
    def test_extracted_services_and_core_do_not_import_http(self):
        for folder in ('services', 'core'):
            for path in (APP / folder).glob('*.py'):
                for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module or ''
                        self.assertFalse(module.startswith('fastapi') or module.startswith('api.')
                                         or module.endswith('_api'), (path.name, module))

    def test_v2_and_input_runner_do_not_depend_on_old_entrypoints(self):
        for name, forbidden in [('matching_quality_executor.py', 'matching_executor'),
                                ('planning_input_runner.py', '_api')]:
            tree = ast.parse((APP / name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(forbidden, node.module or '')

    def test_active_services_have_no_retired_source_table_sql(self):
        import re
        from app.retired_tables import RETIRED_TABLES
        pattern = re.compile(r'\b(?:'+'|'.join(RETIRED_TABLES)+r')\b', re.I)
        for path in (APP / 'services').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(pattern.search(node.value), path.name)


class WorkerTests(unittest.TestCase):
    def test_one_job_failure_does_not_stop_other_roles(self):
        good = MagicMock(return_value={'advanced': 1})
        bad = MagicMock(side_effect=RuntimeError('temporary dependency failure'))
        with self.assertLogs('application-worker', level='ERROR'):
            result = run_once({'weekly': (60, bad), 'planning': (10, good)})
        self.assertEqual(result['weekly']['status'], 'failed')
        self.assertEqual(result['planning']['status'], 'ok')
        good.assert_called_once_with()

    def test_empty_role_selection_runs_nothing(self):
        self.assertEqual(run_once({}), {})

    def test_scoped_claim_never_takes_another_pipeline_task(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        @contextmanager
        def database():
            db = MagicMock()
            db.cursor.return_value.__enter__.return_value = cursor
            yield db
        for implementation in (None, 'builtin-tag-vector-portfolio-v2'):
            with patch('app.matching_tasks.connection', database):
                result = claim_task(ClaimTask(),
                                    implementation_key=implementation, task_id=12345)
            sql, values = cursor.execute.call_args.args
            self.assertIn('id=%s', sql)
            self.assertEqual(values[-1], 12345)
            self.assertIsNone(result['job'])


class QueryContractTests(unittest.TestCase):
    def test_page_size_is_bounded_and_unknown_request_fields_rejected(self):
        for values in ({'page': 0}, {'page_size': 201}, {'page_size': 0}, {'unexpected': True}):
            with self.assertRaises(ValidationError):
                PageQuery(**values)

    def test_invalid_dates_are_business_errors_before_querying_database(self):
        for start, end in [('2026-11-30','2026-11-01'), ('not-a-date','')]:
            with self.assertRaises(ApplicationError) as caught:
                validate_dates(start, end)
            self.assertEqual(caught.exception.status_code, 422)

    def test_detail_scope_is_mandatory(self):
        for mode in ('account', 'batch', 'cycle'):
            with self.assertRaises(ApplicationError):
                plan_page(PlanQuery(mode=mode))

    def test_http_contract_preserves_service_error_and_hides_sql_details(self):
        client = TestClient(app)
        with patch('app.services.list_queries.connection', side_effect=ApplicationError(409,'查询范围已失效')):
            response = client.post('/api/query/manual-tasks', json={})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail'], '查询范围已失效')
        with patch('app.services.list_queries.connection', side_effect=pymysql.OperationalError(2003,'private-host/password')):
            response = client.post('/api/query/manual-tasks', json={})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-host', response.text)


if __name__ == '__main__':
    unittest.main()
