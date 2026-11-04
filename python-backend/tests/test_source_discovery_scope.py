from unittest.mock import MagicMock, patch
import pytest
from app import source_discovery as discovery


def test_scoped_discovery_does_not_cancel_unrelated_pending_jobs():
    db=MagicMock();db.__enter__.return_value=db
    cursor=db.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect=[{'acquired':1},{'version':7}]
    cursor.fetchall.return_value=[{'topic_id':'OLD'},{'topic_id':'TARGET'}]
    with patch.object(discovery,'connection',return_value=db),patch.object(discovery,'current_topics',return_value=[]) as source:
        report=discovery.discover_topics(topic_ids=['TARGET'])
    source.assert_called_once_with(cursor,['TARGET'])
    assert report['cancelled']==1
    cancellations=[call for call in cursor.execute.call_args_list if "status='cancelled'" in call.args[0]]
    assert len(cancellations)==1 and cancellations[0].args[1]==('TARGET',)
    scan=[call for call in cursor.execute.call_args_list if 'SELECT topic_id FROM godp_topic_label_job' in call.args[0]][0]
    assert 'topic_id IN (%s)' in scan.args[0] and scan.args[1]==['TARGET']
    db.commit.assert_called_once()


@pytest.mark.parametrize('scope',[[], 'TARGET', [' bad'], [None]])
def test_empty_scope_is_noop_and_bad_scopes_fail_before_database(scope):
    with patch.object(discovery,'connection') as connect:
        if scope==[]:assert discovery.discover_topics(topic_ids=scope)['scanned']==0
        else:
            with pytest.raises(ValueError):discovery.discover_topics(topic_ids=scope)
        connect.assert_not_called()
