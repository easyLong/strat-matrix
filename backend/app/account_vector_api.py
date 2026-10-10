"""Internal account vector preparation scoped to a frozen planning batch."""

from datetime import date, datetime, timezone
import json
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
import pymysql

from .account_profile import profile_from_snapshot
from .db import connection
from .integration import db_error, require_integration_token
from .vector_utils import normalized_vector


router = APIRouter(dependencies=[Depends(require_integration_token)])
VectorValue = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PROFILE_SELECT = (
    "SELECT p.*, b.batch_code, b.cycle_start, b.cycle_end "
    "FROM godp_account_profile p "
    "JOIN godp_planning_batch b ON b.id=p.batch_id AND b.del_flag='N' AND b.plan_type='auto' "
    "JOIN godp_auto_plan_run r ON r.batch_id=p.batch_id AND r.del_flag='N' "
    "AND r.data_scope='live' AND r.config_version=p.config_version "
    "WHERE p.del_flag='N' AND p.account_id NOT LIKE 'DEMO-%%' "
)


class AccountVectorResult(BaseModel):
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready", "failed"] = "ready"
    vector: list[VectorValue] | None = Field(default=None, min_length=1, max_length=4096)
    vector_model: str | None = Field(default=None, min_length=1, max_length=100)
    error: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_result(self):
        if self.status == "ready":
            normalized_vector(self.vector, self.vector_model, "账号")
            if self.error:
                raise ValueError("已就绪结果不能包含错误原因")
        elif not self.error.strip() or self.vector is not None or self.vector_model is not None:
            raise ValueError("失败结果必须包含错误原因，且不能包含向量")
        return self


def beijing_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def intact_profile(row: dict) -> bool:
    try:
        profile_json, profile_hash = profile_from_snapshot(
            json.loads(row["snapshot_json"]), row["batch_id"], row["config_version"],
        )
        return profile_hash == row["profile_hash"] and profile_json == row["profile_json"]
    except (KeyError, TypeError, ValueError):
        return False


def profile_item(row: dict, include_vector: bool = False) -> dict:
    item = {key: row[key] for key in (
        "id", "batch_id", "batch_code", "account_id", "config_version", "profile_hash", "status",
    )}
    item["profile"] = json.loads(row["profile_json"])
    if include_vector:
        item.update(vector=json.loads(row["vector_json"]), vector_model=row["vector_model"])
    else:
        item["last_error"] = row["last_error"]
    return item


@router.get("/api/internal/account-profiles/{batch_id}/{account_id}")
def account_profile_status(batch_id: int, account_id: str) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(PROFILE_SELECT + "AND p.batch_id=%s AND p.account_id=%s", (batch_id, account_id))
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    if not row:
        raise HTTPException(status_code=404, detail="该正式批次没有完整账号画像快照")
    status = row["status"] if intact_profile(row) else "stale"
    if status == "ready" and (row["vector_json"] is None or not row["vector_model"]):
        status = "stale"
    return {"batch_id": batch_id, "account_id": account_id, "status": status,
            "profile_hash": row["profile_hash"], "config_version": row["config_version"],
            "source_updated_at": row["source_updated_at"].replace(tzinfo=timezone.utc),
            "vector_model": row["vector_model"] if status == "ready" else None,
            "last_error": row["last_error"] if status == "failed" else "",
            "completed_at": (row["completed_at"].replace(tzinfo=timezone.utc)
                             if status == "ready" and row["completed_at"] else None)}


@router.get("/api/internal/account-vector-jobs")
def account_vector_jobs(limit: int = Query(100, ge=1, le=200),
                        after_id: int = Query(0, ge=0),
                        batch_id: int | None = Query(None, ge=1)) -> dict:
    query = PROFILE_SELECT + "AND p.id>%s AND p.status IN ('pending','failed') AND b.cycle_end>=%s "
    params = [after_id, beijing_today()]
    if batch_id is not None:
        query += "AND p.batch_id=%s "
        params.append(batch_id)
    query += "ORDER BY p.id LIMIT %s"
    params.append(limit)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"next_after_id": rows[-1]["id"] if rows else after_id,
            "jobs": [profile_item(row) for row in rows if intact_profile(row)]}


@router.put("/api/internal/account-vectors/{batch_id}/{account_id}")
def save_account_vector(batch_id: int, account_id: str, payload: AccountVectorResult) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(PROFILE_SELECT + "AND p.batch_id=%s AND p.account_id=%s FOR UPDATE",
                           (batch_id, account_id))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="该正式批次没有完整账号画像快照")
            if row["cycle_end"] < beijing_today():
                raise HTTPException(status_code=409, detail="该策划周期已结束，不再接收向量准备结果")
            if not intact_profile(row) or row["profile_hash"] != payload.profile_hash:
                raise HTTPException(status_code=409, detail="账号向量与该批次冻结的画像版本不一致")
            vector = (normalized_vector(payload.vector, payload.vector_model, "账号")
                      if payload.status == "ready" else None)
            vector_json = json.dumps(vector, separators=(",", ":")) if vector else None
            vector_model = payload.vector_model.strip() if vector else None
            if row["status"] == "ready":
                if payload.status != "ready" or row["vector_json"] != vector_json \
                        or row["vector_model"] != vector_model:
                    raise HTTPException(status_code=409, detail="该批次账号向量已就绪，不支持覆盖或退回失败")
            else:
                cursor.execute(
                    "UPDATE godp_account_profile SET status=%s, vector_json=%s, vector_model=%s, "
                    "last_error=%s, completed_at=IF(%s='ready', UTC_TIMESTAMP(6), NULL), "
                    "update_by='account-vector-worker' WHERE id=%s",
                    (payload.status, vector_json, vector_model,
                     payload.error.strip() if payload.status == "failed" else "", payload.status, row["id"]),
                )
                db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"batch_id": batch_id, "account_id": account_id,
            "profile_hash": payload.profile_hash, "status": payload.status}


@router.get("/api/internal/ai-account-candidates")
def ai_account_candidates(batch_id: int = Query(..., ge=1),
                          limit: int = Query(100, ge=1, le=200),
                          after_id: int = Query(0, ge=0)) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                PROFILE_SELECT + "AND p.batch_id=%s AND p.id>%s AND p.status='ready' "
                "AND p.vector_json IS NOT NULL AND p.vector_model IS NOT NULL "
                "AND b.cycle_end>=%s ORDER BY p.id LIMIT %s",
                (batch_id, after_id, beijing_today(), limit),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"batch_id": batch_id, "next_after_id": rows[-1]["id"] if rows else after_id,
            "candidates": [profile_item(row, include_vector=True) for row in rows if intact_profile(row)]}
