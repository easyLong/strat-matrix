"""Planner-owned initial slot state creation."""
def queue_manual_slot(cursor, item_id, batch_id, batch_code, account_id, topic_id, publish_date, operator='system'):
    cursor.execute('INSERT INTO godp_slot_state '
                   '(item_id,slot_id,version,topic_id,create_by,update_by) VALUES (%s,%s,1,%s,%s,%s)',
                   (item_id, f'SLOT-{item_id}', topic_id, operator, operator))
    return False
