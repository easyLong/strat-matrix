"""One-time, idempotent history import. Runtime services never connect across owned databases."""
import argparse
from datetime import datetime,date,timezone,timedelta
import json
from pathlib import Path
import sys
import pymysql
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import connection
from app.java_development import java_database_settings
from app.services.results import read_batches
from app.adapters.mysql.planning_queries import items as source_items
from app.core.planning_items import enrich_plan_item
from app.services.manual_planning import list_manual_tasks
from app.manual_marketing_api import summary as marketing_summary
from app.services.periods import cycle_failure_rows

ROOT=Path(__file__).resolve().parents[2]
def encoded(value):return json.dumps(value,ensure_ascii=False,default=str,separators=(',',':'))
def millis(value):
    if not value:return 0
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:value=value.replace(tzinfo=__import__('zoneinfo').ZoneInfo('Asia/Shanghai'))
    return int(value.timestamp()*1000)
def week(value):
    d=date.fromisoformat(str(value)[:10]);return str(d-timedelta(days=d.weekday()))

def run(apply,output):
    with connection() as db,db.cursor() as c:
        batches=read_batches(c,limit=100000)
        raw=source_items(c,'1=1',[],'i.id',limit=1000000)
        c.execute("SELECT batch_id,account_id,snapshot_json FROM godp_account_profile WHERE del_flag='N'")
        frozen={(r['batch_id'],r['account_id']):json.loads(r['snapshot_json']) for r in c.fetchall()}
        c.execute("SELECT * FROM godp_planning_adjustment WHERE del_flag='N' ORDER BY id")
        operations=c.fetchall()
        c.execute("SELECT * FROM godp_strategy_config_version WHERE config_key='operations' AND del_flag='N' ORDER BY version")
        config_history=c.fetchall()
        c.execute("SELECT * FROM godp_manual_marketing_task WHERE del_flag='N'")
        marketing=c.fetchall()
        c.execute("SELECT batch_id,topic_snapshot_json FROM godp_auto_plan_run WHERE del_flag='N'")
        overlays={r['batch_id']:json.loads(r['topic_snapshot_json']) for r in c.fetchall()}
        c.execute("SELECT item_id,content_id,production_task_id,production_reported_at,production_error FROM godp_slot_state WHERE del_flag='N'")
        production={r['item_id']:r for r in c.fetchall()}
    manual=[]
    for offset in range(0,1000000,100):
        page=list_manual_tasks(100,offset);manual.extend(page)
        if len(page)<100:break
    records=[]
    for original in raw:
        r=enrich_plan_item(dict(original),original['plan_type'])
        source=frozen.get((r['batch_id'],r['account_id'])) or json.loads(r.get('account_source_payload') or '{}')
        profile={k:source.get(k) for k in ('account_id','account_name','um_no','organization','platform','account_type','persona','gender','interests','marketing_eligible')}
        profile.update(account_id=r['account_id'],account_name=r['account_name'],
            followers=source.get('followers',source.get('followers_count',source.get('follower_count',0))),lifecycle_stage=r.get('lifecycle_stage') or source.get('lifecycle_stage',''),persona=source.get('persona') or source.get('account_persona',''))
        r.update({k:v for k,v in production.get(r['id'],{}).items() if k!='item_id'})
        r['account_snapshot']=profile;r['slot_id']=r.get('slot_id') or 'LEGACY-'+str(r['id'])
        r['result_version']=r.get('result_version') or 1
        r['hotspot_fallback']=overlays.get(r['batch_id'],{}).get('hotspot_fallbacks',{}).get(r["account_id"]+'|'+str(r['publish_date']))
        for key in ('account_source_payload','slot_topic_id','del_flag'):r.pop(key,None)
        state=r.get('production_status') or 'planned'
        if not r.get('topic_id') and r.get('slot_type')=='hotspot':state='unassigned';r['status']='待定题'
        elif state=='published':state='generated'
        if state not in ('planned','ready','generated','failed','unassigned'):raise RuntimeError('Unsupported old production status')
        r['production_status']=state
        records.append((r['id'],r['batch_id'],r['slot_id'],r['account_id'],str(r['publish_date']),week(r['publish_date']),encoded(r),state,r['result_version']))
    tasks=[]
    for kind,rows in [('manual',manual),('marketing',marketing)]:
        for r in rows:
            value=marketing_summary(r) if kind=='marketing' else dict(r)
            if kind=='marketing':
                topics=json.loads(r.get('topic_snapshot_json') or '[]');topics=topics if isinstance(topics,list) else []
                value['archive_detail']={'task':marketing_summary(r),'accounts':json.loads(r.get('account_snapshot_json') or '[]'),'topics':topics}
            tasks.append((f"legacy-{kind}:{r['id']}",r['id'],encoded(value),millis(value['created_at'])))
    failures=[]
    bycode={b['batch_code']:b['id'] for b in batches}
    for failure in cycle_failure_rows(batches,raw):
        failures.append((bycode[failure['batch_code']],failure.get('account_id') or '__batch__',encoded(failure)))
    successful_manual={b['id'] for b in batches if b['plan_type']=='manual' and b['completed_count']>0}
    reservations={(r[4],r[3],r[1]) for r in records if r[1] in successful_manual}
    report={'source_batches':len(batches),'source_items':len(records),'source_operations':len(operations),'archived_tasks':len(tasks),'failures':len(failures),'config_versions':len(config_history),'historical_manual_reservations':len(reservations),'applied':False}
    if apply:
        with pymysql.connect(**java_database_settings()) as db,db.cursor() as c:
            c.execute("SELECT GET_LOCK('strat-matrix:history-migration',5) acquired")
            if c.fetchone()['acquired']!=1:raise RuntimeError('History import already running')
            try:
                batch_rows=[]
                today=datetime.now(__import__('zoneinfo').ZoneInfo('Asia/Shanghai')).date()
                for b in batches:
                    b['runtime_active']=b['cycle_end']>=today and b['plan_type']=='auto' and not b['batch_code'].startswith('DEMO-')
                    batch_rows.append((b['id'],week(b['cycle_start']),encoded(b),millis(b['created_at'])))
                c.executemany('INSERT INTO godp_planning_batch(id,week_start,payload,created_at) VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=VALUES(id)',batch_rows)
                for offset in range(0,len(records),200):
                    c.executemany('INSERT INTO godp_planning_item(id,batch_id,slot_id,account_id,publish_date,publish_week,payload,content_status,version) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=VALUES(id)',records[offset:offset+200])
                if tasks:c.executemany('INSERT INTO godp_planning_task_archive(archive_key,source_id,payload,created_at) VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE archive_key=VALUES(archive_key)',tasks)
                if operations:c.executemany('INSERT INTO godp_planning_adjustment(id,item_id,payload) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE id=VALUES(id)',[(r['id'],r['item_id'],encoded({**r,'created_at':r['create_time'],'created_by':r['create_by']})) for r in operations])
                if failures:c.executemany('INSERT INTO godp_planning_failure(batch_id,account_key,payload) VALUES(%s,%s,%s) ON DUPLICATE KEY UPDATE account_key=VALUES(account_key)',failures)
                if reservations:c.executemany('INSERT IGNORE INTO godp_manual_reservation(publish_date,account_id,task_id) VALUES(%s,%s,%s)',list(reservations))
                for r in records:
                    item=json.loads(r[6]);content_id=item.get('content_id')
                    if item.get('topic_type')=='热点' and item.get('topic_id'):
                        c.execute("INSERT IGNORE INTO godp_planning_resource_claim(resource_kind,resource_key,item_id) VALUES('hotspot',%s,%s)",(r[4]+'|'+item['topic_id'],r[0]))
                    if item.get('topic_type')=='营销' and content_id:
                        c.execute("INSERT IGNORE INTO godp_planning_resource_claim(resource_kind,resource_key,item_id) VALUES('marketing',%s,%s)",(content_id,r[0]))
                        c.execute("INSERT IGNORE INTO godp_planning_resource_claim(resource_kind,resource_key,item_id) VALUES('marketing_day',%s,%s)",(r[3]+'|'+r[4],r[0]))
                import hashlib
                c.execute('SELECT COALESCE(MAX(version),0) version FROM godp_planning_config_release WHERE status=\'completed\'')
                current_version=c.fetchone()['version']
                for h in config_history:
                    if h['version']>=current_version:continue
                    values=json.loads(h['config_json'])
                    canonical=json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                    c.execute("INSERT IGNORE INTO godp_planning_config_release(command_id,version,active_version,status,request_hash,config_json,business_expected_version,algorithm_version,created_by,created_at,action,source_version) VALUES(%s,%s,%s,'completed',%s,%s,1,%s,%s,%s,%s,%s)",
                        ('CONFIG-HISTORY-'+str(h['version']),h['version'],h['version'],hashlib.sha256(canonical.encode()).hexdigest(),encoded(values),h['version'],h['create_by'],str(h['create_time']),h['action'],h.get('source_version')))
                c.execute('SELECT COUNT(*) n FROM godp_planning_item WHERE id<1000000000000');assert c.fetchone()['n']==len(records)
                c.execute('SELECT COUNT(*) n FROM godp_planning_batch WHERE id<1000000000000');assert c.fetchone()['n']==len(batches)
                db.commit();report['applied']=True
            except Exception:db.rollback();raise
            finally:c.execute("SELECT RELEASE_LOCK('strat-matrix:history-migration')")
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='保留ID和状态迁入策划历史，原库保留只读')
    parser.add_argument('--apply',action='store_true');parser.add_argument('--output',type=Path,default=ROOT/'run/history-import-20261103.json')
    args=parser.parse_args();run(args.apply,args.output)
