"""MySQL connection and schema helpers for the first release."""

from contextlib import contextmanager
from pathlib import Path
import os

from dotenv import dotenv_values
import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parents[2]
# Only MySQL bootstrapping may come from a file or process environment.
# Application settings are read independently from godp_system_config.
for _file in (ROOT / "docs" / ".env", ROOT / ".env"):
    for _key, _value in dotenv_values(_file).items():
        if _key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE") and _value is not None:
            os.environ[_key] = _value


def settings() -> dict:
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"缺少数据库配置：{', '.join(missing)}")
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
        "autocommit": False,
    }


@contextmanager
def connection():
    db = pymysql.connect(**settings())
    try:
        yield db
    finally:
        db.close()


def check_database() -> bool:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = {next(iter(row.values())) for row in cursor.fetchall()}
            return {
                "godp_system_config",
                "godp_strategy_config",
                "godp_account",
                "godp_topic",
                "godp_planning_batch",
                "godp_planning_item",
                "godp_account_source",
                "godp_topic_source",
                "godp_source_sync_run",
                "godp_marketing_topic_source",
                "godp_marketing_sync_run",
                "godp_hotspot_topic_source",
                "godp_hotspot_sync_run",
                "godp_content_history",
                "godp_slot_state",
                "godp_integration_outbox",
                "godp_content_receipt",
                "godp_publication_receipt",
                "godp_topic_tag",
                "godp_topic_tag_history",
                "godp_t6_tag",
                "godp_topic_profile",
                "godp_account_profile",
                "godp_ai_preparation",
                "godp_ai_preparation_account",
                "godp_ai_preparation_topic",
                "godp_matching_policy",
                "godp_matching_task",
                "godp_matching_attempt",
                "godp_matching_input_snapshot",
                "godp_topic_label_job",
                "godp_topic_official_usage",
                "godp_topic_official_usage_history",
                "godp_strategy_config_version",
                "godp_manual_preview",
                "godp_manual_task",
                "godp_planning_adjustment",
                "godp_auto_plan_run",
            }.issubset(tables)
    except (pymysql.MySQLError, RuntimeError, ValueError):
        return False

