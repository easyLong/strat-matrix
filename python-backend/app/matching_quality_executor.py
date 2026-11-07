"""V19 quality front-end, followed by the existing capacity/portfolio allocator."""
from .account_mapping import resolve_mapping, WEIGHTS
from .core.matching_common import role_plan, stage_targets, ExecutorInputError
from .doubao_labeling import embed_text, read_embedding_config
from .matching_allocation import Candidate, Slot, allocate_matrix
from .matching_contracts import MatchingEvaluation, MatchingPolicyDocument, LeaseHeartbeat
from .matching_portfolio import PortfolioPolicy, optimize_portfolios
from .matching_quality import IMPLEMENTATION_KEY, recall, precision_score, history_penalty, topic_labels, valid_on
from .matching_quality_model import (dictionary, checked_annotation, checked_account_mapping,
                                     annotate_batch, map_account, judge_batch, PairJudgment)
from .matching_quality_snapshot import content_hash, topic_need_vectors
from .matching_quality_store import QualityRuntime, QualityPending, save_quality_report
from .taxonomy import selectable_tags
from .vector_utils import normalized_vector
from .matching_precheck import role_coverage,InsufficientRoleCoverage
from .model_capacity import CapacityExceeded


def raw_account(account):
    source = account.get('snapshot', {}).get('source_payload') or {}
    profile = account['profile']['account']
    # Exclude identifiers, UM, organization, follower counts and activity metadata from model input.
    return {field: profile.get(field) if profile.get(field) not in (None,'',[]) else source.get(field) for field in
            ('persona','family_identity','interests','gender','expression_style')}


def merged_mapping(account, context, model=None):
    raw = raw_account(account)
    options = context['options']
    result = resolve_mapping(raw, context['taxonomy'], context['mapping_rules'],
        mapping_version=options['mapping_version'],taxonomy_version=context['taxonomy_version'],
        preview=options['mapping_mode'] == 'draft_preview')
    if model:
        for item in model['mappings']:
            feature = result['features'][item['dimension']]
            for index, leaf in enumerate(feature['leaves']):
                if leaf['tag_id'] != item['tag_id'] or leaf['known']: continue
                leaf.update(known=True,value=WEIGHTS[item['relation']],relation=item['relation'],
                            condition=item['condition'],requires_precision=item['relation']=='CONDITIONAL',
                            reason='restricted_model_mapping',evidence=[{'source_field':item['evidence_field'],
                            'source_value':item['evidence'],'status':'model_derived'}])
                feature['values'][index], feature['known_mask'][index] = leaf['value'], 1
        if not result['need_capability']['known']:
            result['need_capability'].update(known=True,text=model['need_capability'],source='restricted_model')
        result['mapping_hash'] = content_hash({'fixed_mapping':result['mapping_hash'],'model_mapping':model})
    return result


def _topic_content(topic):
    source = topic['source_payload']
    return {k:source.get(k) or '' for k in ('title','outline','summary','content_type')}


def _label_value(topic, dimension):
    value = topic['tags'].get(dimension,topic['tags'].get(dimension.lower()))
    if isinstance(value,list) and len(value)==1: value=value[0]
    if not isinstance(value,str) or not value.strip():
        raise ValueError('冻结选题缺少单值经营作用或需求描述')
    return value


def _static_account(raw, mapping, context):
    nodes = {d:{n['id']:n['path'] for n in nodes} for d,nodes in dictionary(context['taxonomy']).items()}
    return {'raw':raw, 'need_capability':mapping['need_capability']['text'],
            'style':mapping['style']['text'] or raw.get('expression_style'),
            'capabilities':{d:[{'path':nodes[d][n['tag_id']],'relation':n['relation'],'condition':n['condition']}
                              for n in value['leaves'] if n['known']]
                            for d,value in mapping['features'].items()}}


def _pair_topic(topic, annotation, mapping, context):
    nodes = {d:{n['id']:n['path'] for n in ns} for d,ns in dictionary(context['taxonomy']).items()}
    capability = {n['tag_id']:n for n in mapping['features']['T3']['leaves']}
    conditions = [capability[t]['condition'] for t,_ in topic_labels(annotation)
                  if t in capability and capability[t]['relation']=='CONDITIONAL']
    return {'content':_topic_content(topic), 'need':topic['tags']['T6'],
            'main_t3':nodes['T3'][annotation['main_t3']],
            'related_t3':[nodes['T3'][t] for t in annotation['related_t3']],
            't4':[nodes['T4'][t] for t in annotation['t4']],
            't5':[nodes['T5'][t] for t in annotation['t5']], 'conditions':conditions}


def _need_vector(runtime, text, dimension):
    def compute():
        config = read_embedding_config()
        if config.embedding_model != runtime.context['embedding_model']:
            raise ValueError('需求向量模型已变化')
        return embed_text(text, config)
    def validate(value):
        vector = normalized_vector(value['vector'], value['vector_model'], '需求向量')
        if value['vector_model'] != runtime.context['embedding_model'] or len(vector) != dimension:
            raise ValueError('需求向量模型或维度不一致')
        return {**value,'vector':vector}
    return runtime.cached('need_vector',{'text':text},compute,validate)['vector']


def execute_quality_job(job):
    document = MatchingPolicyDocument.model_validate(job['policy'])
    if document.implementation_key != IMPLEMENTATION_KEY or document.quality is None:
        raise ExecutorInputError('V19执行策略不完整')
    context = job['inputs']['supplemental']['quality_context']
    if context['options'] != document.quality.model_dump(mode='json',exclude_none=True):
        raise ExecutorInputError('V19冻结参数与策略不一致')
    from .matching_tasks import heartbeat_task
    identity = {k:job[k] for k in ('lease_id','input_hash','policy_hash')}
    renew = lambda: heartbeat_task(job['task_id'], LeaseHeartbeat(**identity,lease_seconds=1800))
    runtime = QualityRuntime(context, renew)
    report = {'schema_version':1,'evaluation_only':document.quality.evaluation_only,'input_hash':job['input_hash'],'accounts':{},'topic_annotations':{},
              'models':{k:context[k] for k in ('chat_model','embedding_model')}, 'policy_hash':job['policy_hash']}
    phase = 'topic_annotations'
    def checkpoint(state='processing'):
        report['worker_turn'] = dict(runtime.stats)
        save_quality_report(job,report,state,phase)
    try:
        phase='role_coverage'
        report['precheck']=role_coverage(job['inputs'])
        if report['precheck']['status']=='blocked':
            raise InsufficientRoleCoverage('冻结候选中缺少指定日期所需经营作用的选题')
        phase='topic_annotations'
        topics = job['inputs']['topics']
        topic_by_id = {t['topic_id']:t for t in topics}
        missing = []
        topic_dictionary=dictionary(context['taxonomy'])
        topic_payloads=[(topic,{'topic':_topic_content(topic),'dictionary':topic_dictionary}) for topic in topics]
        runtime.prefetch('topic_annotation',[payload for _,payload in topic_payloads])
        for topic,payload in topic_payloads:
            cached = runtime.find('topic_annotation',payload)
            if cached is None: missing.append((topic['topic_id'],payload))
            else: report['topic_annotations'][topic['topic_id']] = checked_annotation(cached,context)
        for offset in range(0,len(missing),8):
            batch = missing[offset:offset+8]
            data = {str(i):payload['topic'] for i,(_,payload) in enumerate(batch)}
            results = runtime.call(lambda:annotate_batch(context,data))
            for i,(topic_id,payload) in enumerate(batch):
                value = runtime.save('topic_annotation',payload,results[str(i)])
                report['topic_annotations'][topic_id] = checked_annotation(value,context)
            checkpoint()
        vectors = topic_need_vectors(context)
        need_vectors = {}
        for topic in topics:
            vector = vectors.get(str(topic['t6_tag_id']))
            need_vectors[topic['topic_id']] = (vector if vector and len(vector)==document.vector_space.dimension
                else _need_vector(runtime,_label_value(topic,'T6'),document.vector_space.dimension))
        for account in job['inputs']['accounts']:
            account_id = account['account_id']
            phase = 'account_mapping'
            raw = raw_account(account)
            mapping = merged_mapping(account,context)
            if (not mapping['need_capability']['known'] or not any(mapping['features']['T3']['known_mask'])) \
                    and document.quality.unknown_persona == 'restricted_model':
                payload = {'account':raw,'dictionary':dictionary(context['taxonomy']),
                           'fixed_mapping_hash':mapping['mapping_hash']}
                model = runtime.cached('account_mapping',payload,lambda:map_account(context,raw),
                                       lambda v:checked_account_mapping(v,context,raw))
                mapping = merged_mapping(account,context,model)
            entry = {'mapping':mapping,'recall':None,'precision':[],'top30':[]}
            report['accounts'][account_id] = entry
            checkpoint()
            if not mapping['need_capability']['known']:
                entry['waiting_reason'] = 'account_need_unknown'
                continue
            account_need = _need_vector(runtime,mapping['need_capability']['text'],document.vector_space.dimension)
            phase = 'recall'
            entry['recall'] = recall(account,topics,report['topic_annotations'],mapping,account_need,
                                     need_vectors,job['inputs'],document.quality)
            checkpoint()
            phase = 'precision'
            static = _static_account(raw,mapping,context)
            pending = []
            judgments = {}
            pair_payloads={candidate['topic_id']:{'account':static,
                'topic':_pair_topic(topic_by_id[candidate['topic_id']],report['topic_annotations'][candidate['topic_id']],mapping,context),
                'mapping_hash':mapping['mapping_hash']} for candidate in entry['recall']['ranked']}
            runtime.prefetch('pair_precision',list(pair_payloads.values()))
            for candidate in entry['recall']['ranked']:
                topic_id = candidate['topic_id']
                payload = pair_payloads[topic_id]
                cached = runtime.find('pair_precision',payload)
                if cached is None: pending.append((topic_id,payload))
                else: judgments[topic_id] = PairJudgment.model_validate(cached).model_dump()
            for offset in range(0,len(pending),30):
                batch = pending[offset:offset+30]
                data = {str(i):payload['topic'] for i,(_,payload) in enumerate(batch)}
                values = runtime.call(lambda:judge_batch(context,static,data))
                for i,(topic_id,payload) in enumerate(batch):
                    cached = runtime.save('pair_precision',payload,values[str(i)])
                    judgments[topic_id] = PairJudgment.model_validate(cached).model_dump()
                checkpoint()
            history = [h['source_payload'].get('title') or '' for h in
                       job['inputs']['supplemental']['history']['observed_records'] if h['account_id']==account_id]
            for candidate in entry['recall']['ranked']:
                topic_id = candidate['topic_id']
                item = _pair_topic(topic_by_id[topic_id],report['topic_annotations'][topic_id],mapping,context)
                penalty, exact = history_penalty(item['content']['title'],history)
                value = judgments[topic_id]
                primary = next(n for n in mapping['features']['T3']['leaves']
                               if n['tag_id']==report['topic_annotations'][topic_id]['main_t3'])
                scored = precision_score(value,document.quality,conditional=bool(item['conditions']),
                                         adjacent=primary['relation']=='ADJACENT',repeat_penalty=penalty,exact_duplicate=exact)
                entry['precision'].append({'topic_id':topic_id,'judgment':value,**scored})
            accepted = [p for p in entry['precision'] if p['accepted']]
            entry['top30'] = sorted(accepted,key=lambda r:(-r['final_precision'],r['topic_id']))[:document.quality.precision_limit]
            checkpoint()
        phase = 'allocation'
        result = allocate_quality(job, document, report)
        report['summary'] = {'matched':sum(p.outcome=='matched' for p in result.positions),
                             'failed':sum(p.outcome=='failed' for p in result.positions),
                             'model_pair_decisions':sum(len(a['precision']) for a in report['accounts'].values())}
        checkpoint('ready')
        result.stages[2].summary['quality_report_hash'] = content_hash(report)
        return result
    except (QualityPending,CapacityExceeded):
        checkpoint('waiting')
        raise
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        if isinstance(exc,ValueError): report['error_message'] = str(exc).splitlines()[0][:200]
        try: checkpoint('failed')
        except Exception: pass
        raise


def allocate_quality(job, document, report):
    """V19 allocator; no independent 7-8 pool, history T2 or two-stage solver."""
    inputs = job['inputs']
    targets = stage_targets(inputs)
    roles = {}
    slots = []
    for account in inputs['accounts']:
        positions = [p for p in inputs['positions'] if p['account_id']==account['account_id']]
        roles.update(role_plan(account,positions,targets[account['profile']['lifecycle_stage']]))
        slots += [Slot(slot_id=f"{p['account_id']}:{p['publish_date']}",account_id=p['account_id'],
                       publish_date=p['publish_date']) for p in positions]
    topics = {t['topic_id']:t for t in inputs['topics']}
    candidates, evidence = [], {}
    for slot in slots:
        for item in report['accounts'][slot.account_id]['top30']:
            topic = topics[item['topic_id']]
            if _label_value(topic,'T2') != roles[(slot.account_id,slot.publish_date)] or not valid_on(topic,slot.publish_date): continue
            candidate = Candidate(slot_id=slot.slot_id,account_id=slot.account_id,topic_id=item['topic_id'],
                                  signals={'precision':item['final_precision']},fit_score=item['final_precision'])
            candidates.append(candidate)
            evidence[(slot.slot_id,item['topic_id'])] = item
    parameters = document.decisions['ALG-05'].parameters
    capacities = {t:parameters['global_topic_max'] if parameters['global_topic_max'] is not None else len(slots) for t in topics}
    initial = allocate_matrix(slots,candidates,capacities,account_topic_capacity=parameters['same_account_topic_max'],reserved_account_topics={})
    annotations = report['topic_annotations']
    labels = {t:{'T3':[a['main_t3'],*a['related_t3']],'T4':a['t4'],'T5':a['t5']} for t,a in annotations.items()}
    def similarity(left,right):
        return max(0.0,min(1.0,sum(a*b for a,b in zip(topics[left]['vector'],topics[right]['vector']))))
    optimized = optimize_portfolios(slots,candidates,initial,labels,similarity,capacities,
        account_topic_capacity=parameters['same_account_topic_max'],reserved_account_topics={},
        policy=PortfolioPolicy.from_mapping(document.portfolio.model_dump()),allow_unassignment=False)
    assigned = {a.slot_id:a for a in optimized.assignments}
    positions = []
    for slot in slots:
        item = assigned.get(slot.slot_id)
        if item:
            row = evidence[(slot.slot_id,item.topic_id)]
            positions.append({'account_id':slot.account_id,'publish_date':slot.publish_date,'outcome':'matched',
                              'topic_id':item.topic_id,'content_role':roles[(slot.account_id,slot.publish_date)],
                              'fit_score':round(row['final_precision']*100,6),'reason':row['judgment']['reason'][:500]})
        else:
            positions.append({'account_id':slot.account_id,'publish_date':slot.publish_date,'outcome':'failed',
                              'reason':'没有满足精判底线、当前经营作用或容量约束的选题；未使用低适配兜底'})
    matched = sum(p['outcome']=='matched' for p in positions)
    counts = {identity:len(a['top30']) for identity,a in report['accounts'].items()}
    stages = [
        {'stage':'hard_gate','summary':{'held_or_excluded_pairs':sum(len(a['recall']['rejected']) for a in report['accounts'].values() if a['recall'])}},
        {'stage':'recall','summary':{'method':'five_routes_200_to_100','accounts':{k:len(a['recall']['ranked']) if a['recall'] else 0 for k,a in report['accounts'].items()}}},
        {'stage':'fit','summary':{'score_scale':'model_precision_0_100','qualified_by_account':counts,'evaluation_only':document.quality.evaluation_only}},
        {'stage':'global_allocation','summary':{'matched_positions':matched,'fallback_positions':0,'failed_positions':len(positions)-matched}},
        {'stage':'composition','summary':{'allocator':'v19_portfolio','history_t2_enabled':False,'two_stage_schedule_enabled':False,
            'actual_traffic_positions':sum(p.get('content_role')=='流量' for p in positions),
            'actual_conversion_positions':sum(p.get('content_role')=='转化' for p in positions)}},
    ]
    return MatchingEvaluation.model_validate({**{k:job[k] for k in ('lease_id','input_hash','policy_hash')},
        'implementation_key':IMPLEMENTATION_KEY,'positions':positions,'stages':stages})
