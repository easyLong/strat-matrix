"""Apply the first release schema to the configured MySQL database."""

from pathlib import Path
import re

from .db import connection


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
        updated_tables = sync_table_comments(cursor, source)
        updated_columns = sync_column_comments(cursor, source)
        db.commit()
    print(f"Schema ready; table comments updated: {updated_tables}; "
          f"column comments updated: {updated_columns}")


if __name__ == "__main__":
    main()

