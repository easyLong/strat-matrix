"""MySQL config source, migration safety and redaction tests; no business DB writes."""

from pathlib import Path
import os
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from dotenv import dotenv_values
import pymysql

from app import init_system_config as migration
from app import system_config as config
from app.init_db import column_definitions, table_descriptions
from app.system_config_catalog import CATALOG, MYSQL_KEYS, validate_value


class SystemConfigTests(unittest.TestCase):
    def setUp(self):
        config.clear_cache()
        self.addCleanup(config.clear_cache)
        self.db = MagicMock()
        self.cursor = MagicMock()
        self.db.__enter__.return_value = self.db
        self.db.cursor.return_value = self.cursor
        self.cursor.__enter__.return_value = self.cursor

    def rows(self, **values):
        values = {key: spec.default for key, spec in CATALOG.items()} | values
        self.cursor.fetchall.return_value = [
            {"config_key": key, "config_value": value, "enabled": 1}
            for key, value in values.items()]

    def test_runtime_reads_db_and_ignores_non_mysql_environment(self):
        self.rows(ARK_API_KEY="database-secret", BACKEND_PORT="7000")
        with patch.object(config, "connection", return_value=self.db), \
                patch.dict(os.environ, {"ARK_API_KEY": "environment-secret", "BACKEND_PORT": "8000"}):
            self.assertEqual(config.get_setting("ARK_API_KEY"), "database-secret")
            self.assertEqual(config.get_setting("BACKEND_PORT"), "7000")

    def test_missing_db_value_never_falls_back_to_environment(self):
        self.cursor.fetchall.return_value = []
        with patch.object(config, "connection", return_value=self.db), \
                patch.dict(os.environ, {"ARK_API_KEY": "must-not-use"}):
            with self.assertRaises(config.SystemConfigError):
                config.get_setting("ARK_API_KEY")

    def test_cached_snapshot_is_reused_within_five_seconds(self):
        self.rows(INTEGRATION_TOKEN="db-token")
        with patch.object(config, "connection", return_value=self.db) as connect, \
                patch.object(config.time, "monotonic", return_value=100):
            self.assertEqual(config.get_setting("INTEGRATION_TOKEN"), "db-token")
            self.assertEqual(config.get_setting("INTEGRATION_TOKEN"), "db-token")
        connect.assert_called_once()

    def test_expired_cache_fails_closed_if_database_is_unavailable(self):
        self.rows(INTEGRATION_TOKEN="old-token")
        with patch.object(config, "connection", return_value=self.db), \
                patch.object(config.time, "monotonic", return_value=100):
            config.get_setting("INTEGRATION_TOKEN")
        with patch.object(config, "connection", side_effect=pymysql.OperationalError(2003, "private host")), \
                patch.object(config.time, "monotonic", return_value=106):
            with self.assertRaises(config.SystemConfigError) as raised:
                config.get_setting("INTEGRATION_TOKEN")
            self.assertNotIn("private host", str(raised.exception))

    def test_disabled_setting_cannot_fall_back_to_a_default(self):
        self.cursor.fetchall.return_value = [{"config_key": "ARK_API_KEY", "config_value": "secret", "enabled": 0}]
        with patch.object(config, "connection", return_value=self.db):
            with self.assertRaises(config.SystemConfigError):
                config.get_setting("ARK_API_KEY", "unsafe-default")

    def test_frontend_and_shell_exports_do_not_contain_secrets(self):
        self.rows(ARK_API_KEY="never-export", INTEGRATION_TOKEN="never-export-token",
                  BACKEND_PORT="7000", TOPIC_VECTOR_MODEL_URL="https://private.invalid?token=secret")
        with patch.object(config, "connection", return_value=self.db):
            frontend = config.public_settings(frontend=True)
            shell = config.public_settings()
        self.assertEqual(len(frontend), 4)
        self.assertNotIn("ARK_API_KEY", shell)
        self.assertNotIn("INTEGRATION_TOKEN", shell)
        self.assertNotIn("secret", str(frontend) + str(shell))
        self.assertEqual(shell["TOPIC_VECTOR_MODEL_CONFIGURED"], "1")

    def test_secret_masking_also_uses_catalog_classification(self):
        self.cursor.fetchall.return_value = [{"config_key": "ARK_API_KEY", "config_value": "private", "is_secret": 0,
                                             "config_group": "doubao"}]
        with patch.object(config, "connection", return_value=self.db):
            self.assertEqual(config.masked_settings()[0]["config_value"], "******")

    def test_stale_config_update_does_not_commit_or_update(self):
        self.cursor.fetchone.return_value = {"version": 3}
        with patch.object(config, "connection", return_value=self.db):
            with self.assertRaises(config.SystemConfigError):
                config.set_setting("BACKEND_PORT", "7000", expected_version=2)
        self.db.commit.assert_not_called()
        self.assertFalse(any(call.args[0].startswith("UPDATE") for call in self.cursor.execute.call_args_list))

    def test_valid_update_increments_version_and_invalidates_cache(self):
        self.cursor.fetchone.return_value = {"version": 3}
        with patch.object(config, "connection", return_value=self.db), patch.object(config, "clear_cache") as clear:
            self.assertEqual(config.set_setting("BACKEND_PORT", "7000", expected_version=3), 4)
        self.db.commit.assert_called_once()
        clear.assert_called_once()

    def test_invalid_types_or_ports_are_rejected(self):
        for key, value in (("BACKEND_PORT", "0"), ("BACKEND_PORT", "65536"), ("BACKEND_PORT", "text"),
                           ("TOPIC_LABEL_WORKER_ENABLED", "true"), ("TOPIC_LABEL_PROVIDER", "other"),
                           ("ARK_API_KEY", "secret\nextra")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_value(key, value)

    def test_overrides_are_explicit_scoped_and_do_not_access_database(self):
        with patch.object(config, "connection") as connect, config.override_config({"ARK_API_KEY": "outer"}):
            self.assertEqual(config.get_setting("ARK_API_KEY"), "outer")
            with config.override_config({"ARK_API_KEY": "inner"}):
                self.assertEqual(config.get_setting("ARK_API_KEY"), "inner")
            self.assertEqual(config.get_setting("ARK_API_KEY"), "outer")
            connect.assert_not_called()


class SystemConfigMigrationTests(unittest.TestCase):
    def test_table_and_all_fourteen_fields_have_chinese_comments(self):
        source = migration.schema_statement()
        columns = column_definitions(source)["godp_system_config"]
        self.assertEqual(len(columns), 14)
        self.assertIn("godp_system_config", table_descriptions(source))
        self.assertTrue(all(re.search(r"[\u4e00-\u9fff]", comment) for _, comment in columns.values()))

    def test_all_defaults_are_valid_and_mysql_credentials_are_not_in_catalog(self):
        for key, spec in CATALOG.items():
            validate_value(key, spec.default)
            self.assertNotIn(key, MYSQL_KEYS)

    def test_root_env_takes_precedence_and_only_non_mysql_keys_are_imported(self):
        with TemporaryDirectory() as directory:
            legacy, root = Path(directory) / "legacy.env", Path(directory) / ".env"
            legacy.write_text("BACKEND_PORT=6000\nMYSQL_PASSWORD=legacy\n", encoding="utf-8")
            root.write_text("BACKEND_PORT=6930\nARK_API_KEY=\nMYSQL_PASSWORD=root\n", encoding="utf-8")
            self.assertEqual(migration.imported_values([legacy, root]), {"BACKEND_PORT": "6930", "ARK_API_KEY": ""})

    def test_cleanup_preserves_quoted_mysql_password_and_removes_other_values(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("MYSQL_HOST=localhost\nMYSQL_PASSWORD='a#b$ c'\nARK_API_KEY=private\n", encoding="utf-8")
            migration.clean_env_file(path)
            self.assertEqual(dotenv_values(path), {"MYSQL_HOST": "localhost", "MYSQL_PASSWORD": "a#b$ c"})

    def test_seed_does_not_overwrite_values_already_in_database(self):
        saved = {"BACKEND_PORT": "7777"}
        cursor = MagicMock()

        def execute(sql, params):
            key, _, _, value, *_ = params
            self.assertIn("ON DUPLICATE KEY UPDATE config_key=VALUES(config_key)", sql)
            cursor.rowcount = int(key not in saved)
            saved.setdefault(key, value)

        cursor.execute.side_effect = execute
        migration.seed_config(cursor, {"BACKEND_PORT": "6930"})
        self.assertEqual(saved["BACKEND_PORT"], "7777")
        self.assertEqual(len(saved), len(CATALOG))

    def test_cleanup_occurs_only_after_database_commit_and_verification(self):
        db, cursor = MagicMock(), MagicMock()
        db.__enter__.return_value = db
        db.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [{"config_key": "ARK_API_KEY", "config_value": "private"}]
        events = []
        db.commit.side_effect = lambda: events.append("commit")
        with patch.object(migration, "connection", return_value=db), \
                patch.object(migration, "imported_values", return_value={"ARK_API_KEY": "private"}), \
                patch.object(migration, "seed_config", return_value=1), \
                patch.object(migration, "clean_env_file", side_effect=lambda path: events.append("clean")):
            migration.initialize(migrate_env=True, clean_env=True)
        self.assertEqual(events, ["commit", "clean", "clean"])

    def test_migration_conflict_keeps_original_files(self):
        db, cursor = MagicMock(), MagicMock()
        db.__enter__.return_value = db
        db.cursor.return_value = cursor
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [{"config_key": "ARK_API_KEY", "config_value": "changed-in-db"}]
        with patch.object(migration, "connection", return_value=db), \
                patch.object(migration, "imported_values", return_value={"ARK_API_KEY": "old-file"}), \
                patch.object(migration, "seed_config", return_value=0), \
                patch.object(migration, "clean_env_file") as clean:
            with self.assertRaises(ValueError):
                migration.initialize(migrate_env=True, clean_env=True)
        clean.assert_not_called()
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
