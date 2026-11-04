"""Algorithm deployment never requires or creates business/source tables."""
from unittest.mock import MagicMock,patch

from app import algorithm_schema as schema
from app import db
from app import init_algorithm_db


def records():
    return [dict(TABLE_NAME=t,COLUMN_NAME=c,COLUMN_COMMENT=comment)
            for t,ddl in schema.definitions().items() for c,comment in schema.column_specs(ddl).items()]


def test_algorithm_package_exactly_matches_owner_list_and_canonical_sources():
    statements=schema.definitions()
    assert len(statements)==25 and set(statements)==schema.REQUIRED_TABLES
    assert not {'godp_planning_batch','godp_planning_item','godp_slot_state',
                'godp_manual_task','godp_account','godp_topic','godp_topic_official_usage'} & set(statements)
    assert (schema.ROOT/'algorithm_schema.sql').read_text(encoding='utf-8')==schema.build_sql()
    assert all(schema.column_specs(ddl) for ddl in statements.values())
    assert not any(word in schema.build_sql().upper() for word in ('DROP TABLE','ALTER TABLE','INSERT INTO'))


def test_schema_check_detects_missing_tables_columns_and_chinese_comments():
    cursor=MagicMock();cursor.fetchall.return_value=records()
    assert schema.inspect_schema(cursor)['status']=='passed'
    cursor.fetchall.return_value=[r for r in records() if r['TABLE_NAME']!='godp_algorithm_proposal'
        and not (r['TABLE_NAME']=='godp_manual_compute' and r['COLUMN_NAME']=='lease_until')]
    cursor.fetchall.return_value[0]['COLUMN_COMMENT']='English only'
    report=schema.inspect_schema(cursor)
    assert report['missing_tables']==['godp_algorithm_proposal']
    assert report['missing_columns']==['godp_manual_compute.lease_until']
    assert len(report['missing_comments'])==1
    assert report['status']=='not_ready'
    sql,params=cursor.execute.call_args.args
    assert 'TABLE_SCHEMA=DATABASE()' in sql and set(params)==schema.REQUIRED_TABLES


def test_health_uses_algorithm_tables_only_including_new_execution_receipts():
    connect=MagicMock();cursor=connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[{'name':t} for t in schema.REQUIRED_TABLES]
    with patch.object(db,'connection',connect):
        assert db.check_database()
        cursor.fetchall.return_value=[{'name':t} for t in schema.REQUIRED_TABLES if t!='godp_manual_compute']
        assert not db.check_database()


def test_algorithm_initializer_does_not_run_business_upgrade_or_approve_rules():
    connect=MagicMock();database=connect.return_value.__enter__.return_value
    cursor=database.cursor.return_value.__enter__.return_value
    with patch.object(db,'connection',connect),patch.object(init_algorithm_db,'inspect_schema',return_value={'status':'passed'}),\
         patch('app.init_system_config.seed_config',return_value=1) as seed:
        report=init_algorithm_db.initialize()
    assert report['configuration_seeded']
    seed.assert_called_once_with(cursor,migrate_legacy=False)
    statements=[call.args[0] for call in cursor.execute.call_args_list]
    assert len(statements)==25 and all(s.startswith('CREATE TABLE IF NOT EXISTS') for s in statements)
    assert not any('godp_planning_item (' in s or 'godp_manual_task (' in s for s in statements)
    database.commit.assert_called_once()


def test_initializer_does_not_seed_over_incompatible_existing_schema():
    connect=MagicMock()
    with patch.object(db,'connection',connect),patch.object(init_algorithm_db,'inspect_schema',return_value={'status':'not_ready','missing_columns':['example']}),\
         patch('app.init_system_config.seed_config') as seed:
        assert not init_algorithm_db.initialize()['configuration_seeded']
    seed.assert_not_called()
