"""Shared preparations operations used by HTTP and workers."""

from datetime import date
import json
from pydantic import BaseModel, Field
import pymysql
from ..account_profile import profile_from_preparation
from .account_vectors import AccountVectorResult
from ..ai_preparation import (ACTIVE_STATES, advance_preparation, cancel_preparation, create_preparation,
                             read_inputs, read_preparation, select_preparation, summary, today)
from ..db import connection
from ..matching_readiness import account_state
from ..vector_utils import normalized_vector
from .errors import ApplicationError, db_error



class PreparationCreate(BaseModel):
    cycle_start: date | None = None
    account_ids: list[str] | None = Field(default=None, min_length=1, max_length=2000)

class PreparationAction(BaseModel):
    expected_version: int = Field(ge=1)

def guarded(handler, *args):
    try:
        return handler(*args)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc

def create_ai_preparation(payload: PreparationCreate) -> dict:
    return guarded(create_preparation, payload.cycle_start, payload.account_ids)

def list_ai_preparations(after_id: int = 0, limit: int = 100) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM godp_ai_preparation WHERE del_flag='N' AND id>%s "
                           "ORDER BY id LIMIT %s", (after_id, limit))
            rows = cursor.fetchall()
        return {"preparations": [summary(row) for row in rows],
                "next_after_id": rows[-1]["id"] if rows else after_id}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc

def ai_preparation_status(preparation_id: int) -> dict:
    return guarded(read_preparation, preparation_id)

def advance_ai_preparation(preparation_id: int, payload: PreparationAction) -> dict:
    return guarded(advance_preparation, preparation_id, payload.expected_version)

def cancel_ai_preparation(preparation_id: int, payload: PreparationAction) -> dict:
    return guarded(cancel_preparation, preparation_id, payload.expected_version)

def ai_preparation_inputs(preparation_id: int, after_id: int = 0,
                          limit: int = 100) -> dict:
    return guarded(read_inputs, preparation_id, after_id, limit)

def intact_account(profile: dict, preparation: dict) -> bool:
    try:
        snapshots = json.loads(preparation["account_snapshot_json"])
        snapshot = next(account for account in snapshots if account["account_id"] == profile["account_id"])
        state, _ = account_state(snapshot, {**profile, "batch_id": profile["preparation_id"]},
                                 {"batch_id": preparation["id"], "config_version": preparation["config_version"]},
                                 profile_from_preparation)
        return state in ("pending", "failed", "ready")
    except (KeyError, TypeError, ValueError, StopIteration):
        return False

def preparation_account_jobs(after_id: int = 0, limit: int = 100,
                             preparation_id: int | None = None) -> dict:
    query = ("SELECT p.*, r.preparation_code, r.config_version AS frozen_config_version, "
             "r.account_snapshot_json FROM godp_ai_preparation_account p "
             "JOIN godp_ai_preparation r ON r.id=p.preparation_id AND r.del_flag='N' "
             "WHERE p.del_flag='N' AND p.status IN ('pending','failed') "
             "AND r.status IN ('waiting_inputs','blocked') AND r.cycle_end>=%s "
             "AND r.reservation_key IS NOT NULL AND p.id>%s ")
    params = [today(), after_id]
    if preparation_id is not None:
        query += "AND p.preparation_id=%s "
        params.append(preparation_id)
    query += "ORDER BY p.id LIMIT %s"
    params.append(limit)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        jobs = []
        for row in rows:
            preparation = {"id": row["preparation_id"], "config_version": row["frozen_config_version"],
                           "account_snapshot_json": row["account_snapshot_json"]}
            if intact_account(row, preparation):
                jobs.append({**{key: row[key] for key in ("id", "preparation_id", "preparation_code",
                              "account_id", "config_version", "profile_hash", "status", "last_error")},
                             "profile": json.loads(row["profile_json"])})
        return {"jobs": jobs, "next_after_id": rows[-1]["id"] if rows else after_id}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc

def save_preparation_account_vector(preparation_id: int, account_id: str, payload: AccountVectorResult) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            preparation = select_preparation(cursor, preparation_id, lock=True)
            if preparation["status"] not in ACTIVE_STATES or preparation["cycle_end"] < today():
                raise ApplicationError(409, "准备记录已取消或过期，不再接收向量")
            cursor.execute("SELECT * FROM godp_ai_preparation_account "
                           "WHERE preparation_id=%s AND account_id=%s AND del_flag='N' FOR UPDATE",
                           (preparation_id, account_id))
            profile = cursor.fetchone()
            if not profile:
                raise ApplicationError(404, "该准备记录没有指定账号画像")
            if not intact_account(profile, preparation) or profile["profile_hash"] != payload.profile_hash:
                raise ApplicationError(409, "向量与准备记录冻结的账号画像不一致")
            vector = normalized_vector(payload.vector, payload.vector_model, "账号") if payload.status == "ready" else None
            vector_json = json.dumps(vector, separators=(",", ":")) if vector else None
            model = payload.vector_model.strip() if vector else None
            if profile["status"] == "ready":
                if payload.status != "ready" or profile["vector_json"] != vector_json or profile["vector_model"] != model:
                    raise ApplicationError(409, "准备账号向量已就绪，不支持覆盖或退回失败")
            elif preparation["status"] == "inputs_frozen":
                raise ApplicationError(409, "匹配输入已冻结，不支持改变账号向量")
            else:
                cursor.execute(
                    "UPDATE godp_ai_preparation_account SET status=%s, vector_json=%s, vector_model=%s, last_error=%s, completed_at=IF(%s='ready',UTC_TIMESTAMP(6),NULL), update_by='account-vector-worker', updated_by=update_by WHERE del_flag='N' AND id=%s",
                    (payload.status, vector_json, model, payload.error.strip() if payload.status == "failed" else "",
                     payload.status, profile["id"]),
                )
                db.commit()
        return {"preparation_id": preparation_id, "account_id": account_id,
                "profile_hash": payload.profile_hash, "status": payload.status}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
