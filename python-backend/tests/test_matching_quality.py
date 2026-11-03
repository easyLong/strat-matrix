"""V19 quality behavior with deterministic models; no network or live database."""
from copy import deepcopy
from unittest.mock import MagicMock,patch
import json
import unittest

from fastapi import HTTPException
from pydantic import ValidationError

from app.account_mapping import resolve_mapping
from app.matching_contracts import MatchingQualityOptions, MatchingPolicyDocument
from app.matching_quality import (t3_score,masked_score,recall,history_penalty,precision_score,
                                  valid_on,IMPLEMENTATION_KEY,QUALITY_PARAMETERS)
from app.matching_quality_model import checked_annotation,checked_account_mapping,PairJudgment,judge_batch
from app.matching_quality_store import QualityRuntime,QualityPending,save_quality_report
from app.matching_quality_executor import merged_mapping,allocate_quality
from app.matching_quality_executor import raw_account
from app.matching_quality_snapshot import content_hash
from app.matching_quality_validation import validate_quality_evaluation
from app.matching_policy import implementation_approval_errors
from app import matching_executor_worker as worker
from app.system_config import override_config
import test_account_mapping as mapping_fixture
import matching_fixtures as executor_fixture
import test_planning_result_commit as commit_fixture


def context():
    return {'taxonomy':mapping_fixture.taxonomy(),'taxonomy_version':3,'mapping_rules':[],
            'chat_model':'text-model','embedding_model':'vector-model',
            'options':MatchingQualityOptions().model_dump(mode='json')}


def mapping():
    return resolve_mapping({'persona':'福利专家'},context()['taxonomy'],[mapping_fixture.rule()],
                           mapping_version=1,taxonomy_version=3)


def annotation():
    return {'main_t3':'fund','related_t3':[],'t4':['family'],'t5':['scene']}


def judgment(**changes):
    value = {'decision':'ACCEPT','j_topic':.9,'j_need':.8,'j_aud':.5,'j_scene':.5,'j_style':.5,
             'condition_met':None,'reason':'具体内容适合该账号'}
    value.update(changes)
    return value


class QualityScoringTests(unittest.TestCase):
    def test_main_and_related_labels_use_one_and_half_coefficients(self):
        value=mapping()
        for n in value['features']['T3']['leaves']:
            if n['tag_id']=='card':n.update(value=.45,relation='CONDITIONAL')
        score,cause=t3_score(value,{**annotation(),'related_t3':['card']})
        self.assertAlmostEqual(score,(1+.45*.5)/1.5)
        self.assertIsNone(cause)

    def test_off_on_associated_tag_is_a_hard_gate(self):
        value=mapping()
        next(n for n in value['features']['T3']['leaves'] if n['tag_id']=='card')['relation']='OFF'
        self.assertEqual(t3_score(value,{**annotation(),'related_t3':['card']}),(None,'persona_off'))

    def test_unknown_primary_is_held_not_assigned_zero(self):
        self.assertEqual(t3_score(mapping(),{**annotation(),'main_t3':'other'}),(None,'unmapped_primary_topic'))

    def test_unknown_audience_and_scene_are_neutral(self):
        self.assertEqual(masked_score(mapping(),annotation(),'T4'),.5)
        self.assertEqual(masked_score(mapping(),annotation(),'T5'),.5)

    def test_five_routes_deduplicate_and_do_not_filter_by_t2(self):
        topics=[{'topic_id':str(i),'source_payload':{},'profile':{'applicable_cities':[]}} for i in range(120)]
        annotations={t['topic_id']:annotation() for t in topics}
        vectors={t['topic_id']:[1.,0.] for t in topics}
        account={'account_id':'A','profile':{'account':{'city':''}}}
        inputs={'positions':[{'account_id':'A','publish_date':'2027-01-18'}],
                'supplemental':{'history':{'observed_records':[]}}}
        result=recall(account,topics,annotations,mapping(),[1.,0.],vectors,inputs,MatchingQualityOptions())
        self.assertEqual({k:len(v) for k,v in result['channels'].items()},{'t3':60,'t6':60,'t4':30,'t5':30,'explore':20})
        self.assertEqual(result['retrieved_before_dedup'],200)
        self.assertEqual(len(result['ranked']),60)
        self.assertEqual(len({r['topic_id'] for r in result['ranked']}),60)
        self.assertAlmostEqual(result['ranked'][0]['signals']['t6'],1)

    def test_need_cosine_is_shifted_not_clipped_like_old_fit(self):
        topic={'topic_id':'T','source_payload':{},'profile':{'applicable_cities':[]}}
        result=recall({'account_id':'A','profile':{'account':{}}},[topic],{'T':annotation()},mapping(),
            [1.,0.],{'T':[-1.,0.]},{'positions':[{'account_id':'A','publish_date':'2027-01-18'}],
            'supplemental':{'history':{'observed_records':[]}}},MatchingQualityOptions())
        self.assertEqual(result['ranked'][0]['signals']['t6'],0)

    def test_model_drop_cannot_be_rescued_by_high_scores(self):
        result=precision_score(judgment(decision='DROP',j_topic=1.,j_need=1.),MatchingQualityOptions())
        self.assertFalse(result['accepted'])
        self.assertEqual(result['rejection_reason'],'model_drop')

    def test_conditional_needs_explicit_true(self):
        for value in (None,False):
            self.assertFalse(precision_score(judgment(condition_met=value),MatchingQualityOptions(),conditional=True)['accepted'])
        self.assertTrue(precision_score(judgment(condition_met=True),MatchingQualityOptions(),conditional=True)['accepted'])

    def test_repeat_adjustment_is_outside_static_model_score(self):
        result=precision_score(judgment(),MatchingQualityOptions(),repeat_penalty=.5)
        expected=.4*.9+.25*.8+.15*.5+.1*.5+.1*.5
        self.assertAlmostEqual(result['base_precision'],expected)
        self.assertAlmostEqual(result['final_precision'],expected-.05)

    def test_exact_title_duplicate_is_rejected(self):
        penalty,exact=history_penalty('家庭账单，怎么整理？',['家庭账单怎么整理'])
        self.assertEqual((penalty,exact),(1,True))
        self.assertEqual(precision_score(judgment(),MatchingQualityOptions(),exact_duplicate=exact)['rejection_reason'],'exact_duplicate')

    def test_low_topic_fit_cannot_be_rescued_by_other_components(self):
        result=precision_score(judgment(j_topic=.2,j_need=1.,j_aud=1.,j_scene=1.,j_style=1.),MatchingQualityOptions())
        self.assertEqual(result['rejection_reason'],'topic_fit_below_threshold')

    def test_adjacent_profession_requires_its_own_stronger_topic_gate(self):
        options=MatchingQualityOptions(minimum_adjacent_topic_fit=.8)
        value=judgment(j_topic=.7,j_need=.9,j_aud=.9,j_scene=.9,j_style=.9)
        self.assertTrue(precision_score(value,options)['accepted'])
        self.assertEqual(precision_score(value,options,adjacent=True)['rejection_reason'],
                         'adjacent_topic_fit_below_threshold')

    def test_validity_uses_beijing_calendar_days(self):
        topic={'valid_from':'2027-01-18T18:00:00+00:00','valid_to':'2027-01-19T18:00:00+00:00'}
        self.assertFalse(valid_on(topic,'2027-01-18'))
        self.assertTrue(valid_on(topic,'2027-01-19'))


class QualityModelContractTests(unittest.TestCase):
    def test_account_full_profile_takes_priority_over_old_source_alias(self):
        account={'profile':{'account':{'persona':'完整专业描述'}},'snapshot':{'source_payload':{'persona':'旧简称','gender':'女性'}}}
        self.assertEqual(raw_account(account)['persona'],'完整专业描述')
        self.assertEqual(raw_account(account)['gender'],'女性')

    def test_annotations_reject_parent_unknown_cross_dimension_and_duplicates(self):
        self.assertEqual(checked_annotation(annotation(),context()),annotation())
        for changes in ({'main_t3':'g3'},{'main_t3':'invented'},{'t4':['fund']},
                        {'related_t3':['fund']},{'t4':['family','family']}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                checked_annotation({**annotation(),**changes},context())

    def test_model_mapping_requires_verbatim_evidence_and_no_inferred_identity(self):
        raw={'persona':'家庭财务顾问','interests':['基金']}
        value={'mappings':[{'dimension':'T3','tag_id':'fund','relation':'CORE','condition':'',
                           'evidence_field':'interests','evidence':'基金'}],'need_capability':'理解家庭投资'}
        checked_account_mapping(value,context(),raw)
        bad=deepcopy(value);bad['mappings'][0]['evidence']='凭空证据'
        with self.assertRaises(ValueError):checked_account_mapping(bad,context(),raw)
        bad=deepcopy(value);bad['mappings'][0].update(dimension='T4',tag_id='family',evidence_field='persona',evidence='家庭')
        with self.assertRaises(ValueError):checked_account_mapping(bad,context(),raw)

    def test_model_cannot_invent_off_or_override_human_off(self):
        raw={'persona':'福利专家'}
        value={'mappings':[{'dimension':'T3','tag_id':'fund','relation':'OFF','condition':'',
                           'evidence_field':'persona','evidence':'福利专家'}],'need_capability':'发现权益'}
        with self.assertRaises(ValueError):checked_account_mapping(value,context(),raw)
        ctx=context();ctx['mapping_rules']=[mapping_fixture.rule(target_level='L3',target_node_id='fund',relation_type='OFF').model_dump()]
        account={'profile':{'account':{'persona':'福利专家'}}}
        value['mappings'][0]['relation']='CORE'
        result=merged_mapping(account,ctx,value)
        leaf=next(n for n in result['features']['T3']['leaves'] if n['tag_id']=='fund')
        self.assertEqual(leaf['relation'],'OFF')

    def test_young_family_does_not_infer_age_or_children(self):
        ctx=context()
        ctx['taxonomy']['T4'] += [
            {'id':'age_group','name':'年龄阶段','node_type':'group','enabled':True},
            {'id':'young','name':'青年人群','parent_id':'age_group','enabled':True}]
        raw={'persona':'家庭顾问','family_identity':'年轻家庭'}
        value={'mappings':[{'dimension':'T4','tag_id':'young','relation':'CORE','condition':'',
                            'evidence_field':'family_identity','evidence':'年轻家庭'}],'need_capability':'家庭预算'}
        with self.assertRaisesRegex(ValueError,'年龄'):checked_account_mapping(value,ctx,raw)
        value['mappings'][0]['tag_id']='family'
        with self.assertRaisesRegex(ValueError,'有娃'):checked_account_mapping(value,ctx,raw)

    def test_pair_output_rejects_extra_fields_nonfinite_and_string_boolean(self):
        PairJudgment.model_validate(judgment())
        for changes in ({'secret':'extra'},{'j_topic':float('nan')},{'condition_met':'true'}):
            with self.assertRaises(ValidationError):PairJudgment.model_validate(judgment(**changes))

    def test_incomplete_pair_batch_fails_instead_of_assuming_missing_is_accepted(self):
        with patch('app.matching_quality_model.chat',return_value={'results':{}}):
            with self.assertRaises(ValueError):judge_batch(context(),{}, {'0':{}})


class QualityPersistenceTests(unittest.TestCase):
    def test_budget_yields_without_another_model_call_and_renews_around_calls(self):
        renew=MagicMock();model=MagicMock(return_value={})
        runtime=QualityRuntime(context(),renew,max_calls=1)
        runtime.call(model)
        with self.assertRaises(QualityPending):runtime.call(model)
        model.assert_called_once();self.assertEqual(renew.call_count,2)

    def test_cache_key_covers_model_prompt_mapping_and_actual_pair_content(self):
        runtime=QualityRuntime(context(),lambda:None)
        original=runtime.key('pair_precision',{'title':'A'})[0]
        self.assertNotEqual(original,runtime.key('pair_precision',{'title':'B'})[0])
        runtime.context['chat_model']='another'
        self.assertNotEqual(original,runtime.key('pair_precision',{'title':'A'})[0])

    def test_corrupt_cache_is_rejected_without_model_calls(self):
        db=MagicMock();db.__enter__.return_value=db
        db.cursor.return_value.__enter__.return_value.fetchone.return_value={'result_json':'{}','result_hash':'0'*64}
        runtime=QualityRuntime(context(),lambda:None)
        with patch('app.matching_quality_store.connection',return_value=db):
            with self.assertRaises(ValueError):runtime.find('pair_precision',{})
        self.assertEqual(runtime.stats['model_calls'],0)

    def test_stale_task_lease_cannot_overwrite_progress(self):
        db=MagicMock();db.__enter__.return_value=db
        cursor=db.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value={'status':'processing','lease_id':'new','live':1}
        with patch('app.matching_quality_store.connection',return_value=db):
            with self.assertRaises(HTTPException):save_quality_report({'task_id':1,'lease_id':'old'},{},'processing','recall')
        db.commit.assert_not_called()
        self.assertEqual(cursor.execute.call_count,1)

    def test_pending_task_is_requeued_not_failed_by_worker(self):
        job={'task_id':1,'lease_id':'a'*32,'input_hash':'b'*64,'policy_hash':'c'*64}
        with override_config({}),patch.object(worker,'EXECUTORS',{IMPLEMENTATION_KEY:MagicMock(side_effect=QualityPending())}), \
             patch.object(worker,'claim_task',return_value={'job':job,'next_after_id':1}), \
             patch.object(worker,'yield_task') as yield_task,patch.object(worker,'fail_task') as fail:
            self.assertEqual(worker.run_once(max_jobs=1),0)
        yield_task.assert_called_once();fail.assert_not_called()


class QualityPolicyAndAllocationTests(unittest.TestCase):
    def policy(self):
        value=executor_fixture.policy()
        value.update(implementation_key=IMPLEMENTATION_KEY,quality=MatchingQualityOptions().model_dump(),
                     portfolio={'relevance_weight':.55,'coverage_weight':.2,'balance_weight':.1,'redundancy_weight':.15,
                                'mmr_relevance_weight':.7,'shortlist_per_slot':20,'max_improvement_passes':20})
        for code,params in QUALITY_PARAMETERS.items():value['decisions'][code]['parameters']=params
        value['decisions']['ALG-05']['parameters'].update(global_reuse_penalty=0.,official_usage_penalty=0.)
        return MatchingPolicyDocument.model_validate(value)

    def test_policy_has_explicit_quality_contract_and_old_policy_cannot_silently_enable_it(self):
        document=self.policy()
        self.assertEqual(implementation_approval_errors(document),[])
        document.implementation_key='builtin-cosine-portfolio-v2'
        self.assertTrue(document.approval_errors())

    def test_bad_quotas_and_weights_or_precision_limit_are_rejected(self):
        for changes in ({'quotas':{'t3':60}}, {'recall_weights':{'t3':1.}}, {'precision_limit':100,'recall_limit':10}):
            with self.assertRaises(ValidationError):MatchingQualityOptions(**changes)

    def test_allocator_only_uses_accepted_precision_and_never_hotness_fallback(self):
        job={'lease_id':'a'*32,'input_hash':'b'*64,'policy_hash':'c'*64,'inputs':{
            'accounts':[{'account_id':'A','profile':{'lifecycle_stage':'阶段'}}],
            'positions':[{'account_id':'A','publish_date':'2027-01-18'}],
            'config':{'stage_targets':[{'name':'阶段','traffic':100,'conversion':0}]},
            'topics':[{'topic_id':'T','tags':{'T2':['流量']},'vector':[1.,0.]}]}}
        report={'accounts':{'A':{'top30':[],'recall':{'rejected':[],'ranked':[]}}},
                'topic_annotations':{'T':annotation()}}
        result=allocate_quality(job,self.policy(),report)
        self.assertEqual(result.positions[0].outcome,'failed')
        report['accounts']['A']['top30']=[{'topic_id':'T','final_precision':.9,'judgment':{'reason':'适配原因'}}]
        result=allocate_quality(job,self.policy(),report)
        self.assertEqual(result.positions[0].fit_score,90.)
        self.assertEqual(result.positions[0].reason,'适配原因')

    def test_evaluation_only_cannot_commit_a_formal_batch(self):
        helper=commit_fixture.PlanningResultTransactionTests();helper.setUp();self.addCleanup(helper.doCleanups)
        helper.stack.enter_context(patch.object(commit_fixture.service,'intact_document',return_value=self.policy()))
        with self.assertRaises(commit_fixture.service.ResultCommitError) as caught:
            commit_fixture.service.commit_pipeline_result(501,7)
        self.assertEqual(caught.exception.code,'quality_evaluation_only')
        helper.profiles.assert_not_called()


class QualityResultGuardTests(unittest.TestCase):
    def fixture(self):
        document=QualityPolicyAndAllocationTests().policy()
        job={'task_id':1,'lease_id':'a'*32,'input_hash':'b'*64,'policy_hash':'c'*64,'inputs':{
            'accounts':[{'account_id':'A','profile':{'account':{'city':''},'lifecycle_stage':'阶段'}}],
            'positions':[{'account_id':'A','publish_date':'2027-02-01'}],
            'config':{'stage_targets':[{'name':'阶段','traffic':100,'conversion':0}]},
            'supplemental':{'history':{'observed_records':[]}},
            'topics':[{'topic_id':'T','source_payload':{'title':'家庭预算整理'},'profile':{'applicable_cities':[]},
                       'tags':{'T2':['流量']},'vector':[1.,0.]}]}}
        scored=precision_score(judgment(),document.quality)
        report={'policy_hash':job['policy_hash'],'input_hash':job['input_hash'],
                'accounts':{'A':{'mapping':mapping(),'top30':[{'topic_id':'T','judgment':judgment(),**scored}],
                                  'recall':{'rejected':[],'ranked':[]}}},'topic_annotations':{'T':annotation()}}
        result=allocate_quality(job,document,report)
        cursor=MagicMock()
        self.bind(cursor,report,result,job)
        task={'id':1,**{k:job[k] for k in ('lease_id','input_hash','policy_hash')}}
        return cursor,task,result,job['inputs'],document,report

    def bind(self,cursor,report,result,job):
        fingerprint=content_hash(report)
        cursor.fetchone.return_value={'status':'ready','lease_id':job['lease_id'],
                                     'report_json':json.dumps(report),'report_hash':fingerprint}
        result.stages[2].summary['quality_report_hash']=fingerprint

    def test_valid_quality_result_is_accepted_from_persisted_evidence(self):
        cursor,task,result,inputs,document,_=self.fixture()
        validate_quality_evaluation(cursor,task,result,inputs,document)

    def test_direct_submission_cannot_bypass_model_drop(self):
        cursor,task,result,inputs,document,report=self.fixture()
        report['accounts']['A']['top30'][0]['judgment']['decision']='DROP'
        self.bind(cursor,report,result,task)
        with self.assertRaises(HTTPException) as caught:validate_quality_evaluation(cursor,task,result,inputs,document)
        self.assertIn('精判未通过',caught.exception.detail)

    def test_fake_score_or_unbound_report_is_rejected(self):
        cursor,task,result,inputs,document,_=self.fixture()
        result.positions[0].fit_score=99
        with self.assertRaises(HTTPException):validate_quality_evaluation(cursor,task,result,inputs,document)
        result.stages[2].summary['quality_report_hash']='0'*64
        with self.assertRaises(HTTPException) as caught:validate_quality_evaluation(cursor,task,result,inputs,document)
        self.assertEqual(caught.exception.status_code,409)

    def test_hotness_fallback_cannot_bypass_precision(self):
        cursor,task,result,inputs,document,_=self.fixture()
        result.positions[0]=result.positions[0].model_copy(update={'outcome':'fallback','fit_score':None})
        with self.assertRaises(HTTPException) as caught:validate_quality_evaluation(cursor,task,result,inputs,document)
        self.assertIn('不允许',caught.exception.detail)


if __name__=='__main__':unittest.main()
