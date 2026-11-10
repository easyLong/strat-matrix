"""The bank delivery must run with business tables alone, without view DDL or reads."""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
JAVA = ROOT / 'java-backend'
RESOURCES = JAVA / 'godp-planning-services/src/main/resources'


class ViewFreeJavaDeliveryTests(unittest.TestCase):
    def test_all_shipped_sql_and_mapper_queries_are_view_free(self):
        for path in (RESOURCES / 'db').rglob('*.sql'):
            sql = re.sub(r'--[^\n]*|/\*[\s\S]*?\*/', '', path.read_text(encoding='utf-8'))
            self.assertIsNone(re.search(r'\b(?:CREATE\s+(?:OR\s+REPLACE\s+)?|ALTER\s+|DROP\s+)VIEW\b', sql, re.I), str(path))
        for path in (RESOURCES / 'mapper').rglob('*.xml'):
            self.assertNotRegex(path.read_text(encoding='utf-8'), r'\bgodp_planning_(?:item|batch|task)_read\b')
        self.assertFalse((RESOURCES / 'db/planning-query-views.sql').exists())
        self.assertEqual(json.loads((JAVA / 'contracts/api-contract.json').read_text(encoding='utf-8'))['views'], [])

    def test_shared_mapper_fragments_resolve_within_the_delivered_xml(self):
        roots = [ET.parse(path).getroot() for path in (RESOURCES / 'mapper').rglob('*.xml')]
        fragments = {root.attrib['namespace'] + '.' + node.attrib['id'] for root in roots for node in root.findall('sql')}
        for root in roots:
            for include in root.iter('include'):
                name = include.attrib['refid']
                full = name if '.' in name else root.attrib['namespace'] + '.' + name
                self.assertIn(full, fragments)

    def test_release_is_reproducible_and_preserves_the_http_contract(self):
        for args in [
            ['tools/check_contract.py'],
            ['tools/build_db_release.py', '--output', 'godp-planning-services/src/main/resources/db/release/20261110-v10', '--check'],
        ]:
            result = subprocess.run([sys.executable, *args], cwd=JAVA, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((RESOURCES / 'db/release/20261110-v10/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['database_views'], 0)
        self.assertIn('ddl/03-upgrade-v9-to-v10.sql', manifest['files'])


if __name__ == '__main__':
    unittest.main()
