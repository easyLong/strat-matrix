"""MySQL connection and schema helpers for the first release."""

from contextlib import contextmanager
from pathlib import Path
import os

from dotenv import load_dotenv
import pymysql
from pymysql.cursors import DictCursor


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / "docs" / ".env")
load_dotenv(ROOT / ".env", override=True)


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
                "godp_strategy_config",
                "godp_account",
                "godp_topic",
                "godp_planning_batch",
                "godp_planning_item",
                "godp_account_source",
                "godp_topic_source",
                "godp_content_history",
                "godp_slot_state",
                "godp_integration_outbox",
                "godp_content_receipt",
                "godp_publication_receipt",
                "godp_topic_tag",
                "godp_strategy_config_version",
                "godp_manual_preview",
                "godp_manual_task",
                "godp_planning_adjustment",
                "godp_auto_plan_run",
            }.issubset(tables)
    except (pymysql.MySQLError, RuntimeError, ValueError):
        return False

