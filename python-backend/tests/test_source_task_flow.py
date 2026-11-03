"""Provider-backed hotspot and vector tasks must accept completed Chinese states."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.bank_bridge.factory import use_adapters
from app.bank_bridge.memory import fixture_source
from app.hotspot_scheduler import load_hotspot_candidates
from app.topic_vector_api import topic_vector_jobs, ai_topic_candidates


class SourceTaskFlowTests(unittest.TestCase):
    def row(self, status):
        return dict(id=3, topic_id='T-1', profile_status=status, label_status='已完成',
                    tag_version=2, profile_tag_version=2, payload_json='{}', tags_json='{}',
                    content_hash='test-hash', profile_json='{}', vector_json='[1,0]',
                    vector_model='test-embedding', last_error='')

    def test_hotspot_query_excludes_ordinary_and_marketing_topics(self):
        with use_adapters(fixture_source()):
            rows, identity = load_hotspot_candidates(None, datetime.now(timezone.utc))
        self.assertEqual([row['topic_id'] for row in rows], ['FIXTURE-T003'])
        self.assertTrue(identity.startswith('QUERY-'))

    def test_labeled_pending_profile_is_an_embedding_job(self):
        with patch('app.services.topic_vectors.connection'), \
             patch('app.bank_bridge.current_topics.rows', return_value=[self.row('pending')]), \
             patch('app.services.topic_vectors.profile_from_source', return_value=('profile', 'test-hash')):
            result = topic_vector_jobs()
        self.assertEqual([row['topic_id'] for row in result['jobs']], ['T-1'])

    def test_labeled_ready_profile_is_a_matching_candidate(self):
        with patch('app.services.topic_vectors.connection'), \
             patch('app.bank_bridge.current_topics.rows', return_value=[self.row('ready')]), \
             patch('app.services.topic_vectors.profile_from_source', return_value=('profile', 'test-hash')):
            result = ai_topic_candidates()
        self.assertEqual([row['topic_id'] for row in result['candidates']], ['T-1'])


if __name__ == '__main__':
    unittest.main()
