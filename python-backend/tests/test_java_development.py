from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.java_development import local_java_address, properties_text, write_local_configuration
from app.system_config import override_config


class JavaDevelopmentTests(unittest.TestCase):
    def test_local_launcher_rejects_remote_host_and_credentials(self):
        self.assertEqual(local_java_address(""), ("127.0.0.1", 6931))
        self.assertEqual(local_java_address("http://[::1]:16931"), ("::1", 16931))
        for value in ("https://localhost", "http://remote.example:6931", "http://u:p@localhost", "http://localhost/api", "http://localhost:0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_java_address(value)

    def test_generated_configuration_preserves_secret_characters_without_exporting_other_keys(self):
        with patch('app.java_development.java_database_settings', return_value={
            'host':'localhost','port':3306,'database':'business_test','user':'test','password':'test-pass'
        }), patch('pymysql.connect') as connect, TemporaryDirectory() as directory, override_config({
            "JAVA_ACCESS_MODE": "local_development", "JAVA_GATEWAY_URL": "http://127.0.0.1:16931",
            "BACKEND_HOST": "0.0.0.0", "BACKEND_PORT": "16930",
            "INTEGRATION_TOKEN": "test:=\\token", "ARK_API_KEY": "must-not-export",
        }):
            path = Path(directory) / "java.properties"
            write_local_configuration(path)
            text = path.read_text(encoding="ascii")
            self.assertIn("server.port=16931", text)
            self.assertIn("planning.legacy.base-url=http\\://127.0.0.1\\:16930", text)
            self.assertIn("test\\:\\=\\\\token", text)
            self.assertNotIn("must-not-export", text)
            self.assertIn('planning.manual.enabled=true', text)
            self.assertIn('business_test', text)
            self.assertIn('planning.manual.initialize-schema=true', text)
            connect.assert_not_called()
        with self.assertRaises(ValueError):
            properties_text({"key": "bad\nvalue"})

    def test_host_mode_never_generates_local_override(self):
        with TemporaryDirectory() as directory, override_config({"JAVA_ACCESS_MODE": "bank"}):
            path = Path(directory) / "java.properties"
            with self.assertRaises(ValueError):
                write_local_configuration(path)
            self.assertFalse(path.exists())

    def test_invalid_database_target_keeps_previous_launcher_configuration(self):
        with TemporaryDirectory() as directory, override_config({
            'JAVA_ACCESS_MODE':'local_development','JAVA_GATEWAY_URL':'http://127.0.0.1:6931',
            'BACKEND_HOST':'127.0.0.1','BACKEND_PORT':'6930','INTEGRATION_TOKEN':'test'
        }), patch('app.java_development.java_database_settings',side_effect=ValueError('same database')):
            path=Path(directory)/'java.properties'
            path.write_text('previous-config',encoding='ascii')
            with self.assertRaises(ValueError):write_local_configuration(path)
            self.assertEqual('previous-config',path.read_text(encoding='ascii'))
