"""Atomically commit one evaluated AI matching proposal as the formal plan.

The matching task remains the immutable ordinary-topic proposal. This adapter
adds the operational overlay that the proposal deliberately does not own:
hotspot placeholders and account-bound marketing priority slots. A successful
call writes the formal batch/items/slot states, the auto-plan audit snapshot,
and the Pipeline commit state in one database transaction.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import random

from fastapi import HTTPException

from .account_profile import canonical_json, save_batch_account_profiles
from .ai_preparation import load_frozen_inputs, select_preparation
from .db import connection
from .matching_policy import intact_document, select_policy
from .matching_tasks import (InvalidInputs, check_binding, checked_inputs,
                             read_evaluation, select_task)
from .models import StrategyConfig
from .ordinary_planning import PlanningError
from .weekly_planning import load_marketing, round_hotspot_slots


ACTOR = "planning-result-commit"
PLAN_MODE = "ai_matching"
_MISSING = object()


class ResultCommitError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _topic_fields(topic: dict, *, fallback: bool = False) -> dict:
    try:
        source = topic.get("source_payload") or {}
        if fallback:
            title = topic.get("title") or source.get("title") or ""
            content = {}
        else:
            content = (topic.get("profile") or {}).get("content") or {}
            title = source.get("title") or content.get("title") or ""
        outline = (source.get("outline") or source.get("summary")
                   or content.get("outline") or content.get("summary") or "")
        content_type = source.get("content_type") or content.get("content_type") or ""
        topic_id = str(topic["topic_id"])
    except (KeyError, TypeError) as exc:
        raise ResultCommitError("ordinary_snapshot_invalid", "普通选题冻结快照格式错误") from exc
    if not topic_id or not str(title).strip():
        raise ResultCommitError("ordinary_snapshot_invalid", "普通选题冻结快照缺少ID或标题")
    return {"topic_id": topic_id, "title": str(title).strip(), "outline": str(outline),
            "content_type": str(content_type), "topic_type": "普通"}


def _ordinary_positions(inputs: dict, evaluation: dict) -> dict[tuple[str, str], dict]:
    ai_topics = {row["topic_id"]: _topic_fields(row) for row in inputs["topics"]}
    supplemental = inputs.get("supplemental") or {}
    fallback_rows = supplemental.get("fallback_topics")
    if not isinstance(fallback_rows, list):
        raise ResultCommitError("fallback_snapshot_missing", "正式提交缺少冻结普通兜底池")
    fallback_topics = {row["topic_id"]: _topic_fields(row, fallback=True) for row in fallback_rows}
    result = {}
    for position in evaluation.get("positions", []):
        account_id = position.get("account_id")
        publish_date = position.get("publish_date")
        key = (account_id, publish_date)
        if not account_id or not publish_date or key in result:
            raise ResultCommitError("matching_result_invalid", "匹配提案账号日期重复或缺失")
        if position.get("outcome") == "failed":
            raise ResultCommitError(
                "matching_slot_failed",
                f"{account_id} {publish_date} 没有合法普通选题，正式结果不能提交",
            )
        topic_id = position.get("topic_id")
        source = fallback_topics if position.get("outcome") == "fallback" else ai_topics
        topic = source.get(topic_id)
        role = position.get("content_role")
        if topic is None or role not in ("流量", "转化"):
            raise ResultCommitError("matching_result_invalid", "匹配提案引用或经营作用不完整")
        result[key] = {**topic, "content_role": role, "matching_outcome": position["outcome"],
                       "fit_score": position.get("fit_score"), "reason": position.get("reason") or ""}
    return result


def _hotspot_seed(cycle_start: str, config_version: int) -> int:
    return int.from_bytes(
        sha256(f"{cycle_start}:{config_version}:live".encode()).digest()[:8], "big"
    )


def build_final_plan(inputs: dict, evaluation: dict, marketing: list[dict]) -> dict:
    """Pure deterministic ordinary + marketing + hotspot composition."""
    try:
        config = StrategyConfig.model_validate(inputs["config"])
        accounts = inputs["accounts"]
        blueprint = inputs["positions"]
        cycle_start = inputs["cycle_start"]
        config_version = inputs["config_version"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultCommitError("frozen_inputs_invalid", "正式提交读取冻结账号/配置/日期失败") from exc
    if not accounts or not blueprint:
        raise ResultCommitError("frozen_inputs_invalid", "正式提交没有冻结账号或日期安排")

    account_order = [str(row["account_id"]) for row in accounts]
    account_by_id = {str(row["account_id"]): row for row in accounts}
    if len(account_by_id) != len(accounts):
        raise ResultCommitError("frozen_inputs_invalid", "冻结账号编码重复")
    ordinary = _ordinary_positions(inputs, evaluation)
    keys = [(str(row.get("account_id") or ""), str(row.get("publish_date") or "")) for row in blueprint]
    if len(set(keys)) != len(keys) or set(keys) != set(ordinary):
        raise ResultCommitError("matching_result_invalid", "匹配提案没有完整覆盖冻结账号日期安排")

    seed = _hotspot_seed(cycle_start, config_version)
    rng = random.Random(seed)
    hotspot_count = round_hotspot_slots(len(blueprint), config.hotspot_ratio)
    hotspot_positions = set(rng.sample(range(len(blueprint)), hotspot_count)) if hotspot_count else set()

    marketing_by_account: dict[str, list[dict]] = defaultdict(list)
    for topic in marketing:
        marketing_by_account[str(topic.get("account_id") or "")].append(topic)
    for topics in marketing_by_account.values():
        topics.sort(key=lambda row: (row.get("approved_at") or "9999", row.get("topic_id") or ""))

    positions_by_account: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        if key[0] not in account_by_id:
            raise ResultCommitError("frozen_inputs_invalid", "日期安排引用了未冻结账号")
        positions_by_account[key[0]].append(index)

    marketing_slots: dict[int, dict | None] = {}
    for account_id in account_order:
        wrapper = account_by_id[account_id]
        snapshot = wrapper.get("snapshot") or {}
        if not snapshot.get("marketing_eligible"):
            continue
        candidates = marketing_by_account.get(account_id, [])
        # Marketing is a conversion-oriented overlay. Only consume positions
        # already assigned 转化 by Matching Composition so the frozen role mix
        # remains unchanged after the operational overlay.
        eligible = [index for index in positions_by_account[account_id]
                    if index not in hotspot_positions and ordinary[keys[index]]["content_role"] == "转化"]
        count = min(len(candidates), config.marketing_max, len(eligible))
        selected = sorted(rng.sample(eligible, count)) if count else []
        legal = [topic for topic in candidates if topic.get("valid")]
        for offset, index in enumerate(selected):
            marketing_slots[index] = legal[offset] if offset < len(legal) else None

    slots = []
    hotspot_fallbacks = {}
    actual_marketing = marketing_fallback = 0
    for index, _ in enumerate(blueprint):
        account_id, publish_date = keys[index]
        wrapper = account_by_id[account_id]
        snapshot = wrapper.get("snapshot") or {}
        account_name = snapshot.get("account_name") or ""
        lifecycle = (wrapper.get("profile") or {}).get("lifecycle_stage") or snapshot.get("lifecycle_stage")
        base = ordinary[(account_id, publish_date)]
        if not account_name or not lifecycle:
            raise ResultCommitError("account_snapshot_invalid", "冻结账号缺少名称或生命周期阶段")

        common = {"account_id": account_id, "account_name": account_name,
                  "publish_date": publish_date, "lifecycle_stage": lifecycle,
                  "content_role": base["content_role"]}
        if index in hotspot_positions:
            fallback_key = f"{account_id}|{publish_date}"
            hotspot_fallbacks[fallback_key] = {
                key: base[key] for key in ("topic_id", "title", "outline", "content_type", "topic_type")
            }
            slots.append({**common, "slot_type": "hotspot", "topic_id": "",
                          "topic_title": "待热点触发", "topic_type": None,
                          "outline": None, "content_type": None, "status": "待热点触发"})
            continue

        marketing_topic = marketing_slots.get(index, _MISSING)
        if marketing_topic is not _MISSING and marketing_topic is not None:
            if base["content_role"] != "转化":
                raise ResultCommitError("composition_role_changed", "营销覆盖不得改变冻结经营作用")
            slots.append({**common, "slot_type": "marketing_priority",
                          "topic_id": marketing_topic["topic_id"],
                          "topic_title": marketing_topic["title"], "topic_type": "营销",
                          "outline": marketing_topic.get("outline") or "",
                          "content_type": marketing_topic.get("content_type") or "", "status": "已规划"})
            actual_marketing += 1
            continue

        slot_type = "marketing_priority" if index in marketing_slots else "regular"
        if index in marketing_slots:
            marketing_fallback += 1
        slots.append({**common, "slot_type": slot_type,
                      "topic_id": base["topic_id"], "topic_title": base["title"],
                      "topic_type": "普通", "outline": base["outline"],
                      "content_type": base["content_type"], "status": "已规划"})

    traffic = sum(row["content_role"] == "流量" for row in slots)
    conversion = sum(row["content_role"] == "转化" for row in slots)
    composition = next((row.get("summary") or {} for row in evaluation.get("stages", [])
                        if row.get("stage") == "composition"), {})
    if evaluation.get('implementation_key') == 'builtin-v19-quality-v1' and not {
            'actual_traffic_positions', 'actual_conversion_positions'} & composition.keys():
        # Early immutable V19 reports omitted these fields. Compare the overlay
        # against original hash-checked positions; never rewrite saved reports.
        composition = {**composition,
            'actual_traffic_positions':sum(p.get('content_role')=='流量' for p in evaluation['positions']),
            'actual_conversion_positions':sum(p.get('content_role')=='转化' for p in evaluation['positions'])}
    if composition.get("actual_traffic_positions") != traffic \
            or composition.get("actual_conversion_positions") != conversion:
        raise ResultCommitError("composition_role_changed", "正式组合覆盖改变了Matching经营作用数量")

    return {
        "slots": slots,
        "hotspot_positions": sorted(hotspot_positions),
        "hotspot_fallbacks": hotspot_fallbacks,
        "random_seed": seed,
        "hotspot_slots": len(hotspot_positions),
        "marketing_priority_slots": len(marketing_slots),
        "marketing_topics": actual_marketing,
        "marketing_ordinary_fallback_slots": marketing_fallback,
        "traffic_slots": traffic,
        "conversion_slots": conversion,
    }


def _pipeline_row(cursor, pipeline_id: int, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_planning_pipeline_run WHERE id=%s AND del_flag='N'"
                   + (" FOR UPDATE" if lock else ""), (pipeline_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Pipeline运行记录不存在")
    return row


def _stage_row(cursor, pipeline_id: int, stage_key: str, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_planning_stage_run WHERE pipeline_id=%s AND stage_key=%s "
                   "AND del_flag='N'" + (" FOR UPDATE" if lock else ""), (pipeline_id, stage_key))
    row = cursor.fetchone()
    if not row:
        raise ResultCommitError("pipeline_stage_missing", "Pipeline正式提交阶段不存在")
    return row


def _existing_formal_batch(cursor, cycle_start) -> dict | None:
    cursor.execute("SELECT id,batch_code FROM godp_planning_batch WHERE plan_type='auto' "
                   "AND cycle_start=%s AND batch_code NOT LIKE 'DEMO-%%' AND del_flag='N' "
                   "ORDER BY id LIMIT 1 FOR UPDATE", (cycle_start,))
    return cursor.fetchone()


BUSINESS_CONFIG_FIELDS = ("planning_days", "schedule_day", "schedule_time",
                          "marketing_max", "hotspot_ratio")


def _validated_plan(cursor, pipeline: dict, *, lock: bool) -> dict:
    """Read and validate one frozen algorithm proposal without changing business facts."""
    if not pipeline["preparation_id"] or not pipeline["matching_task_id"]:
        raise ResultCommitError("pipeline_backend_missing", "Pipeline尚未绑定完整准备和匹配任务")
    composition_stage = _stage_row(cursor, pipeline["id"], "composition", lock=lock)
    if composition_stage["status"] != "succeeded":
        raise ResultCommitError("composition_not_ready", "选题组合尚未完成，不能生成正式提案")

    preparation = select_preparation(cursor, pipeline["preparation_id"], lock=lock)
    policy = select_policy(cursor, pipeline["policy_id"], lock=lock)
    task = select_task(cursor, pipeline["matching_task_id"], lock=lock)
    if task["preparation_id"] != preparation["id"] or task["policy_id"] != policy["id"]:
        raise ResultCommitError("task_binding_changed", "Pipeline后端绑定与匹配任务不一致")
    if task["status"] != "evaluated":
        raise ResultCommitError("matching_not_evaluated", "匹配提案尚未完成")
    if task.get("production_batch_id") is not None:
        raise ResultCommitError("task_already_committed", "匹配任务已关联其他正式批次")
    try:
        check_binding(task, preparation, policy)
        inputs = checked_inputs(cursor, preparation, policy, datetime.now(timezone.utc), task=task)
    except InvalidInputs as exc:
        raise ResultCommitError(exc.code, "正式提交前匹配输入或策略已失效") from exc
    verified_inputs, _ = load_frozen_inputs(cursor, preparation)
    if canonical_json({k: v for k, v in inputs.items() if k != "supplemental"}) \
            != canonical_json(verified_inputs):
        raise ResultCommitError("snapshot_integrity_error", "冻结匹配输入复核不一致")
    document = intact_document(policy)
    if document.implementation_key == 'builtin-v19-quality-v1' and document.quality.evaluation_only:
        raise ResultCommitError('quality_evaluation_only', 'V19适配质量验证策略只保存提案，暂不提交正式结果')
    evaluation = read_evaluation(task)

    account_snapshots = [row["snapshot"] for row in inputs["accounts"]]
    try:
        marketing, marketing_sync_batch = ([], None) if pipeline.get('planning_scope') == 'ordinary_only' else load_marketing(cursor, account_snapshots)
    except PlanningError as exc:
        raise ResultCommitError("marketing_snapshot_unavailable", str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultCommitError("marketing_snapshot_invalid", "营销选题快照格式错误") from exc
    return {"preparation": preparation, "policy": policy, "task": task,
            "inputs": inputs, "marketing": marketing,
            "marketing_sync_batch": marketing_sync_batch,
            "account_snapshots": account_snapshots,
            "plan": build_final_plan(inputs, evaluation, marketing)}


def _check_business_config(frozen: dict, supplied: dict) -> None:
    """Prevent Java and Python from planning the same cycle with different business rules."""
    try:
        expected = StrategyConfig.model_validate(frozen)
        actual = StrategyConfig.model_validate({**frozen, **supplied})
    except (TypeError, ValueError) as exc:
        raise ResultCommitError("business_config_invalid", "业务配置快照格式无效") from exc
    if set(supplied) != set(BUSINESS_CONFIG_FIELDS) or any(
            getattr(expected, key) != getattr(actual, key) for key in BUSINESS_CONFIG_FIELDS):
        raise ResultCommitError("business_config_mismatch", "Java业务配置与算法冻结输入不一致")


def build_pipeline_proposal(pipeline_id: int, business_config: dict,
                            business_config_version: int) -> dict:
    """Freeze an immutable algorithm handoff; never write a formal business result."""
    if business_config_version < 1:
        raise ResultCommitError("business_config_invalid", "业务配置版本无效")
    with connection() as db, db.cursor() as cursor:
        pipeline = _pipeline_row(cursor, pipeline_id, lock=True)
        if pipeline.get("commit_owner", "python") != "java":
            raise ResultCommitError("proposal_owner_mismatch", "该Pipeline不由Java提交正式结果")
        if pipeline.get("planning_scope") != "ordinary_only":
            raise ResultCommitError("proposal_scope_unsupported", "当前只支持普通选题提案交由Java提交")
        if pipeline.get('business_config_json') is not None:
            _check_business_config(json.loads(pipeline['business_config_json']), business_config)
            if pipeline['business_config_version'] != business_config_version:
                raise ResultCommitError('business_config_mismatch', '提案请求与Pipeline业务配置版本不同')
        cursor.execute("SELECT * FROM godp_algorithm_proposal WHERE del_flag='N' AND pipeline_id=%s FOR UPDATE",
                       (pipeline_id,))
        saved = cursor.fetchone()
        if saved:
            frozen = json.loads(saved["proposal_json"])
            _check_business_config(frozen["business_config"], business_config)
            if saved["business_config_version"] != business_config_version:
                raise ResultCommitError("business_config_mismatch", "冻结提案的业务配置版本不一致")
            return _proposal_envelope(saved["proposal_json"], saved["proposal_hash"])
        if pipeline["status"] == "cancelled" or pipeline.get("production_batch_id") is not None:
            raise ResultCommitError("proposal_unavailable", "Pipeline已取消或已经提交正式结果")
        validated = _validated_plan(cursor, pipeline, lock=True)
        _check_business_config(validated["inputs"]["config"], business_config)
        plan = validated["plan"]
        accounts = {str(row["account_id"]): row["snapshot"]
                    for row in validated["inputs"]["accounts"]}
        slots = [{**slot, "slot_id": f"AUTO-{index + 1:06d}",
                  "account_snapshot": accounts[slot["account_id"]]}
                 for index, slot in enumerate(plan["slots"])]
        proposal = {
            "schema_version": 1,
            "pipeline_id": pipeline_id,
            "cycle_start": pipeline["cycle_start"].isoformat(),
            "cycle_end": pipeline["cycle_end"].isoformat(),
            "planning_scope": "ordinary_only",
            "business_config_version": business_config_version,
            "business_config": business_config,
            "algorithm_config_version": validated["preparation"]["config_version"],
            "policy_id": validated["policy"]["id"],
            "policy_hash": validated["policy"]["document_hash"],
            "matching_task_id": validated["task"]["id"],
            "matching_result_hash": validated["task"]["result_hash"],
            "accounts": accounts,
            "slots": slots,
            "hotspot_fallbacks": plan["hotspot_fallbacks"],
            "hotspot_slots": plan["hotspot_slots"],
        }
        encoded = canonical_json(proposal)
        fingerprint = sha256(encoded.encode("utf-8")).hexdigest()
        cursor.execute("INSERT INTO godp_algorithm_proposal "
                       "(pipeline_id,proposal_hash,proposal_json,business_config_version) "
                       "VALUES (%s,%s,%s,%s)",
                       (pipeline_id, fingerprint, encoded, business_config_version))
        db.commit()
        return _proposal_envelope(encoded, fingerprint)


def _proposal_envelope(encoded: str, fingerprint: str) -> dict:
    # Hash the original UTF-8 string in Java; avoid cross-language float/JSON formatting drift.
    if sha256(encoded.encode("utf-8")).hexdigest() != fingerprint:
        raise ResultCommitError("proposal_integrity_error", "冻结算法提案指纹不一致")
    return {"schema_version": 1, "proposal_json": encoded, "proposal_hash": fingerprint}


def acknowledge_pipeline_proposal(pipeline_id: int, proposal_hash: str,
                                  business_batch_id: int) -> dict:
    """Accept an idempotent Java commit receipt, touching algorithm tables only."""
    if business_batch_id < 1 or len(proposal_hash) != 64:
        raise HTTPException(422, "业务提交凭证无效")
    with connection() as db, db.cursor() as cursor:
        pipeline = _pipeline_row(cursor, pipeline_id, lock=True)
        if pipeline.get("commit_owner", "python") != "java" or pipeline["status"] == "cancelled":
            raise HTTPException(409, "该Pipeline不能确认Java提交")
        cursor.execute("SELECT * FROM godp_algorithm_proposal WHERE del_flag='N' AND pipeline_id=%s FOR UPDATE",
                       (pipeline_id,))
        proposal = cursor.fetchone()
        if not proposal or proposal["proposal_hash"] != proposal_hash:
            raise HTTPException(409, "确认凭证与冻结提案不一致")
        reused = proposal["business_batch_id"] is not None
        if reused:
            if (proposal["business_batch_id"] != business_batch_id
                    or pipeline["production_batch_id"] != business_batch_id):
                raise HTTPException(409, "该提案已关联其他业务批次")
        else:
            if pipeline["production_batch_id"] is not None:
                raise HTTPException(409, "Pipeline已有不同的提交凭证")
            stage = _stage_row(cursor, pipeline_id, "result_commit", lock=True)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cursor.execute("UPDATE godp_matching_task SET production_batch_id=%s,operations_committed_at=%s,version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s AND production_batch_id IS NULL AND status='evaluated'",
                           (business_batch_id, now, ACTOR, pipeline["matching_task_id"]))
            if cursor.rowcount != 1:
                raise HTTPException(409, "匹配任务已经变化，不能关联业务批次")
            detail = canonical_json({"commit_owner": "java", "proposal_hash": proposal_hash,
                                     "business_batch_id": business_batch_id})
            cursor.execute("UPDATE godp_planning_stage_run SET status='succeeded',backend_type='java_business_batch',backend_id=%s,detail_json=%s,error_code='',error_message='',started_at=COALESCE(started_at,%s),finished_at=%s,version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                           (business_batch_id, detail, now, now, ACTOR, stage["id"]))
            cursor.execute("UPDATE godp_planning_pipeline_run SET status='succeeded',current_stage=NULL,production_batch_id=%s,last_error_code='',last_error_message='',version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                           (business_batch_id, ACTOR, pipeline_id))
            cursor.execute("UPDATE godp_algorithm_proposal SET business_batch_id=%s,accepted_at=%s WHERE del_flag='N' AND pipeline_id=%s", (business_batch_id, now, pipeline_id))
            db.commit()
        return {"status": "accepted", "pipeline_id": pipeline_id,
                "proposal_hash": proposal_hash, "business_batch_id": business_batch_id,
                "reused": reused}


def commit_pipeline_result(pipeline_id: int, expected_version: int) -> dict:
    """Create the operations batch and mark Pipeline success atomically."""
    # Read only the immutable cycle identity before taking the named lock. Use
    # a fresh connection for the real transaction so its Repeatable Read
    # snapshot cannot be established while waiting for another cycle writer.
    with connection() as initial_db, initial_db.cursor() as initial_cursor:
        initial = _pipeline_row(initial_cursor, pipeline_id)
        cycle_start = initial["cycle_start"]
    lock_name = f"godp:ordinary:live:{cycle_start:%Y%m%d}"

    with connection() as db, db.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (lock_name,))
        if cursor.fetchone()["acquired"] != 1:
            raise ResultCommitError("cycle_locked", "该周期正式结果正在提交，请稍后重试")
        try:
            pipeline = _pipeline_row(cursor, pipeline_id, lock=True)
            if pipeline.get("commit_owner", "python") != "python":
                raise ResultCommitError("commit_owner_mismatch", "该Pipeline正式结果应由Java提交")
            if pipeline["cycle_start"] != cycle_start:
                raise ResultCommitError("pipeline_cycle_changed", "Pipeline策划周期发生异常变化")
            if pipeline["version"] != expected_version:
                raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
            if pipeline["status"] == "cancelled":
                raise ResultCommitError("pipeline_cancelled", "已取消Pipeline不能提交正式结果")
            if pipeline["production_batch_id"] is not None:
                cursor.execute("SELECT id,batch_code FROM godp_planning_batch WHERE id=%s AND del_flag='N'",
                               (pipeline["production_batch_id"],))
                batch = cursor.fetchone()
                if not batch:
                    raise ResultCommitError("committed_batch_missing", "Pipeline引用的正式批次不存在")
                db.rollback()
                return {"batch_id": batch["id"], "batch_code": batch["batch_code"], "reused": True}
            commit_stage = _stage_row(cursor, pipeline_id, "result_commit", lock=True)
            validated = _validated_plan(cursor, pipeline, lock=True)
            existing = _existing_formal_batch(cursor, pipeline["cycle_start"])
            if existing:
                raise ResultCommitError("formal_batch_conflict", "该周期已存在正式自动策划批次")
            preparation, policy, task = (validated[key] for key in ("preparation", "policy", "task"))
            inputs = validated["inputs"]
            account_snapshots = validated["account_snapshots"]
            marketing = validated["marketing"]
            marketing_sync_batch = validated["marketing_sync_batch"]
            plan = validated["plan"]

            batch_code = f"AUTO-AI-{pipeline['cycle_start']:%Y%m%d}"
            note = (f"AI匹配任务{task['id']}；策略{policy['id']}；热点空槽{plan['hotspot_slots']}；"
                    f"营销优先槽{plan['marketing_priority_slots']}；配置V{preparation['config_version']}")
            cursor.execute(
                "INSERT INTO godp_planning_batch "
                "(batch_code,plan_type,status,cycle_start,cycle_end,account_count,content_count,note,create_by,update_by) "
                "VALUES (%s,'auto','已规划',%s,%s,%s,%s,%s,%s,%s)",
                (batch_code, pipeline["cycle_start"], pipeline["cycle_end"], preparation["account_count"],
                 preparation["slot_count"], note[:500], ACTOR, ACTOR),
            )
            batch_id = cursor.lastrowid
            for slot in plan["slots"]:
                cursor.execute(
                    "INSERT INTO godp_planning_item "
                    "(batch_id,account_id,account_name,publish_date,slot_type,topic_id,topic_title,topic_type,"
                    "outline,content_type,status,lifecycle_stage,content_role,create_by,update_by) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (batch_id, slot["account_id"], slot["account_name"], slot["publish_date"],
                     slot["slot_type"], slot["topic_id"], slot["topic_title"], slot["topic_type"],
                     slot["outline"], slot["content_type"], slot["status"], slot["lifecycle_stage"],
                     slot["content_role"], ACTOR, ACTOR),
                )
                item_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO godp_slot_state (item_id,slot_id,version,topic_id,create_by,update_by) "
                    "VALUES (%s,%s,1,%s,%s,%s)",
                    (item_id, f"SLOT-{item_id}", slot["topic_id"], ACTOR, ACTOR),
                )

            audit_snapshot = {
                "schema_version": 1,
                "planning_scope": pipeline.get('planning_scope', 'full'),
                "mode": PLAN_MODE,
                "pipeline_id": pipeline_id,
                "preparation_id": preparation["id"],
                "matching_task_id": task["id"],
                "matching_result_hash": task["result_hash"],
                "policy_id": policy["id"],
                "policy_hash": policy["document_hash"],
                "marketing_sync_batch_id": marketing_sync_batch,
                "marketing": marketing,
                "hotspot_positions": plan["hotspot_positions"],
                "hotspot_fallbacks": plan["hotspot_fallbacks"],
                "random_seed": plan["random_seed"],
            }
            cursor.execute(
                "INSERT INTO godp_auto_plan_run "
                "(cycle_start,cycle_end,data_scope,plan_mode,batch_id,config_version,config_json,"
                "account_snapshot_json,topic_snapshot_json,account_count,slot_count,status,create_by,update_by) "
                "VALUES (%s,%s,'live',%s,%s,%s,%s,%s,%s,%s,%s,'已规划',%s,%s)",
                (pipeline["cycle_start"], pipeline["cycle_end"], PLAN_MODE, batch_id,
                 preparation["config_version"], canonical_json(inputs["config"]),
                 canonical_json(account_snapshots), canonical_json(audit_snapshot),
                 preparation["account_count"], preparation["slot_count"], ACTOR, ACTOR),
            )
            save_batch_account_profiles(cursor, batch_id, account_snapshots,
                                        preparation["config_version"], ACTOR)

            committed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            cursor.execute(
                "UPDATE godp_matching_task SET production_batch_id=%s,operations_committed_at=%s,version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                (batch_id, committed_at, ACTOR, task["id"]),
            )
            detail = canonical_json({
                "production_batch_id": batch_id,
                "batch_code": batch_code,
                "matching_task_id": task["id"],
                "matching_result_hash": task["result_hash"],
                "hotspot_slots": plan["hotspot_slots"],
                "marketing_priority_slots": plan["marketing_priority_slots"],
                "marketing_topics": plan["marketing_topics"],
                "marketing_ordinary_fallback_slots": plan["marketing_ordinary_fallback_slots"],
                "traffic_slots": plan["traffic_slots"],
                "conversion_slots": plan["conversion_slots"],
            })
            cursor.execute(
                "UPDATE godp_planning_stage_run SET status='succeeded',backend_type='planning_batch',backend_id=%s,detail_json=%s,error_code='',error_message='',started_at=COALESCE(started_at,%s),finished_at=%s,version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                (batch_id, detail, committed_at, committed_at, ACTOR, commit_stage["id"]),
            )
            cursor.execute(
                "UPDATE godp_planning_pipeline_run SET status='succeeded',current_stage=NULL,production_batch_id=%s,last_error_code='',last_error_message='',version=version+1,update_by=%s, updated_by=update_by WHERE del_flag='N' AND id=%s",
                (batch_id, ACTOR, pipeline_id),
            )
            db.commit()
            return {"batch_id": batch_id, "batch_code": batch_code,
                    "slot_count": len(plan["slots"]), "hotspot_slots": plan["hotspot_slots"],
                    "marketing_priority_slots": plan["marketing_priority_slots"], "reused": False}
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
