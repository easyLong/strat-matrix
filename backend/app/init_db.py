"""Apply the first release schema to the configured MySQL database."""

from pathlib import Path
import json
import re

from .db import connection
from .taxonomy import legacy_tag_ids, normalize_taxonomy


def column_definitions(schema: str) -> dict[str, dict[str, tuple[str, str]]]:
    """Read the column declarations used for both CREATE and comment updates."""
    tables: dict[str, dict[str, tuple[str, str]]] = {}
    table: str | None = None
    for line in schema.splitlines():
        stripped = line.strip().rstrip(",")
        start = re.fullmatch(r"CREATE TABLE IF NOT EXISTS (godp_[a-z0-9_]+) \(", stripped)
        if start:
            table = start.group(1)
            tables[table] = {}
            continue
        if stripped.startswith(") ENGINE="):
            table = None
            continue
        if table is None:
            continue
        column = re.match(r"^([a-z][a-z0-9_]*)\s+(.+)$", stripped)
        if not column:
            continue
        name = column.group(1)
        definition = column.group(2)
        comment = re.search(r"\bCOMMENT '([^']+)'", definition)
        if not comment or not re.search(r"[\u4e00-\u9fff]", comment.group(1)):
            raise ValueError(f"{table}.{name} 缺少中文字段说明")
        # A primary key is already present on an existing table. MODIFY COLUMN
        # retains its index, while AUTO_INCREMENT must stay in the declaration.
        definition = re.sub(r"\bPRIMARY KEY\b", "", definition).strip()
        tables[table][name] = (definition, comment.group(1))
    return tables


def table_descriptions(schema: str) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    table: str | None = None
    for line in schema.splitlines():
        stripped = line.strip()
        start = re.fullmatch(r"CREATE TABLE IF NOT EXISTS (godp_[a-z0-9_]+) \(", stripped)
        if start:
            table = start.group(1)
            continue
        if table and stripped.startswith(") ENGINE="):
            comment = re.search(r"\bCOMMENT='([^']+)'", stripped)
            if not comment or not re.search(r"[\u4e00-\u9fff]", comment.group(1)):
                raise ValueError(f"{table} 缺少中文表说明")
            descriptions[table] = comment.group(1)
            table = None
    return descriptions


def sync_table_comments(cursor, schema: str) -> int:
    updated = 0
    for table, description in table_descriptions(schema).items():
        cursor.execute(
            "SELECT TABLE_COMMENT FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            (table,),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"{table} 不存在")
        if row["TABLE_COMMENT"] != description:
            cursor.execute(f"ALTER TABLE `{table}` COMMENT=%s", (description,))
            updated += 1
    return updated


def sync_column_comments(cursor, schema: str) -> int:
    updated = 0
    for table, columns in column_definitions(schema).items():
        cursor.execute(
            "SELECT COLUMN_NAME, COLUMN_COMMENT FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
            (table,),
        )
        existing = {row["COLUMN_NAME"]: row["COLUMN_COMMENT"] for row in cursor.fetchall()}
        missing = set(columns) - set(existing)
        if missing:
            raise RuntimeError(f"{table} 缺少字段：{', '.join(sorted(missing))}")
        modifications = [
            f"MODIFY COLUMN `{name}` {definition}"
            for name, (definition, comment) in columns.items()
            if existing[name] != comment
        ]
        if modifications:
            cursor.execute(f"ALTER TABLE `{table}` " + ", ".join(modifications))
            updated += len(modifications)
    return updated


def main() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
    source = schema_path.read_text(encoding="utf-8")
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("--"))
    statements = [statement.strip() for statement in source.split(";") if statement.strip()]
    with connection() as db, db.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        for name, definition in (
            ("lifecycle_stage", "VARCHAR(32) NULL COMMENT '策划时账号生命周期阶段快照'"),
            ("content_role", "VARCHAR(16) NULL COMMENT '策划时选题经营作用快照：流量或转化'"),
            ("topic_type", "VARCHAR(16) NULL COMMENT '实际绑定选题的来源类型：普通、营销或热点；待定空槽为空'"),
            ("outline", "LONGTEXT NULL COMMENT '策划结果选题大纲快照；待定空槽为空'"),
            ("content_type", "VARCHAR(100) NULL COMMENT '策划结果内容类型快照；待定空槽为空'"),
        ):
            cursor.execute(
                "SELECT COUNT(*) AS column_count FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_planning_item' "
                "AND COLUMN_NAME=%s", (name,),
            )
            if cursor.fetchone()["column_count"] == 0:
                cursor.execute(f"ALTER TABLE godp_planning_item ADD COLUMN `{name}` {definition}")
        for name, definition in (
            ("label_status", "VARCHAR(16) NOT NULL DEFAULT '处理中' COMMENT '普通选题T1到T6标签识别状态：处理中、已完成或失败'"),
            ("label_error", "VARCHAR(500) NOT NULL DEFAULT '' COMMENT '标签识别失败原因或空字符串'"),
            ("tag_ids_json", "LONGTEXT NULL COMMENT '选题已识别T1到T5标签稳定ID映射JSON；旧数据可部分解析'"),
            ("taxonomy_version", "INT NULL COMMENT '本次标签识别使用的T1到T5字典版本；旧记录未知时为空'"),
        ):
            cursor.execute(
                "SELECT COUNT(*) AS column_count FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_topic_tag' "
                "AND COLUMN_NAME=%s", (name,),
            )
            if cursor.fetchone()["column_count"] == 0:
                cursor.execute(f"ALTER TABLE godp_topic_tag ADD COLUMN `{name}` {definition}")
        for table, description in (
            ("godp_account_source", "账号来源记录当前是否有效：1有效0已被全量快照停用"),
            ("godp_topic_source", "普通选题来源记录当前是否有效：1有效0已被全量快照停用"),
        ):
            cursor.execute(
                "SELECT COUNT(*) AS column_count FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s "
                "AND COLUMN_NAME='active_in_snapshot'", (table,),
            )
            if cursor.fetchone()["column_count"] == 0:
                cursor.execute(
                    f"ALTER TABLE `{table}` ADD COLUMN active_in_snapshot "
                    f"TINYINT(1) NOT NULL DEFAULT 1 COMMENT '{description}'"
                )
        cursor.execute(
            "SELECT config_json FROM godp_strategy_config "
            "WHERE config_key='tag_taxonomy' AND del_flag='N' FOR UPDATE"
        )
        taxonomy_row = cursor.fetchone()
        if taxonomy_row:
            raw_taxonomy = json.loads(taxonomy_row["config_json"])
            if any(isinstance(value, str) for values in raw_taxonomy.values() for value in values):
                cursor.execute(
                    "UPDATE godp_strategy_config SET config_json=%s, update_by='migration' "
                    "WHERE config_key='tag_taxonomy'",
                    (json.dumps(normalize_taxonomy(raw_taxonomy), ensure_ascii=False,
                                separators=(",", ":")),),
                )
        cursor.execute(
            "SELECT id, config_json FROM godp_strategy_config_version "
            "WHERE config_key='tag_taxonomy' AND del_flag='N'"
        )
        for old_version in cursor.fetchall():
            old_raw = json.loads(old_version["config_json"])
            if any(isinstance(value, str) for values in old_raw.values() for value in values):
                cursor.execute(
                    "UPDATE godp_strategy_config_version SET config_json=%s, update_by='migration' "
                    "WHERE id=%s",
                    (json.dumps(normalize_taxonomy(old_raw), ensure_ascii=False,
                                separators=(",", ":")), old_version["id"]),
                )
        cursor.execute(
            "INSERT IGNORE INTO godp_strategy_config_version "
            "(config_key, version, config_json, action, create_by, update_by) "
            "SELECT config_key, version, config_json, '历史基线', create_by, update_by "
            "FROM godp_strategy_config WHERE del_flag='N'"
        )
        for module in ("marketing", "strategy"):
            cursor.execute(
                "INSERT IGNORE INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "SELECT %s, 1, config_json, '迁移基线', create_by, update_by "
                "FROM godp_strategy_config WHERE config_key='operations' AND del_flag='N'",
                (module,),
            )
        cursor.execute(
            "SELECT config_json FROM godp_strategy_config_version "
            "WHERE config_key='tag_taxonomy' AND del_flag='N' ORDER BY version"
        )
        snapshots = [normalize_taxonomy(json.loads(row["config_json"]))
                     for row in cursor.fetchall()]
        cursor.execute(
            "SELECT id, tags_json FROM godp_topic_tag "
            "WHERE tag_ids_json IS NULL AND del_flag='N'"
        )
        for tag_row in cursor.fetchall():
            try:
                tags = json.loads(tag_row["tags_json"])
                resolved = legacy_tag_ids(tags, snapshots) if isinstance(tags, dict) else {}
            except (TypeError, json.JSONDecodeError):
                resolved = {}
            cursor.execute(
                "UPDATE godp_topic_tag SET tag_ids_json=%s, "
                "update_by='migration', update_time=update_time WHERE id=%s",
                (json.dumps(resolved, ensure_ascii=False, separators=(",", ":")), tag_row["id"]),
            )
        cursor.execute(
            "INSERT IGNORE INTO godp_topic_tag_history "
            "(topic_id, version, tags_json, tag_ids_json, taxonomy_version, "
            "label_status, label_error, create_time, create_by, update_by) "
            "SELECT topic_id, version, tags_json, COALESCE(tag_ids_json, '{}'), "
            "taxonomy_version, label_status, label_error, update_time, update_by, 'migration' "
            "FROM godp_topic_tag WHERE del_flag='N'"
        )
        updated_tables = sync_table_comments(cursor, source)
        updated_columns = sync_column_comments(cursor, source)
        db.commit()
    print(f"Schema ready; table comments updated: {updated_tables}; "
          f"column comments updated: {updated_columns}")


if __name__ == "__main__":
    main()

