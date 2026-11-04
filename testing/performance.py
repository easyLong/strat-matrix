"""Offline duration analysis of opt-in real acceptance traces; no DB/model access."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime
import csv
import json
from pathlib import Path
from statistics import mean,median


STEPS=[
 ('source.discovery','资料发现与任务入队'),('preparation.create','原始资料快照与准备任务'),
 ('input.labels','选题T1–T6打标及T6向量'),('input.topic_vectors','选题画像向量'),
 ('account.profile','账号画像规则计算'),('input.account_vectors','账号画像向量'),
 ('matching.freeze','匹配输入冻结'),('matching.annotations','V19主关联标签补充'),
 ('matching.mapping','账号标签映射'),('matching.need_vector','需求语义向量/缓存'),
 ('matching.recall','五路召回'),('matching.precision','模型精判'),('matching.allocation','容量与组合分配'),
 ('java.proposal_fetch','提案读取与校验'),('java.business_transaction','正式结果业务事务'),
 ('java.acknowledge','Java→Python落库确认'),('java.simulated_content_status','模拟内容状态读取与对账'),
 ('java.usage_query','选题使用次数查询'),('page.batch','批次页面查询'),
 ('page.account','账号页面查询'),('page.cycle','周期页面查询'),
 ('page.csv','CSV导出'),('page.xlsx','XLSX导出'),
]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []


def intervals_union(intervals):
    total=0.;left=right=None
    for start,end in sorted(intervals):
        if end<start:raise ValueError('Invalid timing interval')
        if left is None:left,right=start,end
        elif start<=right:right=max(right,end)
        else:total+=right-left;left,right=start,end
    return total+(right-left if left is not None else 0.)


def epoch(event):
    return datetime.fromisoformat(event['started_at'].replace('Z','+00:00')).timestamp()


def stats(events):
    values=[e['duration_s'] for e in events]
    return dict(count=len(values),total_s=round(sum(values),6),
                mean_s=round(mean(values),6) if values else 0,
                median_s=round(median(values),6) if values else 0,
                max_s=round(max(values),6) if values else 0,
                errors=sum(e['status']=='error' for e in events))


def summarize(python,java,page,harness):
    by_id={(e['process_id'],e['span_id']):e for e in python}
    def ancestry(event):
        names=[];seen=set();parent=event.get('parent_id')
        while parent is not None:
            key=(event['process_id'],parent)
            if key in seen:raise ValueError('Cyclic timing parent')
            seen.add(key);node=by_id.get(key)
            if node is None:break
            names.append(node['name']);parent=node.get('parent_id')
        return names
    loops=[e for e in java if e['name']=='java.planning_closed_loop' and e['status']=='ok']
    loop=loops[-1] if loops else None
    bounds=(epoch(loop),epoch(loop)+loop['duration_s']) if loop else None
    def overlap(event):
        start,end=epoch(event),epoch(event)+event['duration_s']
        if bounds:start,end=max(start,bounds[0]),min(end,bounds[1])
        return (start,end) if end>=start else None
    steps=[]
    for name,title in STEPS:
        source=java if name.startswith('java.') else page if name.startswith('page.') else python
        items=[e for e in source if e['name']==name]
        if name=='java.business_transaction' and bounds:
            items=[e for e in items if overlap(e)]
        steps.append(dict(name=name,title=title,**stats(items)))
    models=[e for e in python if e['name'].startswith('model.')]
    model_groups=defaultdict(list)
    purposes=('input.labels','input.topic_vectors','input.account_vectors','matching.annotations',
              'matching.mapping','matching.precision','matching.need_vector')
    for event in models:
        chain=ancestry(event)
        purpose=next((p for p in purposes if p in chain),'diagnostic_or_unparented')
        model_groups[purpose+'.'+event['name']].append(event)
    cache=defaultdict(lambda:dict(lookups=0,hits=0,unique_keys=0,preexisting_keys=0,cold_keys=0))
    seen=set()
    for event in sorted((e for e in python if e['name']=='cache.lookup'),key=epoch):
        group=cache[event['kind']];group['lookups']+=1;group['hits']+=int(event['hit'])
        key=event.get('cache_key')
        if key and key not in seen:
            seen.add(key);group['unique_keys']+=1
            group['preexisting_keys' if event['hit'] else 'cold_keys']+=1
    workers=[e for e in python if e['name']=='pipeline.worker']
    worker_union=intervals_union([i for e in workers if (i:=overlap(e))])
    model_union=intervals_union([i for e in models if (i:=overlap(e))])
    source_counts=Counter(e.get('capability') for e in python if e['name']=='source.java_http')
    transport_contexts={scope:{n:stats([e for e in python if e['name']==n
        and ('pipeline.worker' in ancestry(e))==in_worker]) for n in ('db.connect','db.execute','db.commit','source.java_http')}
        for scope,in_worker in (('worker',True),('api_or_other',False))}
    return dict(complete_planning_timing=bool(loop),planning_wall_s=loop['duration_s'] if loop else None,
                harness=harness,steps=steps,models={k:stats(v) for k,v in model_groups.items()},
                model_active_union_s=round(model_union,6),worker_active_union_s=round(worker_union,6),
                worker_gap_s=round(max(0,loop['duration_s']-worker_union),6) if loop else None,
                model_tokens={k:sum(e.get(k,0) for e in models) for k in ('prompt_tokens','completion_tokens','total_tokens')},
                cache=dict(cache),source_calls=dict(source_counts),
                transport_contexts=transport_contexts,
                transport={n:stats([e for e in python if e['name']==n]) for n in ('db.connect','db.execute','db.commit','source.java_http')})


def analyze(directory):
    directory=Path(directory)
    python=read_jsonl(directory/'python-timings.jsonl')
    java=read_jsonl(directory/'java-timings.jsonl')
    page=read_jsonl(directory/'page-timings.jsonl')
    if not python:raise ValueError('No measured Python events')
    harness=json.loads((directory/'harness-timings.json').read_text())
    report=summarize(python,java,page,harness)
    audit_file=directory/'execution-audit.json'
    audit=json.loads(audit_file.read_text(encoding='utf-8')) if audit_file.exists() else {}
    report['execution']=audit
    report['status']='measured' if report['complete_planning_timing'] else 'partial'
    (directory/'performance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (directory/'performance-steps.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['name','title','count','total_s','mean_s','median_s','max_s','errors'])
        writer.writeheader();writer.writerows(report['steps'])
    lines=['# 真实模型主链耗时记录','',
           '计时采用真实单调时钟；资料、宿主日期和内容生产方为模拟，模型、两个数据库及业务提交使用真实服务。',
           '阶段调用时间为累计调用耗时，可能嵌套；不能直接相加当作总耗时。模型请求耗时包含网络与服务端处理，不是纯推理时间。','',
           f"Java发起至完成落库确认：{report['planning_wall_s'] or '未完成'} 秒。",
           f"完整验收驱动：{harness.get('harness_total_s')} 秒；其中Maven至测试就绪 {harness.get('maven_until_test_ready_s')} 秒。",'',
           '| 步骤 | 次数 | 累计秒 | 平均秒 | 最大秒 | 异常调用 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for item in report['steps']:
        lines.append(f"| {item['title']} | {item['count']} | {item['total_s']:.3f} | {item['mean_s']:.3f} | {item['max_s']:.3f} | {item['errors']} |")
    lines+=['','## 模型请求分布','','| 用途 | 调用数 | 累计秒 | 最大秒 | 异常 |','| --- | ---: | ---: | ---: | ---: |']
    for kind,item in report['models'].items():
        lines.append(f"| {kind} | {item['count']} | {item['total_s']:.3f} | {item['max_s']:.3f} | {item['errors']} |")
    lines+=['','## 数据库与Java资料往返','','| 项目 | 次数 | 累计秒 | 平均秒 |','| --- | ---: | ---: | ---: |']
    for kind,item in report['transport'].items():
        lines.append(f"| {kind} | {item['count']} | {item['total_s']:.3f} | {item['mean_s']:.3f} |")
    lines+=['','Java资料能力调用次数：`'+json.dumps(report['source_calls'],ensure_ascii=False)+'`。',
            '',f"规划窗口内模型请求时间并集：{report['model_active_union_s']:.3f}秒；Python Worker活动并集：{report['worker_active_union_s']:.3f}秒；Worker未运行间隔：{report['worker_gap_s']}秒（含Java轮询、提交和确认，不能全部当作排队）。",'',
            '## 缓存','','| 类型 | 查询 | 命中 | 独立键 | 首次已存在 | 首次未命中 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for kind,item in report['cache'].items():
        lines.append(f"| {kind} | {item['lookups']} | {item['hits']} | {item['unique_keys']} | {item['preexisting_keys']} | {item['cold_keys']} |")
    lines+=['','首次未命中的键后续命中通常是同任务断点复用，不代表首次计算被历史缓存省掉。T6词典已有向量直接复用不经过上述缓存表。',
            '',f"模型返回的token累计：`{json.dumps(report['model_tokens'])}`。未返回的计数按0处理，不据此估算费用。",'',
            '本样本为单账号12选题、3条计划，不代表大规模吞吐或P95。原始计时不包含Prompt、SQL、接口令牌或连接信息。']
    (directory/'performance.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description='离线汇总真实验收计时，不调用模型、不读写数据库')
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    result=analyze(args.directory)
    print(json.dumps(dict(status=result['status'],planning_wall_s=result['planning_wall_s'],
                         model_active_union_s=result['model_active_union_s']),ensure_ascii=True))


if __name__=='__main__':main()
