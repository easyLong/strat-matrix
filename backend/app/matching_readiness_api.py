"""Protected, read-only preparation check for formal matching inputs."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
import pymysql

from .db import connection
from .integration import db_error, require_integration_token
from .matching_readiness import evaluate_readiness


router = APIRouter(dependencies=[Depends(require_integration_token)])


@router.get("/api/internal/matching-readiness")
def matching_readiness(batch_id: int = Query(..., ge=1)) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            checked_at = datetime.now(timezone.utc)
            cursor.execute(
                "SELECT b.id AS batch_id, b.batch_code, b.cycle_end, "
                "b.account_count AS batch_account_count, r.config_version, r.config_json, "
                "r.account_snapshot_json, r.account_count FROM godp_planning_batch b "
                "JOIN godp_auto_plan_run r ON r.batch_id=b.id AND r.del_flag='N' "
                "AND r.data_scope='live' WHERE b.id=%s AND b.del_flag='N' "
                "AND b.plan_type='auto' AND b.batch_code NOT LIKE 'DEMO-%%'",
                (batch_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="正式自动策划批次或运行快照不存在")
            if len(rows) != 1:
                raise HTTPException(status_code=409, detail="该批次存在重复运行快照")
            batch = rows[0]
            cursor.execute(
                "SELECT batch_id, account_id, config_version, snapshot_json, profile_json, "
                "profile_hash, status, vector_json, vector_model FROM godp_account_profile "
                "WHERE batch_id=%s AND del_flag='N' ORDER BY account_id", (batch_id,),
            )
            profiles = cursor.fetchall()
            cursor.execute(
                "SELECT s.topic_id, s.payload_json, s.active_in_snapshot, s.valid_from, s.valid_to, "
                "t.status AS topic_status, t.is_marketing, tag.label_status, tag.tags_json, "
                "tag.version AS tag_version, p.tag_version AS profile_tag_version, p.content_hash, "
                "p.profile_json, p.status AS profile_status, p.vector_json, p.vector_model "
                "FROM godp_topic_source s JOIN godp_topic t ON t.topic_code=s.topic_id AND t.del_flag='N' "
                "LEFT JOIN godp_topic_tag tag ON tag.topic_id=s.topic_id AND tag.del_flag='N' "
                "LEFT JOIN godp_topic_profile p ON p.topic_id=s.topic_id AND p.del_flag='N' "
                "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND t.status='可用' AND t.is_marketing=0 "
                "AND s.topic_id NOT LIKE 'DEMO-%%' "
                "AND (s.valid_from IS NULL OR s.valid_from<=%s) "
                "AND (s.valid_to IS NULL OR s.valid_to>=%s) ORDER BY s.topic_id",
                (checked_at.replace(tzinfo=None), checked_at.replace(tzinfo=None)),
            )
            topics = cursor.fetchall()
            report = evaluate_readiness(batch, profiles, topics, checked_at)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return report
