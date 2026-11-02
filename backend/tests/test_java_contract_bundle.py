"""Java belongs to the host; deliver only documentation and non-buildable templates."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from app.bank_bridge.package import build_bundle


class JavaContractBundleTests(unittest.TestCase):
    def test_bundle_contains_only_host_java_handoff_references(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'onsite.zip'
            build_bundle(output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn('docs/integration/java-host/README.md', names)
                self.assertIn('docs/integration/java-host/contracts.json', names)
                self.assertFalse(any(name.startswith('java-access/') or name.endswith('.java') for name in names))
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
                    self.assertFalse(name.endswith(('.class', '.env', 'pom.xml')))
                    self.assertNotIn('site_java_private', name)
                    self.assertFalse(name.startswith(('run/', 'logs/')))
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['java_implementation'], 'host_owned_reference_only')
                self.assertFalse(manifest['java_runtime_in_project'])
                self.assertTrue(manifest['java_requires_host_auth'])
                self.assertFalse(manifest['includes_credentials'])
                self.assertIn('本项目无Java模块', archive.read('ONSITE.txt').decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
