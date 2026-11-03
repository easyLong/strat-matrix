import json
import pytest
from testing import content_live


def test_content_acceptance_requires_explicit_execute():
    with pytest.raises(SystemExit):content_live.main([])


def test_content_verification_checks_two_batches_accounts_cycle_usage_and_exports(monkeypatch,tmp_path):
    auto=[dict(id=i,account_id='A'+str(i),publish_date='2030-01-09',topic_id='T'+str(i),content_id='C'+str(i),
               production_status='generated',allow_replace=False) for i in range(1,6)]
    manual=[dict(id=i,account_id='A5',publish_date='2030-01-11',topic_id='MARKETING',content_id='C'+str(i),
                 production_status='generated',allow_replace=False) for i in range(6,8)]
    usage=[dict(topic_id='T1',official_use_count=1),dict(topic_id='MARKETING',official_use_count=2)]
    business=dict(prefix='E2E-TEST',scope='formal-business-results-to-simulated-content',auto_batch_id=1,manual_batch_id=2,
                  auto_items=auto,manual_items=manual,account_ids=['A1','A2','A3','A4','A5'],cycle_start='2030-01-07',
                  usage=dict(topic_results=usage),cases=['test'])
    (tmp_path/'business.json').write_text(json.dumps(business),encoding='utf-8')
    def read(_base,path,q):
        if path=='/query/topic-usage':return dict(topic_results=usage)
        records=auto if q.get('batch_id')==1 else manual
        if path=='/query/export':
            return b'PK-test' if q['format']=='xlsx' else ('id\n'+'\n'.join(str(r['id']) for r in records)+'\n').encode()
        if q.get('mode')=='account':records=[r for r in auto+manual if r['account_id']==q['account_id']]
        if q.get('mode')=='cycle':records=auto+manual
        return dict(items=records)
    monkeypatch.setattr(content_live,'read',read)
    assert content_live.verify(tmp_path)['completed_items']==7
    auto[0]['allow_replace']=True
    with pytest.raises(AssertionError):content_live.verify(tmp_path)
