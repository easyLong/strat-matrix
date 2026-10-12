"""Persist immutable reviewed algorithm documents without creating defaults."""

from hashlib import sha256
import json

from fastapi import HTTPException

from .account_profile import canonical_json
from .ai_preparation import utc_text
from .db import connection
from .matching_contracts import MatchingPolicyDocument, PolicyCreate, PolicyConfirmation


def digest(document: str) -> str:
    return sha256(document.encode("utf-8")).hexdigest()


def select_policy(cursor, policy_id: int, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_matching_policy WHERE id=%s AND del_flag='N'"
                   + (" FOR UPDATE" if lock else ""), (policy_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "算法策略版本不存在")
    return row


def intact_document(row: dict) -> MatchingPolicyDocument:
    try:
        document = MatchingPolicyDocument.model_validate_json(row["document_json"])
        # Hash the saved document, not defaults added by a newer model schema.
        # Legacy policy fingerprints remain stable across contract upgrades.
        if digest(canonical_json(json.loads(row["document_json"]))) != row["document_hash"]:
            raise ValueError("策略指纹错误")
        return document
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, "算法策略版本完整性校验未通过") from exc


def policy_summary(row: dict, *, include_document: bool = False) -> dict:
    document = intact_document(row)
    result = {"policy_id": row["id"], "policy_key": row["policy_key"], "version": row["version"],
              "document_hash": row["document_hash"], "status": row["status"],
              "implementation_key": document.implementation_key, "confirmed_by": row["confirmed_by"],
              "confirmed_at": utc_text(row["confirmed_at"]), "approval_errors": document.approval_errors()}
    if include_document:
        result["document"] = json.loads(row["document_json"])
    return result


def create_policy(payload: PolicyCreate) -> dict:
    encoded = canonical_json(payload.document.model_dump())
    with connection() as db, db.cursor() as cursor:
        lock = f"godp:matching-policy:{payload.policy_key}"
        cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (lock,))
        if cursor.fetchone()["acquired"] != 1:
            raise HTTPException(409, "该算法策略正在更新")
        try:
            cursor.execute("SELECT version FROM godp_matching_policy WHERE policy_key=%s "
                           "ORDER BY version DESC LIMIT 1 FOR UPDATE", (payload.policy_key,))
            latest = cursor.fetchone()
            version = latest["version"] if latest else 0
            if version != payload.expected_latest_version:
                raise HTTPException(409, "算法策略已有新版本，请重新查询")
            cursor.execute("INSERT INTO godp_matching_policy "
                           "(policy_key,version,document_json,document_hash,create_by,update_by) "
                           "VALUES (%s,%s,%s,%s,'matching-policy-api','matching-policy-api')",
                           (payload.policy_key, version + 1, encoded, digest(encoded)))
            row = select_policy(cursor, cursor.lastrowid)
            db.commit()
            return policy_summary(row, include_document=True)
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock,))


def confirm_policy(policy_id: int, payload: PolicyConfirmation, *, disable: bool = False) -> dict:
    if not payload.confirmed_by.strip():
        raise HTTPException(422, "规则确认人不能为空")
    with connection() as db, db.cursor() as cursor:
        row = select_policy(cursor, policy_id, lock=True)
        document = intact_document(row)
        if payload.expected_hash != row["document_hash"]:
            raise HTTPException(409, "算法策略指纹不一致")
        target = "disabled" if disable else "approved"
        if row["status"] == target:
            db.rollback()
            return policy_summary(row)
        if not disable:
            if row["status"] != "draft":
                raise HTTPException(409, "已停用策略不可重新批准，请创建新版本")
            if problems := document.approval_errors():
                raise HTTPException(409, {"message": "算法规则尚未完整确认", "problems": problems})
            cursor.execute("UPDATE godp_matching_policy SET status='approved',confirmed_by=%s, "
                           "confirmed_at=UTC_TIMESTAMP(6),update_by=%s WHERE id=%s",
                           (payload.confirmed_by.strip(), payload.confirmed_by.strip(), policy_id))
        else:
            cursor.execute("UPDATE godp_matching_policy SET status='disabled',update_by=%s WHERE id=%s",
                           (payload.confirmed_by.strip(), policy_id))
        row = select_policy(cursor, policy_id)
        db.commit()
        return policy_summary(row)
