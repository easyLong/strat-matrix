"""Explicit deployment tool for both owned schemas; never imported by the runtime services."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.content_planning.db import connection
from app.content_planning.java_development import java_database_settings
from app.content_planning.init_planner_db import statements

ROOT = Path(__file__).resolve().parents[2]


def backup(db, destination, data_tables):
    with db.cursor() as cursor:
        cursor.execute('SELECT DATABASE() name'); name=cursor.fetchone()['name']
        cursor.execute('SHOW FULL TABLES'); names=[list(row.values())[0] for row in cursor.fetchall() if list(row.values())[1]=='BASE TABLE']
        result={'database':name,'schema':{},'data':{},'counts':{}}
        for table in names:
            cursor.execute(f'SHOW CREATE TABLE `{table}`');definition=cursor.fetchone();result['schema'][table]=definition['Create Table']
            if table in data_tables:
                cursor.execute(f'SELECT * FROM `{table}`');result['data'][table]=cursor.fetchall()
                result['counts'][table]=len(result['data'][table])
    destination.write_text(json.dumps(result,ensure_ascii=False,default=str),encoding='utf-8')
    db.rollback()  # Release metadata locks taken by the backup reads before DDL on another connection.
    return {'database':name,'saved_tables':len(result['schema']),'data_counts':result['counts']}


def run(output, apply):
    output.mkdir(parents=True,exist_ok=True)
    cfg=java_database_settings()
    with connection() as algorithm, pymysql.connect(**cfg) as business:
        a=backup(algorithm,output/'algorithm-before.json',{
            'godp_planning_pipeline_run','godp_planning_stage_run','godp_strategy_config',
            'godp_strategy_config_version','godp_planning_batch','godp_planning_item',
            'godp_planning_adjustment','godp_slot_state','godp_manual_task','godp_manual_preview','godp_manual_marketing_task'})
        with business.cursor() as c:
            c.execute('SHOW FULL TABLES'); all_business={list(r.values())[0] for r in c.fetchall() if list(r.values())[1]=='BASE TABLE'}
        b=backup(business,output/'business-before.json',all_business)
        if a['database']==b['database']:raise RuntimeError('业务库与算法库不可相同')
        report={'before':{'algorithm':a,'business':b},'applied':False}
        if apply:
            root=ROOT/'java-backend/godp-planning-services/src/main/resources/db'
            with business.cursor() as c:
                c.execute("SELECT GET_LOCK('strat-matrix:business-migration',5) acquired")
                if c.fetchone()['acquired']!=1:raise RuntimeError('业务库迁移锁被占用')
                try:
                    for file in ('manual-business.sql','business-planning-config.sql','auto-planning-business.sql','slot-completion.sql'):
                        for sql in statements((root/file).read_text(encoding='utf-8')):c.execute(sql)
                    c.execute('SHOW COLUMNS FROM godp_planning_item'); columns={r['Field'] for r in c.fetchall()}
                    if 'slot_id' not in columns:
                        source=(root/'migrations/V3__result_slot_identity.sql').read_text(encoding='utf-8')
                        for sql in '\n'.join(l for l in source.splitlines() if not l.startswith('--')).split(';'):
                            if sql.strip():c.execute(sql)
                    c.execute('SHOW COLUMNS FROM godp_auto_planning_task'); columns={r['Field'] for r in c.fetchall()}
                    if 'business_batch_id' not in columns:
                        source=(root/'migrations/V4__auto_result_receipt.sql').read_text(encoding='utf-8')
                        for sql in '\n'.join(l for l in source.splitlines() if not l.startswith('--')).split(';'):
                            if sql.strip():c.execute(sql)
                    for table,column,definition in (
                        ('godp_planning_batch','week_start',"VARCHAR(10) NULL COMMENT '批次所属自然周的周一，用于时间列表数据库分页'"),
                        ('godp_planning_item','publish_week',"VARCHAR(10) NULL COMMENT '投放日期所属自然周的周一，用于账号日历数据库分页'"),
                        ('godp_manual_marketing_task','batch_id',"BIGINT NULL COMMENT '过审内容完成投放日期编排后关联的正式批次'"),
                        ('godp_manual_marketing_task','linked_count',"INT NOT NULL DEFAULT 0 COMMENT '已引用过审内容并确定投放日期的数量'"),
                    ):
                        c.execute(f'SHOW COLUMNS FROM {table}')
                        if column not in {r['Field'] for r in c.fetchall()}:c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                    c.execute("UPDATE godp_planning_batch SET week_start=DATE_FORMAT(DATE_SUB(STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'%Y-%m-%d'),INTERVAL WEEKDAY(STR_TO_DATE(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.cycle_start')),'%Y-%m-%d')) DAY),'%Y-%m-%d') WHERE week_start IS NULL")
                    c.execute("UPDATE godp_planning_item SET publish_week=DATE_FORMAT(DATE_SUB(STR_TO_DATE(publish_date,'%Y-%m-%d'),INTERVAL WEEKDAY(STR_TO_DATE(publish_date,'%Y-%m-%d')) DAY),'%Y-%m-%d') WHERE publish_week IS NULL")
                    for table,name,cols in [('godp_planning_batch','idx_batch_week','week_start,id'),('godp_planning_item','idx_item_week_account','publish_week,account_id,id')]:
                        c.execute(f'SHOW INDEX FROM {table}')
                        if name not in {r['Key_name'] for r in c.fetchall()}:c.execute(f'ALTER TABLE {table} ADD INDEX {name}({cols})')
                    c.execute("ALTER TABLE godp_planning_item MODIFY COLUMN content_status VARCHAR(16) NOT NULL DEFAULT 'planned' COMMENT '内容状态unassigned待定题 awaiting_market待营销引用 planned待生产 ready生产中 generated已完成 failed生产失败'")
                    business.commit()
                finally:c.execute("SELECT RELEASE_LOCK('strat-matrix:business-migration')")
            from app.content_planning.init_pipeline_db import main
            main()
            with algorithm.cursor() as c:
                c.execute("INSERT IGNORE INTO godp_system_config(config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by) VALUES('AUTO_SCHEDULE_OWNER','planning','周自动策划触发方','python','string',0,'boundary-migration','boundary-migration')")
                algorithm.commit()
            report['applied']=True
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='备份并增量发布策划业务／算法库迁移')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'run/backups'/datetime.now(timezone.utc).strftime('boundary-%Y%m%d-%H%M%S'))
    args=parser.parse_args();run(args.output,args.apply)
