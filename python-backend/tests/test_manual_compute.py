import unittest
from app.content_planning.manual_compute import ComputeInput, allocate


class ManualComputeTests(unittest.TestCase):
    def payload(self):
        return dict(request_id='JMAN-test', algorithm_version='frozen-v1',
                    accounts=[{'account_id':'A1','lifecycle_stage':'growth'},{'account_id':'A2'}],
                    topics=[{'topic_id':'T1','is_marketing':False},{'topic_id':'T2','is_marketing':False}])

    def test_retries_are_deterministic_and_stay_within_selection(self):
        payload=ComputeInput(**self.payload())
        first=allocate(payload)
        self.assertEqual(first,allocate(payload))
        self.assertEqual({'A1','A2'},{r['account_id'] for r in first['items']})
        self.assertTrue(all(r['topic_id'] in {'T1','T2'} for r in first['items']))
        self.assertEqual('frozen-v1',first['algorithm_version'])

    def test_duplicate_accounts_and_marketing_are_rejected(self):
        payload=self.payload();payload['accounts']*=2
        with self.assertRaises(ValueError):ComputeInput(**payload)
        payload=self.payload();payload['topics'][0]['is_marketing']=True
        with self.assertRaises(ValueError):ComputeInput(**payload)

    def test_compute_does_not_depend_on_business_database(self):
        import inspect,app.content_planning.manual_compute
        source=inspect.getsource(app.content_planning.manual_compute)
        for table in ('godp_manual_task','godp_planning_batch','godp_planning_item','godp_slot_state'):
            self.assertNotIn(table,source)


if __name__=='__main__':unittest.main()
