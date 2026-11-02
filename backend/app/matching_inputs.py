"""Read current eligible ordinary inputs within the caller's transaction."""


def load_matching_topics(cursor, checked_at, topic_ids=None) -> list[dict]:
    if topic_ids == []:
        return []
    from .bank_bridge.factory import external_source_enabled
    if external_source_enabled():
        from .bank_bridge.bridge import matching_topics
        return (matching_topics(cursor, checked_at, topic_ids=topic_ids) if topic_ids is not None
                else matching_topics(cursor, checked_at))
    scope_sql = (' AND s.topic_id IN (' + ','.join(['%s'] * len(topic_ids)) + ')' if topic_ids else '')
    cursor.execute(
        "SELECT s.topic_id, s.payload_json, s.source_updated_at, s.active_in_snapshot, s.valid_from, s.valid_to, "
        "t.status AS topic_status, t.is_marketing, tag.label_status, tag.tags_json, "
        "tag.tag_ids_json, tag.taxonomy_version, tag.t6_tag_id, "
        "tag.version AS tag_version, p.tag_version AS profile_tag_version, p.content_hash, "
        "p.profile_json, p.status AS profile_status, p.vector_json, p.vector_model "
        "FROM godp_topic_source s JOIN godp_topic t ON t.topic_code=s.topic_id AND t.del_flag='N' "
        "LEFT JOIN godp_topic_tag tag ON tag.topic_id=s.topic_id AND tag.del_flag='N' "
        "LEFT JOIN godp_topic_profile p ON p.topic_id=s.topic_id AND p.del_flag='N' "
        "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND t.status='可用' AND t.is_marketing=0 "
        "AND s.topic_id NOT LIKE 'DEMO-%%' "
        "AND (s.valid_from IS NULL OR s.valid_from<=%s) "
        "AND (s.valid_to IS NULL OR s.valid_to>=%s)" + scope_sql + " ORDER BY s.topic_id",
        (checked_at.replace(tzinfo=None), checked_at.replace(tzinfo=None), *(topic_ids or [])),
    )
    return cursor.fetchall()
