import json

import pytest

from testing.live import fixture_for
from testing import live_verify
from testing.source_fixtures import install


def test_live_facts_have_unique_test_ids_and_no_injected_algorithm_outputs():
    fixture=fixture_for('20261103000000')
    assert len(fixture['accounts'])==1 and len(fixture['topics'])==12
    assert len({row['topic_id'] for row in fixture['topics']})==12
    assert all(row['topic_id'].startswith('E2E-CHAIN-') for row in fixture['topics'])
    assert all(not ({'tags','vector','fit_score'} & row.keys()) for row in fixture['topics'])
    assert len(fixture['accounts'][0]['interactions'])==4
    assert all(row['account_id']==fixture['accounts'][0]['account_id'] for row in fixture['accounts'][0]['interactions'])


def test_source_install_preserves_unrelated_facts_and_rejects_conflicting_ids(tmp_path):
    path = tmp_path/'facts.json'
    path.write_text(json.dumps(dict(accounts=[dict(data=dict(account_id='OLD'))],topics=[])),encoding='utf-8')
    fixture = dict(accounts=[dict(account_id='NEW')],topics=[dict(topic_id='T1')])
    install(fixture,path); install(fixture,path)
    result=json.loads(path.read_text(encoding='utf-8'))
    assert [r['data']['account_id'] for r in result['accounts']]==['OLD','NEW']
    original=path.read_bytes()
    with pytest.raises(ValueError):install(dict(accounts=[dict(account_id='NEW',nickname='changed')],topics=[]),path)
    assert path.read_bytes()==original


def test_live_page_verification_checks_scopes_content_usage_and_both_exports(monkeypatch,tmp_path):
    items=[dict(id=i,topic_id=f'T{i}',publish_date=f'2027-02-{22+i}',topic_title=f'topic {i}',
                production_status='generated',allow_replace=False,content_id=f'SIM-CONTENT-{i}') for i in range(3)]
    business=dict(status='passed',business_batch_id=1,account_id='E2E-CHAIN-A',cycle_start='2027-02-22',items=items)
    (tmp_path/'business.json').write_text(json.dumps(business),encoding='utf-8')
    calls=[]
    def read(_base,path,payload):
        calls.append(path)
        if path=='/query/plans':return dict(items=items)
        if path=='/query/topic-usage':return dict(topic_results=[dict(topic_id=f'T{i}',official_use_count=1) for i in range(3)])
        if payload['format']=='xlsx':return b'PK-test-container'
        return b'topic_id\nT0\nT1\nT2\n'
    monkeypatch.setattr(live_verify,'read',read)
    assert live_verify.verify(tmp_path)['status']=='passed'
    assert calls.count('/query/plans')==3
    assert (tmp_path/'planning.csv').is_file() and (tmp_path/'planning.xlsx').is_file()
    items[0]['production_status']='ready'
    with pytest.raises(AssertionError):live_verify.verify(tmp_path)
