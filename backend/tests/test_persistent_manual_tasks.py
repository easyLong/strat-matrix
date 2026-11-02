"""Durable-task behavior independent of model services or a live database."""
from contextlib import contextmanager
from datetime import datetime,timedelta
import unittest
from unittest.mock import MagicMock,patch
from app.services import manual_tasks as tasks
from app.services.errors import ApplicationError
from app.jobs.worker import execute
from app.services.result_scope import ResultQuery,compile_scope
from app.services.result_lists import account_matches

class PersistentTaskTests(unittest.TestCase):
    def database(self,cursor):
        @contextmanager
        def db():
            value=MagicMock();value.cursor.return_value.__enter__.return_value=cursor
            yield value
        return db

    def test_business_rejection_is_terminal_and_token_guarded(self):
        cursor=MagicMock();cursor.rowcount=1
        job={'id':3,'execution_token':'new-claim','attempt_count':1}
        with patch.object(tasks,'connection',self.database(cursor)):
            result=tasks.record_failure(job,ApplicationError(409,'选题已失效'))
        sql,params=cursor.execute.call_args.args
        self.assertEqual(result['status'],'failed');self.assertEqual(params[0],'执行失败')
        self.assertIn('execution_token=%s',sql);self.assertIn('lease_expires_at>UTC_TIMESTAMP(6)',sql)
        self.assertEqual(params[-1],'new-claim')

    def test_transient_failure_retries_but_attempt_budget_is_finite(self):
        for attempt,expected in ((1,'retrying'),(tasks.MAX_ATTEMPTS,'failed')):
            cursor=MagicMock();cursor.rowcount=1
            with patch.object(tasks,'connection',self.database(cursor)):
                result=tasks.record_failure({'id':3,'execution_token':'x','attempt_count':attempt},RuntimeError('private database details'))
            self.assertEqual(result['status'],expected)
            self.assertNotIn('private database details',str(cursor.execute.call_args.args))

    def test_obsolete_worker_cannot_write_failure_over_new_claim(self):
        cursor=MagicMock();cursor.rowcount=0
        with patch.object(tasks,'connection',self.database(cursor)):
            result=tasks.record_failure({'id':3,'execution_token':'old','attempt_count':1},RuntimeError())
        self.assertEqual(result['status'],'stale')

    def test_processing_and_results_are_scoped_to_requested_task(self):
        job={'id':7,'execution_token':'x','attempt_count':1}
        with patch.object(tasks,'claim_task',return_value=job) as claim,patch.object(tasks,'finish_claim',return_value={'status':'completed','task_id':7}):
            result=tasks.run_once(7,limit=10)
        claim.assert_called_once_with(7);self.assertEqual(result['completed'],1)

    def test_job_wrapper_reports_nested_business_failure(self):
        for result in ({'status':'failed'},{'pipelines':[{'pipeline_id':1,'status':'failed'}]},{'pipelines':[{'error':'dependency'}]}):
            self.assertEqual(execute('manual',lambda:result)['status'],'failed')

    def test_empty_explicit_scope_is_empty_not_all_results(self):
        where,params,_,_=compile_scope(ResultQuery(mode='all',batch_ids=[]))
        self.assertIn('0=1',where);self.assertEqual(params,[])

    def test_export_and_details_use_the_same_range_and_plan_type(self):
        query=ResultQuery(mode='cycle',cycle_start='2026-11-02',cycle_end='2026-11-08',
            batch_ids=[1,2],filters={'start':'2026-11-04','end':'2026-11-04','planType':'manual'})
        where,params,_,_=compile_scope(query)
        self.assertIn('b.plan_type=%s',where);self.assertEqual(params[-1],'manual')
        self.assertEqual(sum('publish_date' in value for value in where),2)

    def test_account_filter_range_and_owner_are_literal(self):
        account={'followers':80,'um_no':'UM-1','account_type':'认证'}
        self.assertTrue(account_matches(account,{'followersMin':50,'followersMax':100,'umNo':'um-1'}))
        self.assertFalse(account_matches(account,{'followersMin':100}))
        self.assertFalse(account_matches(account,{'umNo':'um-2'}))

if __name__=='__main__':unittest.main()
