"""Outside content-branch acceptance using daily Java facts, actual business MySQL and simulated content.

Starts at seeded formal business rows. Does not run V19, call models or emulate the real content system.
"""
import argparse
import csv
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

from .datasets import ROOT
from .live_verify import read
from .live import stop_child
from .run import executable
from .source_fixtures import FIXTURE_PATH


def verify(directory, base='http://127.0.0.1:930'):
    directory = Path(directory)
    business = json.loads((directory/'business.json').read_text(encoding='utf-8'))
    pages, exports = {}, []
    for kind, key in (('auto', 'auto_batch_id'), ('manual', 'manual_batch_id')):
        query = dict(page=1, page_size=20, filters={}, mode='batch', batch_id=business[key])
        page = read(base, '/query/plans', query)
        expected = {r['id'] for r in business[kind+'_items']}
        assert {r['id'] for r in page['items']} == expected
        assert all(r['production_status']=='generated' and not r['allow_replace'] and r['content_id'] for r in page['items'])
        data = read(base, '/query/export', dict(query, format='csv'))
        records = list(csv.reader(io.StringIO(data.decode('utf-8-sig'))))
        assert len(records) == len(expected)+1
        (directory/(kind+'.csv')).write_bytes(data)
        excel = read(base, '/query/export', dict(query, format='xlsx'))
        assert excel.startswith(b'PK')
        (directory/(kind+'.xlsx')).write_bytes(excel)
        pages[kind] = page
        exports.append(dict(kind=kind, rows=len(expected), xlsx_container=True))
    for account in business['account_ids']:
        page = read(base, '/query/plans', dict(page=1,page_size=20,filters={},mode='account',account_id=account))
        assert page['items'] and all(r['account_id']==account for r in page['items'])
    cycle = read(base, '/query/plans', dict(page=1,page_size=100,filters={},mode='cycle',
                cycle_start=business['cycle_start'],cycle_end=business['cycle_start']))
    own = {r['id'] for name in ('auto_items','manual_items') for r in business[name]}
    assert own <= {r['id'] for r in cycle['items']}
    topic_ids = [r['topic_id'] for r in business['usage']['topic_results']]
    usage = read(base, '/query/topic-usage', dict(topic_ids=topic_ids))
    expected_usage = {r['topic_id']:r['official_use_count'] for r in business['usage']['topic_results']}
    assert {r['topic_id']:r['official_use_count'] for r in usage['topic_results']} == expected_usage
    summary = dict(status='passed', prefix=business['prefix'],scope=business['scope'],cases=business['cases'],
        auto_batch_id=business['auto_batch_id'],manual_batch_id=business['manual_batch_id'],
        completed_items=len(own),account_count=len(business['account_ids']),exports=exports,
        topic_usage=usage['topic_results'],model_calls=0,real_content_system=False,
        auto_url=f"{base}/results?dimension=period&batch={business['auto_batch_id']}",
        manual_url=f"{base}/results?dimension=period&batch={business['manual_batch_id']}")
    (directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 营销、热点与模拟内容衔接验收','',
        '范围：从测试正式策划明细开始，使用真实Java业务服务、MyBatis/MySQL和日常Java资料入口。',
        '内容方为明确模拟事实；本轮未运行V19、未调用模型，不能作为真实内容系统接入验收。','',
        f"完成 {len(own)} 条策划，涉及 {len(business['account_ids'])} 个账号。",'']
    lines += ['- '+case for case in business['cases']]
    lines += ['',f"[自动批次]({summary['auto_url']})",f"[人工营销批次]({summary['manual_url']})",'',
              '账号、周期、批次查询及CSV行数对账通过；XLSX只核对容器格式。','',
              '| 批次 | 账号 | 投放日期 | 选题ID | 内容ID |','| --- | --- | --- | --- | --- |']
    for kind,page in pages.items():
        for item in page['items']:
            lines.append(f"| {kind} | {item['account_id']} | {item['publish_date']} | {item.get('topic_id') or '—'} | {item['content_id']} |")
        (directory/(kind+'-page.json')).write_text(json.dumps(page,ensure_ascii=False,indent=2),encoding='utf-8')
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description='营销/热点/模拟内容衔接：会写业务测试数据，不调用模型')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--verify',type=Path,help='只读复核已有验收目录')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--base',default='http://127.0.0.1:930')
    args=parser.parse_args(argv)
    if args.verify:
        print(json.dumps(verify(args.verify,args.base),ensure_ascii=True));return 0
    if not args.execute:parser.error('创建测试资料和正式明细须显式使用 --execute')
    sys.path.insert(0,str(ROOT/'python-backend'))
    from app.deployment_environment import current
    from app.bank_bridge.java_http import JavaHTTPClient
    from app.java_development import java_database_settings,properties_text
    from app.system_config import get_setting
    if current()['PLANNING_ENV']!='outside':raise ValueError('Content acceptance is outside-only')
    with urllib.request.urlopen(args.base+'/api/service-health',timeout=10) as response:
        health=json.load(response)
    if health.get('local_scheduler_enabled') is not False:
        raise ValueError('Pause daily Java local pulse first; this tool never stops services automatically')
    client=JavaHTTPClient.from_settings()
    from urllib.parse import urlsplit
    if urlsplit(client.base_url).hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('Use the daily loopback Java source in outside acceptance')
    run_id=datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S')
    output=(args.output or ROOT/'run/content-branches'/run_id).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('Use a new output directory; partial evidence is preserved')
    output.mkdir(parents=True,exist_ok=True)
    cycle=datetime.now(ZoneInfo('Asia/Shanghai')).date()+timedelta(days=180)
    cycle-=timedelta(days=cycle.weekday())
    db=java_database_settings()
    host=get_setting('BACKEND_HOST')
    if host in ('0.0.0.0','::'):host='127.0.0.1'
    if ':' in host:host='['+host+']'
    values={'planning.manual.jdbc-url':f"jdbc:mysql://{db['host']}:{db['port']}/{db['database']}?characterEncoding=UTF-8&serverTimezone=UTC",
        'planning.manual.username':db['user'],'planning.manual.password':db['password'],
        'planning.legacy.base-url':f"http://{host}:{get_setting('BACKEND_PORT')}",
        'planning.legacy.integration-token':get_setting('INTEGRATION_TOKEN'),
        'acceptance.java-source':client.base_url,'acceptance.java-token':client.token,
        'acceptance.fixture':str(FIXTURE_PATH),'acceptance.output':str(output),
        'acceptance.prefix':'E2E-BRANCH-'+run_id,'acceptance.cycle':cycle.isoformat(),
        'acceptance.batch-id':str(4_000_000_000_000+int(datetime.now().timestamp()*1000))}
    private=output/'private.properties';private.write_text(properties_text(values),encoding='ascii');private.chmod(0o600)
    env=dict(os.environ,PYTHONIOENCODING='utf-8')
    if not env.get('JAVA_HOME'):
        candidates=list((ROOT/'.tmp-tools/jdk').glob('*/bin/java.exe'))
        if candidates:env['JAVA_HOME']=str(candidates[-1].parent.parent)
    with (output/'java.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([executable('mvn'),'-o','-q','-Dtest=OutsideContentBranchesAcceptanceTest',
            f'-Dplanning.content-acceptance-properties={private}','test'],cwd=ROOT/'java-backend',env=env,
            stdout=log,stderr=subprocess.STDOUT)
        try:code=process.wait(timeout=180)
        finally:stop_child(process)
    if code:
        print(json.dumps(dict(status='failed',output=str(output),reason='See private java.log; partial test evidence preserved')));return 1
    print(json.dumps(verify(output,args.base),ensure_ascii=True));return 0


if __name__=='__main__':raise SystemExit(main())
