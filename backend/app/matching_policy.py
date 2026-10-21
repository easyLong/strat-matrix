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


def implementation_approval_errors(document: MatchingPolicyDocument) -> list[str]:
    """Validate known executor contracts without inventing rules for unknown engines."""
    if document.implementation_key not in {
        "builtin-cosine-balanced-v1", "builtin-cosine-portfolio-v2",
    }:
        return []
    from .matching_executor import ExecutorPolicyError, executor_config
    try:
        raw = document.model_dump(mode="json")
        if document.implementation_key == "builtin-cosine-balanced-v1":
            if document.portfolio is not None:
                return ["V1策略不能包含V2组合目标参数"]
            executor_config(raw)
        else:
            if document.portfolio is None:
                return ["V2策略必须完整声明组合目标与MMR参数"]
            if document.schema_version != 2:
                return ["V2组合执行器要求策略schema_version=2"]
            if set(document.required_inputs) != {
                "accounts", "topics", "config", "positions",
                "fallback_topics", "history", "official_usage",
            }:
                return ["V2当前要求与V1相同的冻结输入集合"]
            # V2 portfolio optimization intentionally starts from the approved
            # deterministic cosine candidate contract. Only the composition
            # objective and allocation search differ in this implementation.
            raw["implementation_key"] = "builtin-cosine-balanced-v1"
            executor_config(raw)
            allocation = document.decisions["ALG-05"].parameters
            if allocation["global_reuse_penalty"] != 0 \
                    or allocation["official_usage_penalty"] != 0:
                return ["V2组合执行器要求旧版选题复用排序惩罚均为0"]
    except ExecutorPolicyError as exc:
        return [f"内置执行器参数契约不兼容：{exc}"]
    except (TypeError, ValueError) as exc:
        return [f"内置执行器策略无法解析：{type(exc).__name__}"]
    return []


def approval_errors(document: MatchingPolicyDocument) -> list[str]:
    problems = document.approval_errors()
    if not problems:
        problems.extend(implementation_approval_errors(document))
    return problems


def policy_summary(row: dict, *, include_document: bool = False) -> dict:
    document = intact_document(row)
    result = {"policy_id": row["id"], "policy_key": row["policy_key"], "version": row["version"],
              "document_hash": row["document_hash"], "status": row["status"],
              "implementation_key": document.implementation_key, "confirmed_by": row["confirmed_by"],
              "confirmed_at": utc_text(row["confirmed_at"]), "approval_errors": approval_errors(document)}
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
            if problems := approval_errors(document):
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
