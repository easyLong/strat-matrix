"""Bank audit contract and non-destructive deployment plans; no live connections."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import re

import pytest

from app import algorithm_schema
from app.table_audit import PUBLIC_COLUMNS, metadata_errors, normalize_ddl, validate_ddl

spec = importlib.util.spec_from_file_location('table_audit_migration', Path(__file__).resolve().parents[1] / 'tools/migrate_table_audit.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def row(name, typ, default=None, extra='', comment='中文说明'):
    return dict(COLUMN_NAME=name, COLUMN_TYPE=typ, IS_NULLABLE='NO', COLUMN_DEFAULT=default,
                EXTRA=extra, COLUMN_COMMENT=comment)


def compliant():
    return [row('id', 'bigint', extra='auto_increment'), row('del_flag', 'varchar(1)', 'N'),
            row('created_by', 'varchar(50)', 'system'), row('updated_by', 'varchar(50)', 'system'),
            row('created_time', 'datetime', 'CURRENT_TIMESTAMP'),
            row('updated_time', 'datetime', 'CURRENT_TIMESTAMP', 'on update CURRENT_TIMESTAMP')]


def test_all_39_active_tables_have_identical_six_column_contract_and_comments():
    tables = {**algorithm_schema.definitions(), **migration.business_definitions()}
    assert len(tables) == 39
    for ddl in tables.values():
        assert validate_ddl(ddl)
        assert all(name in algorithm_schema.column_specs(ddl) for name in PUBLIC_COLUMNS)


def test_natural_and_compound_primary_keys_remain_unique_under_new_surrogate_id():
    for key, body in [(['request_id'], "request_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '请求编号'"),
                      (['kind','resource_key'], "kind VARCHAR(24) NOT NULL COMMENT '类型',\nresource_key VARCHAR(80) NOT NULL COMMENT '资源键',\nPRIMARY KEY(kind,resource_key)")]:
        ddl = normalize_ddl("CREATE TABLE IF NOT EXISTS godp_probe (\n" + body + "\n) ENGINE=InnoDB COMMENT='测试表';")
        assert validate_ddl(ddl)
        assert 'UNIQUE KEY uk_audit_legacy_godp_probe (' + ','.join(key) + ')' in ddl
        assert normalize_ddl(ddl) == ddl


def test_metadata_validation_checks_types_defaults_primary_and_update_behavior():
    assert not metadata_errors(compliant(), ['id'])
    wrong = deepcopy(compliant())
    wrong[2]['COLUMN_TYPE'] = 'varchar(64)'
    wrong[3]['COLUMN_DEFAULT'] = 'worker'
    wrong[4]['COLUMN_TYPE'] = 'bigint'
    wrong[5]['EXTRA'] = ''
    errors = metadata_errors(wrong, ['request_id'])
    assert {'created_by:type','updated_by:default','created_time:type','updated_time:on_update','id:primary_key'} <= set(errors)


def test_compatibility_migration_retains_business_fields_and_converts_millis_without_reidentification():
    old = [row('request_id','varchar(64)'), row('created_at','bigint'), row('updated_at','bigint'), row('payload','longtext')]
    ddl, dml, actors = migration.plan('godp_probe', old, ['request_id'], 'BTREE')
    assert 'DROP PRIMARY KEY' in ddl[0] and 'UNIQUE KEY uk_audit_legacy_godp_probe (`request_id`)' in ddl[0]
    assert not any('DROP COLUMN' in sql for sql in ddl)
    assert 'FROM_UNIXTIME(`created_at` / 1000)' in dml[0]
    assert 'FROM_UNIXTIME(`updated_at` / 1000)' in dml[0]
    assert "$.created_by" in actors['created_by']
    existing = [row('id','bigint'),row('payload','longtext')]
    ddl,_,_ = migration.plan('godp_probe',existing,['id'],'BTREE')
    assert 'MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT' in ddl[0]
    assert not any('DROP PRIMARY KEY' in sql for sql in ddl)


def test_backfill_preserves_old_on_update_timestamps_and_is_idempotent():
    old = [row('id','bigint',extra='auto_increment'), row('create_time','datetime(6)'),
           row('update_time','datetime(6)',extra='on update CURRENT_TIMESTAMP(6)'), row('create_by','varchar(50)'),row('update_by','varchar(50)')]
    _,dml,_ = migration.plan('godp_probe',old,['id'],'BTREE')
    assert '`update_time`=`update_time`' in dml[0]
    assert "`created_by`=COALESCE(NULLIF(`create_by`,''),'system')" in dml[0]
    assert migration.plan('godp_probe',compliant(),['id'],'BTREE') == ([],[],{})


def test_resume_skips_already_added_id_and_columns_but_keeps_missing_alters():
    original = [row('request_id','varchar(64)')]
    ddl,_,_ = migration.plan('godp_probe',original,['request_id'],'BTREE')
    current = original + [compliant()[0],compliant()[2]]
    pending = migration.pending_ddl(ddl,current,['id'],'BTREE')
    assert not any('DROP PRIMARY KEY' in sql or 'ADD COLUMN created_by ' in sql for sql in pending)
    assert any('ADD COLUMN updated_time ' in sql for sql in pending)


def test_migration_rejects_unknown_or_conflicting_identifiers_instead_of_changing_keys():
    with pytest.raises(ValueError):migration.plan('not-owned',compliant(),['id'],'BTREE')
    with pytest.raises(ValueError):migration.plan('godp_probe',compliant(),['request_id'],'BTREE')


def test_manual_claim_query_filters_deleted_rows_outside_the_whole_or_condition():
    import ast
    path=Path(__file__).resolve().parents[1]/'app/manual_compute.py'
    queries=[node.value for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))) if isinstance(node,ast.Constant) and isinstance(node.value,str)]
    query=next(value for value in queries if 'SELECT request_id,input_json' in value)
    assert re.search(r"WHERE del_flag='N' AND \(status='pending' OR .*\) ORDER BY",query)
