"""Read current content-production counts."""
import pymysql
from ..db import connection
from .errors import db_error
def topic_usage(topic_id: str) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS generated_count FROM godp_slot_state "
                "WHERE topic_id=%s AND production_status IN ('generated','published') "
                "AND del_flag='N'", (topic_id,),
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "generated_count": row["generated_count"]}
