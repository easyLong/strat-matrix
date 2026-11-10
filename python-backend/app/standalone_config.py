"""Standalone-only file loading. Embedded imports never execute this loader."""
from pathlib import Path
import os


def load_config(*, environ=None, workspace=None):
    from dotenv import dotenv_values
    from .content_planning.config import DatabaseConfig, PlanningConfig
    root = Path(workspace).resolve() if workspace else Path(__file__).resolve().parent.parent.parent
    env = dict(os.environ if environ is None else environ)
    values = {}
    for file in (root / 'docs/.env', root / '.env'):
        values.update({k: v for k, v in dotenv_values(file).items() if k.startswith('MYSQL_') and v is not None})
    values.update({k: v for k, v in env.items() if k.startswith('MYSQL_')})
    database = None
    if all(values.get('MYSQL_' + k) for k in ('HOST', 'USER', 'PASSWORD', 'DATABASE')):
        database = DatabaseConfig(host=values['MYSQL_HOST'], user=values['MYSQL_USER'],
                                  password=values['MYSQL_PASSWORD'], database=values['MYSQL_DATABASE'],
                                  port=int(values.get('MYSQL_PORT', 3306)))
    return PlanningConfig(enabled=True, database=database, standalone=True, check_schema=False,
                          workspace_directory=root, fixture_path=root / 'run/bank-source-fixture.json',
                          resource_directory=root / 'python-backend/database/content_planning')
