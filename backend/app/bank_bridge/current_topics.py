"""Join current source methods to planner extensions without source mirror tables."""

from datetime import datetime, timezone
import json

from .bridge import collect, topic_payload
from .contracts import TopicQuery
from .factory import get_source


def rows(cursor, topic_ids=None, *, available_only=True, as_of=None):
    now = as_of or datetime.now(timezone.utc)
    topics = [t for t in collect(get_source(cursor), 'topics', TopicQuery(
        topic_ids=topic_ids, source='普通', topic_type='非营销', available_only=available_only,
        valid_at=now if available_only else None)) if not t.topic_id.startswith('DEMO-')]
    if not topics:
        return []
    extensions = {}
    for start in range(0, len(topics), 500):
        group = topics[start:start + 500]
        cursor.execute(
            'SELECT tag.topic_id,tag.label_status,tag.tags_json,tag.version AS tag_version,'
            'tag.tag_ids_json,tag.taxonomy_version,tag.t6_tag_id,p.id,p.content_hash,'
            'p.tag_version AS profile_tag_version,p.profile_json,p.status AS profile_status,'
            'p.vector_json,p.vector_model,p.last_error FROM godp_topic_tag tag '
            "LEFT JOIN godp_topic_profile p ON p.topic_id=tag.topic_id AND p.del_flag='N' "
            "WHERE tag.del_flag='N' AND tag.topic_id IN (" + ','.join(['%s'] * len(group)) + ')',
            [t.topic_id for t in group])
        extensions.update({r['topic_id']: r for r in cursor.fetchall()})
    empty = {key: None for key in ('id', 'label_status', 'tags_json', 'tag_ids_json', 'taxonomy_version',
        't6_tag_id', 'tag_version', 'profile_tag_version', 'content_hash', 'profile_json',
        'profile_status', 'vector_json', 'vector_model', 'last_error')}
    def utc(value):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None
    result = []
    for topic in topics:
        # Existing dev inputs retain their exact original payload for hash compatibility.
        payload = topic._local_payload or topic_payload(topic)
        result.append({**empty, **extensions.get(topic.topic_id, {}), 'topic_id': topic.topic_id,
            'title': topic.title, 'payload_json': json.dumps(payload, ensure_ascii=False),
            'source_updated_at': utc(topic.updated_at), 'active_in_snapshot': True,
            'valid_from': utc(topic.valid_from), 'valid_to': utc(topic.valid_to),
            'topic_status': '可用' if topic.available else '停用', 'is_marketing': False})
    return result


def source_row(cursor, topic_id):
    found = rows(cursor, [topic_id])
    return found[0] if found else None
