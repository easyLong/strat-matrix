"""Task scope stability and readiness must not depend on a live model or database."""
from copy import deepcopy
import json
import unittest
from unittest.mock import MagicMock, patch

from app import preparation_scope as scope
from app.account_profile import canonical_json
from app.ai_preparation import advance_preparation
import test_ai_preparation as prep_fixtures
from test_matching_readiness import fixture, CHECKED_AT


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.topics = fixture()[2]
        for topic in self.topics:
            topic.update(tag_ids_json=canonical_json({f'T{i}': f'T{i}-ID' for i in range(1, 6)}),
                         taxonomy_version=2, t6_tag_id=1)
        self.binding = {'taxonomy_version': 2, 'chat_model': 'chat', 'embedding_model': 'shared-v1'}
        self.value = {'schema_version': 1, 'account_ids': ['A'],
                      'topic_sources': {t['topic_id']: scope.source_signature(t['payload_json']) for t in self.topics},
                      **self.binding}

    def test_new_candidates_never_expand_saved_scope(self):
        cursor = MagicMock()
        with patch.object(scope, 'ensure_scope', return_value=(self.value, {})), \
                patch.object(scope, 'versions', return_value=self.binding):
            extra = {**self.topics[0], 'topic_id': 'ADDED-LATER'}
            topics, saved, reasons = scope.scoped_topics(cursor, {'id': 7}, self.topics + [extra])
        self.assertEqual([t['topic_id'] for t in topics], list(self.value['topic_sources']))
        self.assertEqual(reasons, [])

    def test_source_changes_missing_candidates_and_version_changes_are_explicit(self):
        changed = deepcopy(self.topics)
        payload = json.loads(changed[0]['payload_json'])
        payload['title'] = 'changed'
        changed[0]['payload_json'] = canonical_json(payload)
        reasons = scope.scope_reasons(self.value, changed, {**self.binding, 'chat_model': 'new'})
        self.assertEqual({r['code'] for r in reasons}, {'chat_model_changed', 'candidate_source_changed'})
        self.assertEqual(scope.scope_reasons(self.value, [], self.binding)[0]['code'], 'candidate_unavailable')

    def test_empty_scope_never_means_all_topics(self):
        self.value['topic_sources'] = {}
        self.assertEqual(scope.scope_reasons(self.value, self.topics, self.binding)[0]['code'], 'empty_candidate_scope')

    def test_scope_tampering_is_rejected(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {'scope_json': canonical_json(self.value),
                                        'scope_hash': '0' * 64, 'progress_json': '{}'}
        with self.assertRaisesRegex(ValueError, '完整性'):
            scope.read_scope(cursor, 7)

    def test_ready_vector_with_wrong_model_or_taxonomy_is_not_reusable(self):
        topic = self.topics[0]
        topic['taxonomy_version'] = 2
        self.assertEqual(scope.readiness_reasons(self.value, self.topics, CHECKED_AT), [])
        topic['vector_model'] = 'another'
        self.assertEqual(scope.readiness_reasons(self.value, self.topics, CHECKED_AT)[0]['code'],
                         'topic_vector_model_mismatch')
        topic['vector_model'] = 'shared-v1'
        topic['taxonomy_version'] = 1
        self.assertEqual(scope.readiness_reasons(self.value, self.topics, CHECKED_AT)[0]['code'],
                         'topic_taxonomy_mismatch')

    def test_ready_topics_with_wrong_dimensions_or_missing_stable_ids_block_freezing(self):
        reason = scope.readiness_reasons(self.value, self.topics, CHECKED_AT,
                                        {'vector_model': 'shared-v1', 'dimension': 3})
        self.assertEqual(reason[0]['code'], 'topic_vector_space_mismatch')
        self.topics[0]['tag_ids_json'] = '{}'
        self.assertEqual(scope.readiness_reasons(self.value, self.topics, CHECKED_AT)[0]['code'],
                         'topic_label_ids_incomplete')


class ScopedFreezeTests(unittest.TestCase):
    # Reuse the scripted preparation store, but assert the new readiness boundary.
    def test_one_ready_topic_cannot_hide_an_unprepared_scoped_candidate(self):
        helper = prep_fixtures.PreparationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.create()
        helper.store.ready_accounts()
        with patch('app.ai_preparation.readiness_reasons', return_value=[
                {'code': 'topic_awaiting_labels', 'topic_id': 'PENDING'}]):
            result = advance_preparation(123, 1)
        self.assertEqual(result['status'], 'waiting_inputs')
        self.assertFalse(helper.store.frozen_topics)
        self.assertEqual(result['last_report']['waiting_reasons'][0]['topic_id'], 'PENDING')
