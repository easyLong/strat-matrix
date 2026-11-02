"""Retired source/sync tables must not return through initialization or HTTP."""

from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from app.main import app
from app.retired_tables import RETIRED_TABLES, retired_statement
from app.init_planner_db import statements
from app.bank_bridge.local_fixture import load_fixture
from app.bank_bridge.ports import IntegrationUnavailable


class RetiredTablesTests(unittest.TestCase):
    def test_schema_has_no_retired_table_definitions(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('schema.sql', 'content_production_schema.sql', 'pipeline_schema.sql', 'manual_marketing_schema.sql'):
            for statement in statements((root / name).read_text(encoding='utf-8')):
                self.assertFalse(retired_statement(statement), name)

    def test_old_sync_and_production_entries_are_gone(self):
        client = TestClient(app)
        for path in ('/api/integrations/accounts/sync', '/api/integrations/topics/sync',
                     '/api/integrations/marketing-topics/sync', '/api/integrations/hotspot-topics/sync',
                     '/api/integrations/content-history/sync', '/api/batches/1/content-production'):
            self.assertEqual(client.post(path, json={}).status_code, 410)

    def test_fixture_is_explicit_not_an_automatic_empty_success(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(IntegrationUnavailable):
            load_fixture(Path(directory) / 'missing.json')

    def test_drop_whitelist_is_exact_and_excludes_business_results(self):
        self.assertEqual(len(RETIRED_TABLES), 14)
        for table in ('godp_planning_item', 'godp_slot_state', 'godp_topic_tag', 'godp_topic_profile',
                      'godp_account_profile', 'godp_topic_usage_fact', 'godp_system_config'):
            self.assertNotIn(table, RETIRED_TABLES)


if __name__ == '__main__':
    unittest.main()
