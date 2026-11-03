"""Account mapping boundaries, inheritance, unknown values and replay-safe seed data."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.account_mapping import MappingRule, resolve_mapping, validate_target
from app.account_mapping_seed import build_seed_rules
from app import init_account_mapping as initializer
from app.init_db import column_definitions, table_descriptions
from app.taxonomy import normalize_taxonomy


def taxonomy():
    return normalize_taxonomy({
        'T3': [{'id': 'g3', 'name': '金融与财富', 'node_type': 'group', 'enabled': True},
               {'id': 'fund', 'name': '基金', 'parent_id': 'g3', 'enabled': True},
               {'id': 'card', 'name': '信用卡', 'parent_id': 'g3', 'enabled': True},
               {'id': 'other', 'name': '未知方向', 'enabled': True}],
        'T4': [{'id': 'g4', 'name': '家庭阶段', 'node_type': 'group', 'enabled': True},
               {'id': 'family', 'name': '有娃家庭', 'parent_id': 'g4', 'enabled': True}],
        'T5': [{'id': 'g5', 'name': '家庭场景', 'node_type': 'group', 'enabled': True},
               {'id': 'scene', 'name': '亲子出行', 'parent_id': 'g5', 'enabled': True}],
    })


def rule(identity=1, **changes):
    values = dict(id=identity, mapping_version=1, taxonomy_version=3, source_field='persona',
                  source_value='福利专家', target_dimension='T3', target_level='L2',
                  target_node_id='g3', relation_type='CORE', status='active')
    values.update(changes)
    return MappingRule(**values)


class AccountMappingTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = taxonomy()
        self.account = {'account_id': 'A', 'persona': '福利专家'}

    def resolve(self, rules, **options):
        return resolve_mapping(self.account, self.taxonomy, rules, mapping_version=1,
                               taxonomy_version=3, **options)

    def leaf(self, result, identity='fund', dimension='T3'):
        return next(n for n in result['features'][dimension]['leaves'] if n['tag_id'] == identity)

    def test_leaf_off_overrides_category_without_double_counting(self):
        output = self.resolve([rule(), rule(2, target_level='L3', target_node_id='fund', relation_type='OFF')])
        self.assertEqual(self.leaf(output)['value'], 0)
        self.assertTrue(self.leaf(output)['known'])
        self.assertEqual(self.leaf(output)['evidence'][0]['target_level'], 'L3')
        self.assertEqual(self.leaf(output, 'card')['value'], 1)
        self.assertNotIn('g3', output['features']['T3']['tag_ids'])

    def test_persona_off_cannot_be_revived_by_interest(self):
        self.account['interests'] = ['理财']
        output = self.resolve([rule(target_level='L3', target_node_id='fund', relation_type='OFF'),
            rule(2, source_field='interests', source_value='理财', target_level='L3', target_node_id='fund')])
        self.assertEqual(self.leaf(output)['relation'], 'OFF')

    def test_unknown_stays_unknown_and_does_not_inherit_from_siblings(self):
        output = self.resolve([rule(target_level='L3', target_node_id='fund')])
        self.assertEqual(self.leaf(output, 'card')['relation'], 'UNKNOWN')
        self.assertIsNone(self.leaf(output, 'card')['value'])
        self.assertFalse(self.leaf(output, 'card')['known'])

    def test_condition_weight_retains_text_and_never_means_approved(self):
        output = self.resolve([rule(relation_type='CONDITIONAL', condition_text='仅限权益内容')])
        self.assertEqual(self.leaf(output)['value'], .45)
        self.assertEqual(self.leaf(output)['condition'], '仅限权益内容')
        self.assertTrue(self.leaf(output)['requires_precision'])

    def test_drafts_only_work_in_explicit_preview_and_disabled_never_work(self):
        draft = rule(status='draft')
        self.assertFalse(self.leaf(self.resolve([draft]))['known'])
        self.assertTrue(self.leaf(self.resolve([draft], preview=True))['known'])
        self.assertFalse(self.leaf(self.resolve([rule(status='disabled')], preview=True))['known'])

    def test_unchanged_persona_name_is_required(self):
        self.account['persona'] = '福利专家，兼顾其他方向'
        output = self.resolve([rule()])
        self.assertFalse(self.leaf(output)['known'])
        self.assertEqual(output['unmapped_values'][0]['source_value'], self.account['persona'])

    def test_conflicting_nonpersona_signals_remain_unknown(self):
        self.account['interests'] = ['A', 'B']
        output = self.resolve([rule(source_field='interests', source_value='A', target_level='L3', target_node_id='fund'),
            rule(2, source_field='interests', source_value='B', target_level='L3', target_node_id='fund', relation_type='ADJACENT')])
        self.assertEqual(self.leaf(output)['reason'], 'conflicting_rules')
        self.assertIsNone(self.leaf(output)['value'])

    def test_wrong_taxonomy_and_disabled_parent_do_not_apply(self):
        output = self.resolve([rule(taxonomy_version=2)])
        self.assertEqual(output['ignored_rules'][0]['reason'], 'taxonomy_version_mismatch')
        self.taxonomy['T3'][0]['enabled'] = False
        output = self.resolve([rule()])
        self.assertNotIn('fund', output['features']['T3']['tag_ids'])
        self.assertEqual(output['ignored_rules'][0]['reason'], 'target_unavailable')

    def test_need_and_style_are_text_not_structured_features(self):
        self.account['expression_style'] = '干货J人'
        output = self.resolve([
            rule(target_dimension='T6', target_level='TEXT', target_node_id='', relation_type='TEXT', target_text='发现实用权益'),
            rule(2, source_field='expression_style', source_value='干货J人', target_dimension='STYLE',
                 target_level='TEXT', target_node_id='', relation_type='TEXT', target_text='清单、步骤')])
        self.assertEqual(output['need_capability']['text'], '发现实用权益')
        self.assertEqual(output['style']['text'], '清单、步骤')
        self.assertTrue(all(n['relation'] == 'UNKNOWN' for n in output['features']['T3']['leaves']))

    def test_missing_gender_and_family_are_not_inferred_from_persona(self):
        output = self.resolve([rule(source_field='family_identity', source_value='有娃',
                                    target_dimension='T4', target_level='L3', target_node_id='family')])
        self.assertFalse(self.leaf(output, 'family', 'T4')['known'])

    def test_fingerprint_changes_with_rule_body_or_hierarchy_but_not_rule_order(self):
        a = rule()
        b = rule(2, target_level='L3', target_node_id='fund', relation_type='OFF')
        self.assertEqual(self.resolve([a, b])['mapping_hash'], self.resolve([b, a])['mapping_hash'])
        self.assertNotEqual(self.resolve([a])['mapping_hash'], self.resolve([a, b])['mapping_hash'])
        old = self.resolve([a])['mapping_hash']
        self.taxonomy['T3'][1]['name'] = '新名称'
        self.assertNotEqual(old, self.resolve([a])['mapping_hash'])

    def test_rule_validation_rejects_unsafe_shapes_and_weights(self):
        for changes in (
            {'relation_type': 'CONDITIONAL'}, {'relation_type': 'CORE', 'weight': .75},
            {'weight': True}, {'source_value': ' 福利专家'},
            {'relation_type': 'CORE', 'condition_text': '不应被忽略的条件'},
            {'target_dimension': 'T4', 'target_node_id': 'g4'},
            {'source_field': 'expression_style'},
            {'target_dimension': 'STYLE', 'target_level': 'TEXT', 'target_node_id': '',
             'relation_type': 'TEXT', 'target_text': '风格'},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                rule(**changes)

    def test_target_shape_is_checked_against_real_dictionary(self):
        with self.assertRaisesRegex(ValueError, '层级'):
            validate_target(rule(target_level='L3', target_node_id='g3'), self.taxonomy)
        with self.assertRaisesRegex(ValueError, '词表'):
            validate_target(rule(target_node_id='made-up'), self.taxonomy)


class MappingInitializationTests(unittest.TestCase):
    def test_seed_uses_actual_ids_and_reports_missing_targets_without_creating_tags(self):
        tax = taxonomy()
        original = deepcopy(tax)
        rules, missing = build_seed_rules(tax, 3)
        self.assertTrue(all(r.status == 'draft' for r in rules))
        self.assertTrue(any(r.target_node_id == 'fund' and r.relation_type == 'OFF' for r in rules))
        self.assertTrue(any(r['target_name'] == '用卡权益' for r in missing))
        self.assertEqual(tax, original)

    def test_seed_replay_preserves_manually_reviewed_rows(self):
        saved = {}
        cursor = MagicMock()
        def execute(sql, parameters):
            self.assertIn('ON DUPLICATE KEY UPDATE id=id', sql)
            columns = sql.split('(', 1)[1].split(')', 1)[0].split(',')
            row = dict(zip(columns, parameters))
            key = tuple(row[k] for k in ('mapping_version','taxonomy_version','source_field',
                                          'source_value','target_dimension','target_node_id'))
            cursor.rowcount = int(key not in saved)
            saved.setdefault(key, row)
        cursor.execute.side_effect = execute
        with patch.object(initializer, 'load_taxonomy', return_value=(3, taxonomy())):
            first = initializer.seed_rules(cursor)
            next(iter(saved.values()))['status'] = 'active'
            second = initializer.seed_rules(cursor)
        self.assertGreater(first['inserted'], 0)
        self.assertEqual(second['inserted'], 0)
        self.assertEqual(second['existing'], first['inserted'])
        self.assertEqual(next(iter(saved.values()))['status'], 'active')

    def test_all_table_fields_have_chinese_comments(self):
        sql = (Path(__file__).resolve().parents[1] / 'schema.sql').read_text(encoding='utf-8')
        columns = column_definitions(sql)['godp_account_mapping_rule']
        self.assertEqual(len(columns), 21)
        self.assertIn('策划侧', table_descriptions(sql)['godp_account_mapping_rule'])


if __name__ == '__main__':
    unittest.main()
