"""Read-only smoke test of the daily Java facts -> Python -> Java page chain; no model calls."""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

from .datasets import ROOT


def read(url, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['X-Integration-Token'] = token
    request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def verify(base='http://127.0.0.1:930'):
    sys.path.insert(0, str(ROOT/'python-backend'))
    from app.content_planning.bank_bridge.factory import get_source
    from app.content_planning.bank_bridge.bridge import collect
    from app.content_planning.bank_bridge.contracts import AccountQuery, TopicQuery
    from app.content_planning.bank_bridge.java_http import JavaHTTPClient
    from app.content_planning.system_config import get_setting
    from app.content_planning.deployment_environment import current
    if current()['PLANNING_ENV'] != 'outside':
        raise ValueError('Source smoke verification is outside-only')
    source = get_source(None)
    accounts = list(collect(source, 'accounts', AccountQuery(page_size=17)))
    topics = list(collect(source, 'topics', TopicQuery(page_size=13)))
    client = JavaHTTPClient.from_settings()
    try:
        read(client.base_url+'/accounts/query', {})
    except urllib.error.HTTPError as error:
        assert error.code == 401
        error.close()
    else:
        raise AssertionError('Java facts require the internal token')
    page_accounts = read(base+'/api/accounts?limit=1000')
    page_topics = read(base+'/api/topics?limit=1000')
    expected = {a.account_id: a for a in accounts[:1000]}
    assert {r['account_id'] for r in page_accounts} == set(expected)
    for row in page_accounts:
        a = expected[row['account_id']]
        assert row['account_name'] == a.nickname and row['um_no'] == a.owner_um
        assert row['organization'] == a.organization and row['platform'] == a.platform
        assert row['followers'] == a.followers and row['gender'] == a.gender
        assert row['interests'] == a.interests and row['account_type'] == a.account_type
        assert row['lifecycle_stage']
    assert {r['topic_id'] for r in page_topics} <= {t.topic_id for t in topics}
    detail_checked = False
    if page_topics:
        from urllib.parse import quote
        topic = page_topics[0]
        detail = read(base+'/api/topics/'+quote(topic['topic_id'],safe='')+'/detail')
        assert detail['topic_title'] == topic['topic_title'] and 'labels' in detail
        detail_checked = True
    totals = {}
    for view in ('accounts', 'periods', 'manual-tasks'):
        response = read(base+'/api/query/'+view, dict(page=1,page_size=20,filters={}))
        assert len(response['items']) <= 20
        totals[view] = response['total']
    # Old reverse-source endpoint must not remain a parallel active path.
    host = get_setting('BACKEND_HOST')
    if host in ('0.0.0.0','::'): host='127.0.0.1'
    if ':' in host: host='['+host+']'
    try:
        read(f"http://{host}:{get_setting('BACKEND_PORT')}/api/internal/manual-source",
             dict(account_ids=[],topic_ids=[]),get_setting('INTEGRATION_TOKEN'))
    except urllib.error.HTTPError as error:
        assert error.code == 410
        error.close()
    else:
        raise AssertionError('Old Python facts bridge must be retired')
    return dict(status='passed', java_source=client.base_url, transport='java_http',
                source_accounts=len(accounts),source_topics=len(topics),page_accounts=len(page_accounts),
                page_topics=len(page_topics),query_totals=totals,topic_detail=detail_checked,
                unauthorized_rejected=True,old_source_bridge_retired=True,model_calls=0)


def main():
    parser=argparse.ArgumentParser(description='统一资料链路只读验证，不调用模型、不创建策划')
    parser.add_argument('--base',default='http://127.0.0.1:930')
    parser.add_argument('--output',type=Path,default=ROOT/'run/unified-source/verification.json')
    args=parser.parse_args()
    result=verify(args.base)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
