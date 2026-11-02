"""Planner-owned result projections; source hydration is delegated to its adapter."""
from ..bank.catalog import hydrate

def items(cursor, where, params, order, limit=5000):
    cursor.execute(
        'SELECT i.*,s.slot_id,s.production_status,s.topic_id AS slot_topic_id,s.published_at,s.version,'
        'b.batch_code,b.plan_type,b.create_time AS batch_created_at,b.cycle_start,b.cycle_end '
        'FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id '
        "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
        "WHERE i.del_flag='N' AND b.del_flag='N' AND " + where + ' ORDER BY ' + order + ' LIMIT %s',
        [*params, limit])
    return hydrate(cursor, cursor.fetchall())


def planning_accounts(cursor, limit):
    cursor.execute(
        "SELECT i.account_id,MAX(i.account_name) AS account_name,'' AS account_owner,"
        'COUNT(DISTINCT b.cycle_start) AS cycle_count,COUNT(*) AS slot_count,'
        'MAX(b.cycle_start) AS latest_cycle_start,MAX(b.create_time) AS latest_cycle_updated_at,'
        "SUBSTRING_INDEX(GROUP_CONCAT(b.status ORDER BY b.create_time DESC,b.id DESC),',',1) AS latest_status,"
        "CAST(SUBSTRING_INDEX(GROUP_CONCAT(b.id ORDER BY b.create_time DESC,b.id DESC),',',1) AS UNSIGNED) AS latest_batch_id "
        'FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id '
        "WHERE i.del_flag='N' AND b.del_flag='N' GROUP BY i.account_id "
        'ORDER BY latest_cycle_updated_at DESC,account_name,i.account_id LIMIT %s', (limit,))
    return hydrate(cursor, cursor.fetchall())
