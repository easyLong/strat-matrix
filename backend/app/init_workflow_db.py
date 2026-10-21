"""Install additive planning and content workflow migrations, including Chinese comments."""

from pathlib import Path
from .db import connection
from .init_pipeline_db import main as init_pipeline
from .init_result_commit_db import main as init_commit
from .system_config_catalog import CATALOG


def main():
    init_pipeline()
    init_commit()
    source = (Path(__file__).resolve().parents[1] / 'content_production_schema.sql').read_text(encoding='utf-8')
    with connection() as db, db.cursor() as cursor:
        for statement in source.split(';'):
            if statement.strip():
                cursor.execute(statement)
        spec = CATALOG['CONTENT_PRODUCTION_MODE']
        cursor.execute("INSERT IGNORE INTO godp_system_config "
                       '(config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by) '
                       "VALUES ('CONTENT_PRODUCTION_MODE',%s,%s,%s,'string',0,'workflow-migration','workflow-migration')",
                       (spec.group, spec.name, spec.default))
        db.commit()
    print('Planning and content workflow schema ready')


if __name__ == '__main__':
    main()
