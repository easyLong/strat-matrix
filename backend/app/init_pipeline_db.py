"""Install the Planning Pipeline V1 orchestration tables."""

from pathlib import Path

from .db import connection
from .init_db import sync_column_comments, sync_table_comments


def main() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "pipeline_schema.sql"
    source = schema_path.read_text(encoding="utf-8")
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("--"))
    statements = [statement.strip() for statement in source.split(";") if statement.strip()]
    with connection() as db, db.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        updated_tables = sync_table_comments(cursor, source)
        updated_columns = sync_column_comments(cursor, source)
        db.commit()
    print(f"Pipeline schema ready; table comments updated: {updated_tables}; "
          f"column comments updated: {updated_columns}")


if __name__ == "__main__":
    main()
