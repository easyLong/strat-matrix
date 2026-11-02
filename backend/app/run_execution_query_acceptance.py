"""Explicit development-only acceptance for recovery and unified result reads."""
import argparse
import csv
from datetime import date,timedelta
import io
import json
from pathlib import Path
from unittest.mock import patch
import pymysql
from fastapi.testclient import TestClient

from .db import connection
from .bank_bridge.factory import source_mode
from .bootstrap import app
from .models import ManualPreviewInput
from .services import manual_planning as manual,manual_tasks as tasks
from .services.plan_queries import PlanQuery,plan_page
from .services.list_queries import PageQuery
from .services.result_lists import period_page
from .run_shared_workflow_acceptance import check_no_retired_sql

ACCOUNT='E2E-ORD-ACCOUNT-001'
TOPIC='E2E-ORD-TOPIC-001'

def submit(day,name):
    with connection() as db,db.cursor() as cursor:
        cursor.execute("SELECT *,create_time created_at,create_by created_by,update_time updated_at FROM godp_manual_task "
                       "WHERE task_name=%s AND publish_date=%s AND status='执行中' ORDER BY id DESC LIMIT 1",(name,day))
        existing=cursor.fetchone()
    if existing:return existing
    preview=manual.preview_manual_plan(ManualPreviewInput(task_name=name,content_mode='non_marketing',
        publish_date=day,account_ids=[ACCOUNT],topic_ids=[TOPIC]))
    task=manual.submit_manual_preview(preview['preview_id'])
    assert task['batch_id'] is None
    return task

def run(day,output):
    if source_mode()!='local_fixture':raise RuntimeError('Acceptance requires explicit development fixtures')
    report={'date':str(day),'source':source_mode(),'checks':[]}
    with patch('pymysql.cursors.DictCursor.execute',new=check_no_retired_sql()):
        first=submit(day,'ARCH-DURABLE-RECOVERY-'+str(day))
        old=tasks.claim_task(first['id'])
        with connection() as db,db.cursor() as cursor:
            cursor.execute('UPDATE godp_manual_task SET lease_expires_at=UTC_TIMESTAMP()-INTERVAL 1 MINUTE WHERE id=%s',(first['id'],))
            cursor.execute('UPDATE godp_manual_preview SET expires_at=UTC_TIMESTAMP()-INTERVAL 1 DAY WHERE preview_code=%s',(first['preview_code'],))
            db.commit()
        current=tasks.claim_task(first['id'])
        assert current['execution_token']!=old['execution_token']
        assert tasks.finish_claim(old)['status']=='stale'
        done=tasks.finish_claim(current)
        assert done['status']=='completed'
        assert tasks.finish_claim(current)['status']=='stale'
        assert manual.submit_manual_preview(first['preview_code'])['id']==first['id']
        report['checks']+=['expired_lease_reclaimed','stale_execution_rejected','accepted_preview_survives_expiry','duplicate_submission_reused']
        second=submit(day+timedelta(days=1),'ARCH-DURABLE-ROLLBACK-'+str(day))
        original=manual.insert_manual_batch
        def fail_after_writes(*args,**kwargs):
            original(*args,**kwargs)
            raise pymysql.OperationalError(2013,'injected connection interruption')
        with patch.object(manual,'insert_manual_batch',side_effect=fail_after_writes):
            retry=tasks.run_once(second['id'])
        assert retry['retrying']==1
        with connection() as db,db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) n FROM godp_planning_item WHERE account_id=%s AND publish_date=%s AND batch_id IN '
                           "(SELECT id FROM godp_planning_batch WHERE plan_type='manual')",(ACCOUNT,day+timedelta(days=1)))
            assert cursor.fetchone()['n']==0
            cursor.execute('UPDATE godp_manual_task SET next_attempt_at=NULL WHERE id=%s',(second['id'],));db.commit()
        assert tasks.run_once(second['id'])['completed']==1
        report['checks']+=['failed_transaction_rolled_back','transient_failure_retried']
        week=day-timedelta(days=day.weekday());end=week+timedelta(days=6)
        period=period_page(PageQuery(filters={'startDate':str(week),'endDate':str(end)}))['items'][0]
        query=PlanQuery(mode='cycle',cycle_start=week,cycle_end=end)
        detail=plan_page(query)
        assert period['accountCount']==detail['summary']['accounts']
        assert period['autoAccountCount']+period['manualAccountCount']>period['accountCount']
        client=TestClient(app)
        exported=client.post('/api/query/export',json=query.model_dump(mode='json'))
        assert exported.status_code==200
        rows=list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
        assert len(rows)==len(detail['items'])
        filtered=query.model_copy(update={'filters':{'start':str(day),'end':str(day),'planType':'manual'}})
        filtered_rows=list(csv.DictReader(io.StringIO(client.post('/api/query/export',json=filtered.model_dump(mode='json')).content.decode('utf-8-sig'))))
        assert len(filtered_rows)==1
        assert filtered_rows[0]['选题ID']==TOPIC
        assert detail['summary']==plan_page(query.model_copy(update={'page_size':1}))['summary']
        report['checks']+=['cross_batch_account_deduplicated','list_detail_export_same_scope','date_and_mode_filter_consistent','summary_independent_of_page']
        report.update(status='passed',task_ids=[first['id'],second['id']],batch_id=done['batch_id'],
                      period_account_count=period['accountCount'],export_rows=len(rows),content_production='not_triggered')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--publish-date',type=date.fromisoformat,required=True)
    parser.add_argument('--output',type=Path,default=Path('../run/execution-query-acceptance.json'))
    args=parser.parse_args();run(args.publish_date,args.output)

if __name__=='__main__':main()
