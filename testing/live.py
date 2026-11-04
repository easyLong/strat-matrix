"""Opt-in outside acceptance: real services/models/databases, simulated bank and content.

Run from the repository root: python -m testing.live --execute
Never part of the default offline regression suite. Credentials stay under run/.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from hashlib import sha256
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

from .datasets import ROOT
from .run import executable
from .account_fixtures import complete_account
from .source_fixtures import install


def stop_child(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        # Own Popen PID only: Maven's forked test JVM must not outlive a timeout.
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()


def free_port():
    with socket.socket() as server:
        server.bind(('127.0.0.1', 0))
        return server.getsockname()[1]


def fixture_for(run_id):
    account_id = f'E2E-CHAIN-{run_id}'
    now = datetime.now(timezone.utc)
    account = dict(account_id=account_id, nickname='全链路验收·家庭理财', owner_um='TESTCHAINUM',
                   organization='测试分行/测试二级分行', platform='小红书', account_type='认证', eligible=True,
                   followers=20, updated_at=now.isoformat(), persona='家庭理财分享者', gender='女',
                   interests=['家庭预算', '储蓄', '金融知识', '银行账户与支付', '家庭工资管理', '账单提醒服务'],
                   expression_style='通俗自然、重视风险提示，分享银行账户和账单服务的正规查询开通方法', interactions=[])
    account=complete_account(account,now=now)
    cases = [
        ('家庭备用金怎么留：先列支出，再确定流动资金', '金融科普', '流量', '用家庭每月必要支出计算备用金，不推荐产品。说明随时可用资金与长期储蓄的边界。'),
        ('工资到账后的家庭记账清单', '财商教育', '流量', '按照必要开支、弹性消费、目标储蓄记录家庭预算；给出可执行的记账步骤。'),
        ('家庭理财先认识风险：本金、期限和流动性', '金融科普', '流量', '解释存款、理财和基金的风险差异；不承诺收益，不推荐具体产品。'),
        ('普通家庭怎样发现不必要的固定开支', '人设故事', '流量', '分享整理账单和核对自动扣费的生活经验，帮助家庭建立节约习惯。'),
        ('存款保险是什么，家庭储蓄需要知道哪些边界', '金融科普', '流量', '解释存款保险保障范围与限额，强调以官方信息为准，不做投资建议。'),
        ('年底家庭财务盘点：把资产、负债、保障写清楚', '财商教育', '流量', '提供家庭财务整理清单，用浅显语言解释资产负债结构，不推荐金融产品。'),
        ('日常储蓄怎么选：按用钱时间比较活期与定期', '产品权益种草', '转化', '为已有储蓄需求的家庭提供选择步骤：明确期限和应急需求，核对存款产品规则、支取条件，再通过银行官方渠道查询办理。不得承诺收益。'),
        ('家庭工资管理工具怎么选：先比较费用与提醒功能', '三公里好物种草', '转化', '帮助家庭对比官方工资管理和账单工具的费用、提醒和授权规则，给出在官方渠道查询开通的步骤，不夸大权益。'),
        ('家庭保障配置前的四项准备：成员、预算、责任、期限', '产品权益种草', '转化', '面向已有保障需求的家庭，说明核对责任、免责、等待期及预算的方法，提供官方咨询和办理前核对清单，避免误导。'),
        ('日常支付工具怎么选：核对收费、限额与安全设置', '产品权益种草', '转化', '比较官方支付工具的收费、支付限额和安全设置，给出查询、选择及设置步骤，引导使用银行官方渠道。'),
        ('目标储蓄账户如何选择和开通：费用与取用条件先核对', '三公里好物种草', '转化', '针对有明确储蓄目标的家庭，比较官方账户服务的费用、资金取用和管理功能，解释申请前准备资料、官方查询及开通步骤。'),
        ('家庭账单提醒服务开通前要核对什么', '产品权益种草', '转化', '帮助家庭按实际需求选择账单提醒服务，核对通知方式、费用、授权范围，说明如何通过官方渠道查询和开通。'),
    ]
    topics = [dict(topic_id=f'{account_id}-T{i:02}', source='普通', topic_type='非营销', title=title,
                   outline=outline, content_type=content_type, heat=50+i, available=True,
                   valid_from=(now-timedelta(days=1)).isoformat(), valid_to=(now+timedelta(days=730)).isoformat(),
                   updated_at=now.isoformat(), related_product='', related_activity='', related_hotspot='')
              for i, (title, content_type, _role, outline) in enumerate(cases, 1)]
    # Intent labels above describe fixture intent, not injected T2 model outputs.
    return dict(accounts=[account], topics=topics)


def fresh_fixture_for(run_id):
    """Fresh business examples, not cache deletion or prompt-version overrides."""
    fixture=fixture_for(run_id)
    income=12000+int(run_id[-4:])%6000
    spending=4000+int(run_id[-3:])%2000
    fixture['accounts'][0]['persona']='家庭财务与银行账户服务讲解者，擅长家庭预算、储蓄知识、账户支付、账单与工资提醒服务的选择及官方申请流程'
    fixture['accounts'][0]['interests'].append(f'月收入{income}元家庭的预算管理')
    for index,topic in enumerate(fixture['topics'],1):
        topic['outline']+=f' 示例家庭月收入{income}元、必要支出{spending}元，结合此预算说明第{index}项核对步骤。'
    services=('账单提醒服务','工资到账提醒服务','银行电子账单服务','银行卡交易通知服务','家庭目标储蓄账户','银行卡支付安全提醒服务')
    for topic,service in zip(fixture['topics'][6:],services):
        topic.update(title=f'{service}开通指南：选择方案、提交申请与确认启用',related_product=service,
            outline=f'面向已经决定开通{service}的用户，展示银行官方页面选择服务、核对费用、填写申请、确认授权并提交开通的完整操作路径。'
                    f'以月收入{income}元的家庭为使用案例，提供服务开通入口、申请前准备材料和开通成功后的设置核对清单。'
                    '引导读者通过银行官方渠道立即完成申请与启用，不承诺收益，不使用非官方链接。')
    return fixture


def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def label_snapshot(cursor, excluded=()):
    cursor.execute('SELECT * FROM godp_topic_label_job ORDER BY id')
    return {str(row['id']):sha256(json.dumps(row,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
            for row in cursor.fetchall() if row['topic_id'] not in excluded}


def check_label_isolation(cursor, baseline):
    current=label_snapshot(cursor)
    changed=[identity for identity,digest in baseline.items() if current.get(identity)!=digest]
    return dict(status='passed' if not changed else 'failed',preserved_job_count=len(baseline),changed_job_count=len(changed))


def main(argv=None):
    harness_started=time.perf_counter()
    parser = argparse.ArgumentParser(description='真实V19与双库全链路验收；会调用模型并创建明确标识的测试结果')
    parser.add_argument('--execute', action='store_true', help='显式执行，不属于离线回归')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', type=Path, help='恢复本工具未提交的测试周期，保留冻结输入和模型缓存')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--scenario', choices=('ordinary','mixed'), help='默认ordinary；mixed验收真实V19提案后的营销引用和热点T-1')
    parser.add_argument('--measure',action='store_true',help='独立验收进程记录不含输入/SQL/密钥的步骤计时')
    parser.add_argument('--fresh-cases',action='store_true',help='使用新家庭预算案例；保留正常缓存，不清空已有缓存')
    parser.add_argument('--benchmark-mode',choices=('baseline','optimized'),help='测量专用对照装配，不修改模型/规则')
    parser.add_argument('--case-file',type=Path,help='复用原始业务案例，仅替换测试标识和更新时间')
    args = parser.parse_args(argv)
    if args.benchmark_mode and not args.measure:parser.error('benchmark-mode requires --measure')
    if not args.execute:
        parser.error('实际调用模型和写入测试数据须显式使用 --execute')
    sys.path.insert(0, str(ROOT/'python-backend'))
    from app.deployment_environment import current
    from app.db import connection
    from app.java_development import java_database_settings, properties_text
    from app.system_config import get_setting
    if current()['PLANNING_ENV'] != 'outside':
        raise ValueError('Full chain acceptance is outside-only')
    gateway=(get_setting('JAVA_GATEWAY_URL','') or 'http://127.0.0.1:6931').rstrip('/')
    health=request(gateway+'/api/plan/service-health')
    if health.get('local_scheduler_enabled') is not False:
        raise ValueError('Pause daily Java local pulse before full-chain acceptance')
    own_topics=([row['topic_id'] for row in json.loads((args.resume/'fixture.json').read_text(encoding='utf-8'))['topics']] if args.resume else [])
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) n FROM godp_planning_pipeline_run WHERE status IN ('pending','waiting','running')")
        if cursor.fetchone()['n'] and not args.resume:
            raise ValueError('Another planning pipeline is active; finish it before acceptance')
        cursor.execute("SELECT topic_id FROM godp_topic_label_job WHERE status='processing' AND lease_expires_at>UTC_TIMESTAMP(6)")
        if any(row['topic_id'] not in own_topics for row in cursor.fetchall()):
            raise ValueError('Unrelated model workers are active; wait for them before acceptance')
        baseline_labels=label_snapshot(cursor,own_topics)
        cursor.execute("SELECT cycle_start FROM godp_planning_pipeline_run UNION SELECT cycle_start FROM godp_ai_preparation")
        occupied = {r['cycle_start'] for r in cursor.fetchall()}
    run_id = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S')
    output = (args.resume or args.output or ROOT/'run/full-chain'/run_id).resolve()
    if output.exists() and any(output.iterdir()) and not args.resume:
        raise ValueError('Output directory must be new')
    if args.resume and (output/'business.json').exists():
        raise ValueError('Business acceptance already closed; rerun python -m testing.live_verify on this directory')
    output.mkdir(parents=True,exist_ok=True)
    baseline_file=output/'unrelated-label-baseline.json'
    if baseline_file.exists():baseline_labels=json.loads(baseline_file.read_text(encoding='utf-8'))
    else:baseline_file.write_text(json.dumps(baseline_labels,indent=2),encoding='utf-8')
    previous_server=json.loads((output/'server.json').read_text(encoding='utf-8')) if args.resume else {}
    previous_scenario = previous_server.get('scenario','ordinary')
    if args.resume:
        if args.benchmark_mode and args.benchmark_mode!=previous_server.get('benchmark_mode'):
            raise ValueError('Resume cannot change benchmark mode')
        args.benchmark_mode=previous_server.get('benchmark_mode')
    benchmark_namespace=previous_server.get('benchmark_namespace') if args.resume else run_id if args.benchmark_mode else None
    if args.resume and args.scenario and args.scenario != previous_scenario:
        raise ValueError('Resume cannot change the original content scenario')
    args.scenario = previous_scenario if args.resume else (args.scenario or 'ordinary')
    fixture = (json.loads((output/'fixture.json').read_text(encoding='utf-8')) if args.resume
               else fresh_fixture_for(run_id) if args.fresh_cases else fixture_for(run_id))
    if args.case_file and not args.resume:
        from .benchmark import clone_fixture
        fixture=clone_fixture(json.loads(args.case_file.read_text(encoding='utf-8')),run_id)
    from .benchmark import case_fingerprint
    fingerprint=case_fingerprint(fixture)
    (output/'fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
    from app.bank_bridge.java_http import JavaHTTPClient
    from app.bank_bridge.contracts import AccountQuery, Page, Account
    from urllib.parse import urlsplit
    source_client = JavaHTTPClient.from_settings()
    address = urlsplit(source_client.base_url)
    if address.scheme != 'http' or address.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('Outside acceptance requires the daily loopback Java source facade')
    # Fail before publishing new test data if daily Java is not ready or still uses the old jar.
    source_client.read('accounts', AccountQuery(page_size=1), Page[Account])
    python_port = free_port()
    today=datetime.now(ZoneInfo('Asia/Shanghai')).date()
    cycle = today+timedelta(days=(7-today.weekday()) % 7 or 7)
    while cycle in occupied:
        cycle += timedelta(days=7)
    if args.scenario == 'mixed' and not args.resume:
        # Select test dates that exercise all branches; never change the policy, frozen roles or thresholds.
        import random
        from app.planning_result_commit import _hotspot_seed
        from app.services.configuration import get_config
        config=get_config()
        while random.Random(_hotspot_seed(cycle.isoformat(),config.version)).sample(range(3),1)[0] == 0 or cycle in occupied:
            cycle += timedelta(days=7)
    if args.resume:
        progress=json.loads((output/'progress.json').read_text(encoding='utf-8'))
        with connection() as db,db.cursor() as cursor:
            cursor.execute('SELECT cycle_start,selection_json,production_batch_id,commit_owner,status FROM godp_planning_pipeline_run WHERE id=%s',(progress['pipeline_id'],))
            owned=cursor.fetchone()
        if not owned or json.loads(owned['selection_json']) != [fixture['accounts'][0]['account_id']] or owned['commit_owner']!='java' or owned['status'] in ('failed','cancelled'):
            raise ValueError('Resume must own an active or acknowledgement-pending acceptance pipeline')
        cycle=owned['cycle_start']
        (output/'java-ready.json').unlink(missing_ok=True)
        for filename in ('java.log','python.log','failure.json'):
            path=output/filename
            if path.exists():path.rename(output/(filename+'.'+run_id))
    install(fixture)
    trigger = datetime.combine(cycle-timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc).replace(hour=14)
    # UTC Tuesday 14:00 = Beijing Tuesday 22:00, due cycle is the following Monday.
    java_db = java_database_settings()
    settings = {
        'planning.manual.jdbc-url':f"jdbc:mysql://{java_db['host']}:{java_db['port']}/{java_db['database']}?characterEncoding=UTF-8&serverTimezone=UTC",
        'planning.manual.username':java_db['user'],'planning.manual.password':java_db['password'],
        'planning.legacy.base-url':f'http://127.0.0.1:{python_port}',
        'planning.legacy.integration-token':get_setting('INTEGRATION_TOKEN'),
        'acceptance.java-source':source_client.base_url,'acceptance.output':str(output),
        'acceptance.trigger':trigger.isoformat().replace('+00:00','Z'),'acceptance.timeout-seconds':str(args.timeout),
        'acceptance.account-id':fixture['accounts'][0]['account_id'],
        'acceptance.resume':str(bool(args.resume)).lower(),
        'acceptance.scenario':args.scenario,'acceptance.java-token':source_client.token,
        'acceptance.measure':str(args.measure).lower(),
        'acceptance.fixture-path':str(ROOT/'run/bank-source-fixture.json'),
    }
    private = output/'private.properties'
    private.write_text(properties_text(settings),encoding='ascii');private.chmod(0o600)
    server_config = output/'server.json'
    server_config.write_text(json.dumps(dict(java_source=source_client.base_url, python_port=python_port,scenario=args.scenario,
        account_id=fixture['accounts'][0]['account_id'], topic_ids=[row['topic_id'] for row in fixture['topics']],
        measure=args.measure,benchmark_mode=args.benchmark_mode,benchmark_namespace=benchmark_namespace)),encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT),str(ROOT/'python-backend')]), PYTHONIOENCODING='utf-8')
    if not env.get('JAVA_HOME'):
        candidates=list((ROOT/'.tmp-tools/jdk').glob('*/bin/java.exe'))
        if candidates: env['JAVA_HOME']=str(candidates[-1].parent.parent)
    maven = executable('mvn')
    java_process = python_process = None
    timing=dict(started_at=datetime.now(timezone.utc).isoformat(),fresh_cases=args.fresh_cases,
                benchmark_mode=args.benchmark_mode,case_fingerprint=fingerprint)
    try:
        with (output/'java.log').open('w',encoding='utf-8') as java_log, (output/'python.log').open('w',encoding='utf-8') as python_log:
            java_started=time.perf_counter()
            java_process=subprocess.Popen([maven,'-o','-q','-Dtest=OutsideFullChainAcceptanceTest',
                f'-Dplanning.full-chain-properties={private}','test'],cwd=ROOT/'java-backend',env=env,stdout=java_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+90
            while not (output/'java-ready.json').exists():
                if java_process.poll() is not None: raise RuntimeError('Java acceptance driver startup failed; see java.log')
                if time.monotonic()>deadline: raise TimeoutError('Java acceptance driver startup timed out')
                time.sleep(.5)
            timing['maven_until_test_ready_s']=round(time.perf_counter()-java_started,6)
            python_process=subprocess.Popen([sys.executable,'-m','testing.live_server','--config',str(server_config)],cwd=ROOT,env=env,stdout=python_log,stderr=subprocess.STDOUT)
            previous=None;deadline=time.monotonic()+args.timeout+60
            while java_process.poll() is None:
                if python_process.poll() is not None:raise RuntimeError('Python acceptance API stopped; see python.log')
                progress=output/'progress.json'
                if progress.exists():
                    try: value=json.loads(progress.read_text(encoding='utf-8'))
                    except ValueError: value={}
                    if value!=previous:print(json.dumps(value,ensure_ascii=True),flush=True);previous=value
                    if value.get('error') == 'Conflict':
                        with connection() as db, db.cursor() as cursor:
                            cursor.execute('SELECT t.result_json FROM godp_matching_task t JOIN godp_planning_pipeline_run p '
                                           'ON p.matching_task_id=t.id WHERE p.id=%s', (value.get('pipeline_id'),))
                            row=cursor.fetchone()
                        if row and row['result_json'] and any(p['outcome']=='failed' for p in json.loads(row['result_json'])['positions']):
                            raise RuntimeError('V19 produced unassigned positions; formal commit correctly blocked')
                if time.monotonic()>deadline:raise TimeoutError('Full chain acceptance timed out')
                time.sleep(1)
            if java_process.returncode: raise RuntimeError('Java acceptance failed; see java.log and progress.json')
            timing['java_driver_s']=round(time.perf_counter()-java_started,6)
        result=json.loads((output/'business.json').read_text(encoding='utf-8'))
        assert result['status']=='passed'
        with connection() as db, db.cursor() as cursor:
            isolation=check_label_isolation(cursor,baseline_labels)
        (output/'isolation.json').write_text(json.dumps(isolation,indent=2),encoding='utf-8')
        if isolation['status']!='passed':raise RuntimeError('Acceptance modified unrelated label jobs')
        from .live_verify import verify
        if args.measure:
            from .timing import Recorder
            from . import live_verify
            recorder=Recorder(output/'page-timings.jsonl')
            original=live_verify.read
            live_verify.read=recorder.wrap(lambda base,path,payload:'page.'+(
                payload.get('mode','usage') if path=='/query/plans' else payload.get('format','usage')),original)
            try:verify(output)
            finally:live_verify.read=original
        else:verify(output)
        print(json.dumps({'status':'passed','output':str(output),'batch_id':result['business_batch_id'],'account_id':result['account_id']},ensure_ascii=True),flush=True)
        return 0
    except Exception as error:
        (output/'failure.json').write_text(json.dumps({'status':'failed','error_type':type(error).__name__},ensure_ascii=True),encoding='utf-8')
        print(f'Acceptance failed: {type(error).__name__}; logs: {output}',flush=True)
        return 1
    finally:
        for process in (python_process,java_process):
            stop_child(process)
        if args.measure:
            timing['harness_total_s']=round(time.perf_counter()-harness_started,6)
            (output/'harness-timings.json').write_text(json.dumps(timing,indent=2),encoding='utf-8')


if __name__=='__main__':
    raise SystemExit(main())
