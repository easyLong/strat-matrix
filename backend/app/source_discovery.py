"""Discover source changes; store processing snapshots only, never base-data copies."""

from datetime import datetime, timezone
from hashlib import sha256
import json

from .db import connection
from .topic_profile import PROFILE_TEXT_FIELDS, profile_from_source
from .bank_bridge.current_topics import rows as current_topics


def source_signature(payload):
    source = json.loads(payload) if isinstance(payload, str) else payload
    value = {key: source.get(key) or '' for key in (*PROFILE_TEXT_FIELDS,
             'related_product', 'related_activity', 'related_hotspot')}
    value['applicable_cities'] = sorted(set(source.get('applicable_cities') or []))
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def discovery_action(topic, job, taxonomy_version):
    """Metadata-only changes do not invalidate labels or call the model again."""
    same_source = bool(job and source_signature(job['source_payload_json']) ==
                       source_signature(topic['payload_json']))
    same_taxonomy = topic.get('taxonomy_version') == taxonomy_version
    profile_current = False
    if topic.get('label_status') == '已完成' and same_taxonomy:
        try:
            _, fingerprint = profile_from_source(topic['payload_json'], topic['tags_json'])
            profile_current = (fingerprint == topic.get('content_hash') and
                               topic['tag_version'] == topic.get('profile_tag_version'))
        except (ValueError, TypeError):
            pass
    if not job or job.get('del_flag', 'N') != 'N':
        return 'baseline' if profile_current else 'enqueue'
    if same_source and job['status'] in ('pending', 'failed', 'processing'):
        if job.get('taxonomy_version') in (None, taxonomy_version):
            return 'unchanged'
    if same_source and profile_current and job['status'] == 'completed':
        return 'unchanged'
    return 'enqueue'


def discover_topics():
    report = dict(scanned=0, enqueued=0, baselined=0, unchanged=0, cancelled=0)
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK('godp:topic-source-discovery',0) acquired")
        if cursor.fetchone()['acquired'] != 1:
            return {**report, 'busy': True}
        try:
            cursor.execute("SELECT version FROM godp_strategy_config "
                           "WHERE config_key='tag_taxonomy' AND del_flag='N'")
            config = cursor.fetchone()
            if not config:
                raise ValueError('选题标签字典尚未配置')
            # Read the whole provider snapshot before cancelling unavailable jobs.
            topics = current_topics(cursor)
            active = {t['topic_id'] for t in topics}
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for topic in topics:
                report['scanned'] += 1
                cursor.execute('SELECT * FROM godp_topic_label_job WHERE topic_id=%s FOR UPDATE',
                               (topic['topic_id'],))
                job = cursor.fetchone()
                action = discovery_action(topic, job, config['version'])
                if action == 'unchanged':
                    report['unchanged'] += 1
                    continue
                status = 'completed' if action == 'baseline' else 'pending'
                cursor.execute(
                    'INSERT INTO godp_topic_label_job '
                    '(topic_id,source_payload_json,source_updated_at,status,taxonomy_version,completed_at,create_by,update_by) '
                    "VALUES (%s,%s,%s,%s,%s,%s,'source-discovery','source-discovery') "
                    'ON DUPLICATE KEY UPDATE source_payload_json=VALUES(source_payload_json),'
                    'source_updated_at=VALUES(source_updated_at),status=VALUES(status),'
                    'taxonomy_version=VALUES(taxonomy_version),completed_at=VALUES(completed_at),'
                    "lease_id=NULL,lease_expires_at=NULL,last_error='',del_flag='N',update_by='source-discovery'",
                    (topic['topic_id'], topic['payload_json'], topic['source_updated_at'], status,
                     config['version'] if action == 'baseline' else None, now if action == 'baseline' else None))
                report['baselined' if action == 'baseline' else 'enqueued'] += 1
                if action == 'enqueue':
                    cursor.execute("UPDATE godp_topic_tag SET label_status='处理中',label_error='',"
                                   "update_by='source-discovery' WHERE topic_id=%s AND del_flag='N'",
                                   (topic['topic_id'],))
                    cursor.execute("UPDATE godp_topic_profile SET status='pending',vector_json=NULL,"
                                   "vector_model=NULL,completed_at=NULL,last_error='',update_by='source-discovery' "
                                   "WHERE topic_id=%s AND del_flag='N'", (topic['topic_id'],))
            cursor.execute("SELECT topic_id FROM godp_topic_label_job WHERE del_flag='N' "
                           "AND status IN ('pending','failed','processing') FOR UPDATE")
            for job in cursor.fetchall():
                if job['topic_id'] not in active:
                    cursor.execute("UPDATE godp_topic_label_job SET status='cancelled',lease_id=NULL,"
                                   "lease_expires_at=NULL,update_by='source-discovery' WHERE topic_id=%s",
                                   (job['topic_id'],))
                    report['cancelled'] += 1
            db.commit()
            return report
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK('godp:topic-source-discovery')")
