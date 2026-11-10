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
    """Only V19 can be approved or start new work; history remains readable."""
    from .matching_quality import IMPLEMENTATION_KEY, QUALITY_PARAMETERS
    from .core.matching_common import REQUIRED_INPUTS, _strict_parameters, _integer, ExecutorPolicyError
    if document.implementation_key != IMPLEMENTATION_KEY:
        return ['仅支持V19算法；旧策略保留历史查询，请创建V19策略版本']
    if document.quality is None or document.schema_version != 2 or document.portfolio is None:
        return ['V19须完整声明映射、召回、精判和组合参数']
    if problems := document.approval_errors():
        return problems
    if set(document.required_inputs) != REQUIRED_INPUTS:
        return ['V19须声明完整冻结输入集合']
    if any(document.decisions[k].parameters != value for k, value in QUALITY_PARAMETERS.items()):
        return ['V19映射、召回与精判参数契约不一致']
    try:
        allocation = _strict_parameters(document, 'ALG-05', {
            'same_account_topic_max', 'global_topic_max', 'global_reuse_penalty', 'official_usage_penalty'})
        _integer(allocation['same_account_topic_max'], 'same_account_topic_max', 1, 1000)
        if allocation['global_topic_max'] is not None:
            _integer(allocation['global_topic_max'], 'global_topic_max', 1, 20000)
        for key in ('global_reuse_penalty', 'official_usage_penalty'):
            if type(allocation[key]) not in (int, float) or allocation[key] != 0:
                raise ExecutorPolicyError('V19复用通过组合目标处理，旧排序惩罚必须为0')
        expected = {
            'ALG-06': {'rounding': 'half_up', 'role_order': 'even_spread'},
            'ALG-07': {'official_usage_unknown_rank': 'after_known'},
        }
        for code, params in expected.items():
            if _strict_parameters(document, code, set(params)) != params:
                raise ExecutorPolicyError(f'{code}参数契约不一致')
        fallback = _strict_parameters(document, 'ALG-08', {'fallback_sort', 'fallback_same_account_max'})
        if fallback['fallback_sort'] != 'heat_desc_topic_id':
            raise ExecutorPolicyError('ALG-08参数契约不一致')
        _integer(fallback['fallback_same_account_max'], 'fallback_same_account_max', 1, 1000)
    except ExecutorPolicyError as exc:
        return [f'V19参数契约不兼容：{exc}']
    return []


def require_v19(document: MatchingPolicyDocument) -> None:
    require_supported_implementation(document)
    if problems := implementation_approval_errors(document):
        raise HTTPException(409, {'message': '当前仅支持V19算法', 'problems': problems})


def require_supported_implementation(document: MatchingPolicyDocument) -> None:
    from .matching_quality import IMPLEMENTATION_KEY
    if document.implementation_key != IMPLEMENTATION_KEY:
        raise HTTPException(409, '仅支持V19算法，旧版本仅用于历史查询')


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
    require_supported_implementation(payload.document)
    encoded = canonical_json(payload.document.model_dump())
    with connection() as db, db.cursor() as cursor:
        lock = f"godp:matching-policy:{payload.policy_key}"
        cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (lock,))
        if cursor.fetchone()["acquired"] != 1:
            raise HTTPException(409, "该算法策略正在更新")
        try:
            cursor.execute("SELECT version FROM godp_matching_policy WHERE del_flag='N' AND policy_key=%s ORDER BY version DESC LIMIT 1 FOR UPDATE", (payload.policy_key,))
            latest = cursor.fetchone()
            version = latest["version"] if latest else 0
            if version != payload.expected_latest_version:
                raise HTTPException(409, "算法策略已有新版本，请重新查询")
            cursor.execute("INSERT INTO godp_matching_policy (policy_key,version,document_json,document_hash,create_by,update_by,created_by,updated_by) VALUES (%s,%s,%s,%s,'matching-policy-api','matching-policy-api',create_by,update_by)",
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
        if not disable:
            require_v19(document)
        if row["status"] == target:
            db.rollback()
            return policy_summary(row)
        if not disable:
            if row["status"] != "draft":
                raise HTTPException(409, "已停用策略不可重新批准，请创建新版本")
            if problems := approval_errors(document):
                raise HTTPException(409, {"message": "算法规则尚未完整确认", "problems": problems})
            cursor.execute("UPDATE godp_matching_policy SET status='approved',confirmed_by=%s, confirmed_at=UTC_TIMESTAMP(6),update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                           (payload.confirmed_by.strip(), payload.confirmed_by.strip(), policy_id))
        else:
            cursor.execute("UPDATE godp_matching_policy SET status='disabled',update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                           (payload.confirmed_by.strip(), policy_id))
        row = select_policy(cursor, policy_id)
        db.commit()
        return policy_summary(row)
