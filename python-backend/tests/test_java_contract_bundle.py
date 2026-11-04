"""Three independent source projects; no private data or build/runtime artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from app.bank_bridge.package import build_bundle


class JavaContractBundleTests(unittest.TestCase):
    def test_bundle_contains_three_source_projects_and_host_handoff_references(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'onsite.zip'
            build_bundle(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('docs/integration/java-host/README.md', names)
                self.assertIn('docs/integration/java-host/contracts.json', names)
                self.assertFalse(any(name.startswith(('java-access/', 'backend/')) for name in names))
                self.assertIn('java-backend/pom.xml', names)
                self.assertIn('java-backend/src/main/java/com/stratmatrix/standalone/PlanningDevelopmentApplication.java', names)
                self.assertIn('python-backend/app/main.py', names)
                self.assertIn('python-backend/requirements.txt', names)
                self.assertIn('python-backend/matching_quality_schema.sql', names)
                self.assertIn('python-backend/manual_compute_schema.sql', names)
                self.assertIn('python-backend/algorithm_schema.sql', names)
                self.assertIn('python-backend/ONSITE.md', names)
                self.assertIn('java-backend/src/main/resources/mapper/ManualMapper.xml', names)
                self.assertIn('java-backend/host-integration/BankSourceBindings.java.example', names)
                self.assertIn('java-backend/src/main/resources/db/manual-business.sql', names)
                self.assertIn('docs/JAVA_MANUAL_MIGRATION.md', names)
                self.assertIn('docs/contracts/README.md', names)
                self.assertIn('frontend/package.json', names)
                java_names = {name for name in names if name.startswith('docs/integration/java-host/templates/') and name.endswith('.java.example')}
                self.assertEqual({Path(name).name for name in java_names}, {
                    'PlanningGateway.java.example', 'PendingPlanningGateway.java.example',
                    'BankDataReader.java.example', 'PendingBankDataReader.java.example', 'BankContracts.java.example',
                })
                for name in java_names:
                    code = archive.read(name).decode('utf-8')
                    for forbidden in ('static void main', 'RestTemplate', 'HttpURLConnection', '@RestController'):
                        self.assertNotIn(forbidden, code, name)
                for name in names:
                    self.assertNotIn('/target/', name)
                    self.assertFalse(name.endswith(('.class', '.env')))
                    self.assertNotIn('site_java_private', name)
                    self.assertFalse(name.startswith(('run/', 'logs/')))
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['java_implementation'], 'business_services_with_host_ports')
                self.assertTrue(manifest['java_runtime_in_project'])
                self.assertEqual(manifest['subprojects'], ['frontend', 'java-backend', 'python-backend'])
                self.assertTrue(manifest['java_requires_host_auth'])
                self.assertEqual(manifest['python_schema_entry'], 'python-backend/algorithm_schema.sql')
                self.assertNotIn('init_shared_workflow_db',archive.read('ONSITE.txt').decode('utf-8'))
                self.assertFalse(manifest['includes_credentials'])
                self.assertIn('java-backend', archive.read('ONSITE.txt').decode('utf-8'))
                for installer in ('install-offline.sh', 'install-offline.ps1'):
                    self.assertIn('python-backend/requirements.txt', archive.read(installer).decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
