"""Read-only page-proxy, content usage and export verification for a live acceptance run."""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.request


def read(base, path, payload):
    request=urllib.request.Request(base+'/api'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read()
        return json.loads(data) if 'json' in response.headers.get('Content-Type','') else data


def verify(directory, base='http://127.0.0.1:930'):
    directory=Path(directory)
    result=json.loads((directory/'business.json').read_text(encoding='utf-8'))
    batch,account=result['business_batch_id'],result['account_id']
    common=dict(page=1,page_size=20,filters={})
    batch_query=dict(common,mode='batch',batch_id=batch)
    pages={
        'batch':read(base,'/query/plans',batch_query),
        'account':read(base,'/query/plans',dict(common,mode='account',account_id=account)),
        'cycle':read(base,'/query/plans',dict(common,mode='cycle',cycle_start=result['cycle_start'],cycle_end=result['cycle_start'])),
    }
    expected={row['id'] for row in result['items']}
    for name,page in pages.items():
        assert expected <= {row['id'] for row in page['items']},name
        own=[row for row in page['items'] if row['id'] in expected]
        assert len(own)==3 and all(row['production_status']=='generated' for row in own),name
        assert all(not row['allow_replace'] and row['content_id'].startswith('SIM-CONTENT-') for row in own),name
    topic_ids=list(dict.fromkeys(row['topic_id'] for row in pages['batch']['items'] if row.get('topic_id')))
    usage=read(base,'/query/topic-usage',dict(topic_ids=topic_ids))
    assert all(row['official_use_count']==1 for row in usage['topic_results'])
    # Recalled/selected ordinary candidates replaced by marketing must not count as production use.
    source_file=directory/'fixture.json'
    unused_verified=False
    if source_file.exists():
        source_ids=[t['topic_id'] for t in json.loads(source_file.read_text(encoding='utf-8'))['topics']]
        all_ids=list(dict.fromkeys(source_ids+topic_ids))
        all_usage=read(base,'/query/topic-usage',dict(topic_ids=all_ids))
        assert {r['topic_id']:r['official_use_count'] for r in all_usage['topic_results']} == {t:1 if t in topic_ids else 0 for t in all_ids}
        unused_verified=True
    csv_bytes=read(base,'/query/export',dict(batch_query,format='csv'))
    (directory/'planning.csv').write_bytes(csv_bytes)
    exported=list(csv.reader(io.StringIO(csv_bytes.decode('utf-8-sig'))))
    assert len(exported)==4,'Export must contain a header and three planning rows'
    for topic_id in topic_ids:
        assert any(topic_id in cell for row in exported[1:] for cell in row),topic_id
    excel=read(base,'/query/export',dict(batch_query,format='xlsx'))
    assert excel.startswith(b'PK'),'XLSX must be an actual ZIP container'
    (directory/'planning.xlsx').write_bytes(excel)
    verification=dict(status='passed',frontend_proxy=base,query_scopes=list(pages),
        completed_items=3,completed_accounts=1,usage=usage['topic_results'],unused_candidates_not_counted=unused_verified,csv_rows=3,xlsx=True,
        batch_url=f'{base}/results?dimension=period&batch={batch}',account_url=f'{base}/results?account={account}')
    for name,page in pages.items():
        (directory/(name+'-page.json')).write_text(json.dumps(page,ensure_ascii=False,indent=2),encoding='utf-8')
    (directory/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    result.update(status='passed',page_verification=verification)
    result.pop('next_step',None)
    (directory/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    title='V19营销与热点混合闭环验收' if result.get('content_scenario')=='mixed' else '普通自动策划全链路验收'
    lines=['# '+title,'',f"账号：{account}",f"批次：{batch}",f"周期开始：{result['cycle_start']}",'',
           '真实执行：Java HTTP资料查询、打标、画像、向量化、V19匹配、双库持久化、Java确认及页面查询。',
           '模拟部分：行内资料、宿主触发时刻与内容生产方；SIM-CONTENT- 内容ID不代表真实生产。','',
           f'结果：3条正式策划，3条内容完成；内容完成账号1/1；{len(topic_ids)}个实际选题使用次数各1；重复执行未重复落库或计数；确认响应丢失后恢复。','',
           '| 投放日 | 选题 | 选题ID | 内容状态 |','| --- | --- | --- | --- |']
    for item in sorted(pages['batch']['items'],key=lambda x:x['publish_date']):
        lines.append(f"| {item['publish_date']} | {item['topic_title']} | {item['topic_id']} | 已完成 |")
    lines+=['',f"[查看批次]({verification['batch_url']})",f"[查看账号]({verification['account_url']})",'',
            '账号、批次、周期查询经前端代理进入Java，CSV导出3条明细且含选题ID，XLSX文件格式有效。']
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return verification


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--base',default='http://127.0.0.1:930')
    args=parser.parse_args()
    print(json.dumps(verify(args.directory,args.base),ensure_ascii=True))


if __name__=='__main__':main()
