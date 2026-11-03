"""Backfill missing local state for explicitly pending, topic-bound plans.

Run `python -m app.repair_pending_slot_states` to preview; add --apply to repair.
Existing states (including deleted states) are never reset. No integration
events or content-production requests are issued by this repair.
"""

import argparse
import json

from .db import connection


def repair_pending_slot_states(*, apply: bool = False) -> dict:
    with connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT i.id, i.topic_id FROM godp_planning_item i "
            "JOIN godp_planning_batch b ON b.id=i.batch_id "
            "LEFT JOIN godp_slot_state s ON s.item_id=i.id "
            "WHERE i.del_flag='N' AND b.del_flag='N' "
            "AND b.plan_type IN ('auto','manual') AND s.item_id IS NULL "
            "AND NULLIF(TRIM(i.topic_id),'') IS NOT NULL "
            "AND i.status IN ('待生成','待生产','未生成','已规划') "
            "ORDER BY i.id FOR UPDATE"
        )
        rows = cursor.fetchall()
        if apply and rows:
            cursor.executemany(
                "INSERT INTO godp_slot_state "
                "(item_id,slot_id,version,topic_id,production_status,create_by,update_by) "
                "VALUES (%s,%s,1,%s,'planned','slot-state-repair','slot-state-repair')",
                [(row['id'], f"SLOT-{row['id']}", row['topic_id']) for row in rows],
            )
            db.commit()
        return {'applied': apply, 'count': len(rows), 'item_ids': [row['id'] for row in rows]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    print(json.dumps(repair_pending_slot_states(apply=parser.parse_args().apply)))
