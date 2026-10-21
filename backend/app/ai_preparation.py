"""Prepare immutable AI inputs before creating any operations result batch."""

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .account_profile import canonical_json, profile_from_preparation
from .account_metrics import post_time
from .db import connection
from .matching_inputs import load_matching_topics
from .matching_readiness import evaluate_readiness, topic_state
from .models import StrategyConfig
from .ordinary_planning import PlanningError, current_next_monday, load_accounts
from .planning_reservation import reservation_key


ACTOR = "ai-preparation-api"
ACTIVE_STATES = ("waiting_inputs", "blocked", "inputs_frozen")


def today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


@contextmanager
def cycle_transaction(start: date):
    # Same lock as both rule planners. It protects creation and cancellation
    # across planner implementations; row locks protect asynchronous callbacks.
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        lock = f"godp:ordinary:live:{start:%Y%m%d}"
        cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock,))
        if cursor.fetchone()["acquired"] != 1:
            raise HTTPException(409, "该周期策划正在处理，请稍后重试")
        try:
            yield db, cursor
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock,))


def select_preparation(cursor, preparation_id: int, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_ai_preparation WHERE id=%s AND del_flag='N'"
                   + (" FOR UPDATE" if lock else ""), (preparation_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "AI准备记录不存在")
    return row


def summary(row: dict, *, reused: bool = False) -> dict:
    return {
        "preparation_id": row["id"], "preparation_code": row["preparation_code"],
        "cycle_start": row["cycle_start"], "cycle_end": row["cycle_end"],
        "status": ("expired" if row["cycle_end"] < today() and row["status"] != "cancelled"
                   else row["status"]), "version": row["version"],
        "config_version": row["config_version"], "account_count": row["account_count"],
        "scheduled_position_count": row["slot_count"], "frozen_topic_count": row["topic_count"],
        "input_hash": row["input_hash"], "frozen_at": utc_text(row["frozen_at"]),
        "attempt_count": row["attempt_count"],
        "last_report": json.loads(row["last_report_json"]) if row["last_report_json"] else None,
        "production_batch_id": None, "matching_executed": False,
        "algorithm_policy_configured": False, "reused": reused,
    }


def assert_no_result_batch(cursor, start: date) -> None:
    cursor.execute(
        "SELECT id FROM godp_planning_batch WHERE plan_type='auto' AND cycle_start=%s "
        "AND batch_code NOT LIKE 'DEMO-%%' AND del_flag='N' LIMIT 1", (start,),
    )
    if cursor.fetchone():
        raise HTTPException(409, "该周期已有正式自动策划结果，不能叠加AI准备记录")


def create_preparation(cycle_start: date | None = None, account_ids: list[str] | None = None,
                       *, planning_scope: str = 'full') -> dict:
    if planning_scope not in ('full', 'ordinary_only'):
        raise HTTPException(422, '无效的策划范围')
    start = cycle_start or current_next_monday()
    if start.weekday() != 0:
        raise HTTPException(422, "策划周期必须从周一开始")
    if account_ids is not None and (not account_ids or len(set(account_ids)) != len(account_ids)
                                   or any(not value.strip() or len(value) > 64
                                          or value.startswith("DEMO-") for value in account_ids)):
        raise HTTPException(422, "参与账号须为非空、无重复的正式账号编码")
    selection = canonical_json(sorted(account_ids) if account_ids is not None else None)
    with cycle_transaction(start) as (db, cursor):
        cursor.execute("SELECT * FROM godp_ai_preparation WHERE reservation_key=%s "
                       "AND del_flag='N' FOR UPDATE", (reservation_key(start),))
        existing = cursor.fetchone()
        if existing:
            if existing["selection_json"] != selection:
                raise HTTPException(409, "该周期已有不同账号范围的准备记录；请先取消原记录")
            if existing.get('create_by') == 'ordinary-only-preparation' and planning_scope != 'ordinary_only':
                raise HTTPException(409, '该周期已被普通选题流程占用')
            if planning_scope == 'ordinary_only' and existing.get('create_by') != 'ordinary-only-preparation':
                raise HTTPException(409, '该周期已有其他范围的准备记录')
            db.rollback()
            return summary(existing, reused=True)
        if start < current_next_monday():
            raise HTTPException(422, "只能为下周或更晚的周期新建准备记录")
        assert_no_result_batch(cursor, start)
        cursor.execute("SELECT version, config_json FROM godp_strategy_config "
                       "WHERE config_key='operations' AND del_flag='N' FOR UPDATE")
        config_row = cursor.fetchone()
        config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
        config_version = config_row["version"] if config_row else 0
        if planning_scope == 'ordinary_only':
            config = config.model_copy(update={'hotspot_ratio': 0, 'marketing_max': 0})
        try:
            accounts = load_accounts(cursor, "live", config)
        except PlanningError as exc:
            raise HTTPException(409, str(exc)) from exc
        if account_ids is not None:
            chosen = set(account_ids)
            accounts = [account for account in accounts if account["account_id"] in chosen]
            if len(accounts) != len(chosen):
                raise HTTPException(409, "指定账号中存在未同步、停用或缺少完整人设的账号")
        positions = [{"account_id": account["account_id"], "weekday": day,
                      "publish_date": (start + timedelta(days=day - 1)).isoformat()}
                     for account in accounts for day in config.planning_days]
        cursor.execute(
            "INSERT INTO godp_ai_preparation "
            "(preparation_code, reservation_key, cycle_start, cycle_end, selection_json, "
            "config_version, config_json, account_snapshot_json, slot_blueprint_json, "
            "account_count, slot_count, create_by, update_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (f"AI-PREP-{start:%Y%m%d}-{uuid4().hex[:12]}", reservation_key(start),
             start, start + timedelta(days=6), selection, config_version, config.model_dump_json(),
             canonical_json(accounts), canonical_json(positions), len(accounts), len(positions),
             'ordinary-only-preparation' if planning_scope == 'ordinary_only' else ACTOR, ACTOR),
        )
        preparation_id = cursor.lastrowid
        for account in accounts:
            profile_json, fingerprint = profile_from_preparation(account, preparation_id, config_version)
            cursor.execute(
                "INSERT INTO godp_ai_preparation_account "
                "(preparation_id, account_id, config_version, source_updated_at, profile_hash, "
                "snapshot_json, profile_json, create_by, update_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (preparation_id, account["account_id"], config_version,
                 post_time(account["source_updated_at"]).replace(tzinfo=None), fingerprint,
                 canonical_json(account), profile_json, ACTOR, ACTOR),
            )
        row = select_preparation(cursor, preparation_id)
        db.commit()
        return summary(row)


def read_preparation(preparation_id: int) -> dict:
    with connection() as db, db.cursor() as cursor:
        return summary(select_preparation(cursor, preparation_id))


def stable_tags(row: dict) -> bool:
    try:
        ids = json.loads(row["tag_ids_json"])
        return isinstance(ids, dict) and all(isinstance(ids.get(f"T{i}"), str)
                                             and ids[f"T{i}"].strip() for i in range(1, 6)) \
            and type(row["taxonomy_version"]) is int and row["taxonomy_version"] >= 0 \
            and type(row["t6_tag_id"]) is int and row["t6_tag_id"] > 0
    except (KeyError, TypeError, ValueError):
        return False


def utc_text(value) -> str | None:
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def freeze_topic(row: dict) -> dict:
    return {"topic_id": row["topic_id"], "source_payload": json.loads(row["payload_json"]),
            "source_updated_at": utc_text(row["source_updated_at"]),
            "valid_from": utc_text(row["valid_from"]), "valid_to": utc_text(row["valid_to"]),
            "tags": json.loads(row["tags_json"]), "tag_ids": json.loads(row["tag_ids_json"]),
            "taxonomy_version": row["taxonomy_version"], "t6_tag_id": row["t6_tag_id"],
            "tag_version": row["tag_version"], "content_hash": row["content_hash"],
            "profile": json.loads(row["profile_json"]), "vector": json.loads(row["vector_json"]),
            "vector_model": row["vector_model"]}


def load_preparation_accounts(cursor, preparation_id: int) -> list[dict]:
    cursor.execute("SELECT * FROM godp_ai_preparation_account WHERE preparation_id=%s "
                   "AND del_flag='N' ORDER BY account_id", (preparation_id,))
    return cursor.fetchall()


def frozen_input(row: dict, accounts: list[dict], topics: list[dict]) -> dict:
    return {"schema_version": 1, "preparation_id": row["id"],
            "config_version": row["config_version"], "config": json.loads(row["config_json"]),
            "account_count": row["account_count"], "scheduled_position_count": row["slot_count"],
            "account_snapshot_hash": sha256(canonical_json(json.loads(row["account_snapshot_json"]))
                                             .encode("utf-8")).hexdigest(),
            "cycle_start": row["cycle_start"].isoformat(), "cycle_end": row["cycle_end"].isoformat(),
            "positions": json.loads(row["slot_blueprint_json"]),
            "accounts": [{"account_id": profile["account_id"],
                          "snapshot": json.loads(profile["snapshot_json"]),
                          "profile": json.loads(profile["profile_json"]),
                          "profile_hash": profile["profile_hash"],
                          "vector": json.loads(profile["vector_json"]), "vector_model": profile["vector_model"]}
                         for profile in sorted(accounts, key=lambda p: p["account_id"])],
            "topics": sorted(topics, key=lambda topic: topic["topic_id"])}


def input_digest(inputs: dict) -> str:
    return sha256(canonical_json(inputs).encode("utf-8")).hexdigest()


def advance_preparation(preparation_id: int, expected_version: int) -> dict:
    # Obtain the immutable cycle first, then lock the cycle and record in the
    # same order as cancellation, creation and both rule planners.
    with connection() as db, db.cursor() as cursor:
        start = select_preparation(cursor, preparation_id)["cycle_start"]
    with cycle_transaction(start) as (db, cursor):
        row = select_preparation(cursor, preparation_id, lock=True)
        if row["version"] != expected_version:
            raise HTTPException(409, "准备记录已更新，请重新查询版本")
        if row["status"] in ("cancelled", "expired"):
            raise HTTPException(409, "该准备记录已取消或过期")
        if row["cycle_end"] < today():
            cursor.execute("UPDATE godp_ai_preparation SET status='expired', reservation_key=NULL, "
                           "version=version+1, update_by=%s WHERE id=%s", (ACTOR, preparation_id))
            result = summary(select_preparation(cursor, preparation_id))
            db.commit()
            return result
        if row["status"] == "inputs_frozen":
            db.rollback()
            return summary(row, reused=True)
        assert_no_result_batch(cursor, start)
        accounts = load_preparation_accounts(cursor, preparation_id)
        checked_at = datetime.now(timezone.utc)
        topics = load_matching_topics(cursor, checked_at)
        batch = {**row, "batch_id": preparation_id, "batch_code": row["preparation_code"],
                 "batch_account_count": row["account_count"]}
        report = evaluate_readiness(batch, [{**profile, "batch_id": preparation_id} for profile in accounts],
                                    topics, checked_at, profile_builder=profile_from_preparation)
        report.update(preparation_id=preparation_id, account_input_scope="preparation_snapshot")
        report.pop("batch_id")
        report.pop("batch_code")
        space = report["vector_space"]
        selected = [topic for topic in topics if topic_state(topic, checked_at)
                    == ("ready", (space["vector_model"], space["dimension"])) and stable_tags(topic)] if space else []
        report["topics"]["freeze_eligible"] = len(selected)
        if report["inputs_ready"] and not selected:
            report["blocking_reasons"].append({"code": "no_stable_tag_topics",
                                               "message": "兼容选题缺少完整T1至T6稳定ID或字典版本"})
            report.update(inputs_ready=False, status="blocked")
        frozen = report["inputs_ready"]
        # Broken identity/config/model inputs need investigation. Pending or
        # failed model tasks remain retryable waiting inputs.
        structural = {"invalid_config_snapshot", "invalid_account_snapshot", "no_batch_accounts",
                      "account_count_mismatch", "unexpected_account_profiles", "mixed_account_vector_spaces"}
        broken = any(report["accounts"]["counts"][state] for state in
                     ("missing", "incomplete_snapshot", "stale", "invalid_vector"))
        state = ("inputs_frozen" if frozen else "blocked" if broken or any(
            reason["code"] in structural for reason in report["blocking_reasons"]) else "waiting_inputs")
        fingerprint = None
        if frozen:
            snapshots = [freeze_topic(topic) for topic in selected]
            fingerprint = input_digest(frozen_input(row, accounts, snapshots))
            for topic in snapshots:
                cursor.execute("INSERT INTO godp_ai_preparation_topic "
                               "(preparation_id, topic_id, snapshot_json, create_by, update_by) "
                               "VALUES (%s,%s,%s,%s,%s)",
                               (preparation_id, topic["topic_id"], canonical_json(topic), ACTOR, ACTOR))
            report["topic_input_scope"] = "preparation_snapshot"
        cursor.execute(
            "UPDATE godp_ai_preparation SET status=%s, version=version+1, attempt_count=attempt_count+1, "
            "last_report_json=%s, topic_count=%s, input_hash=%s, frozen_at=%s, update_by=%s WHERE id=%s",
            (state, canonical_json(report), len(selected) if frozen else 0, fingerprint,
             checked_at.replace(tzinfo=None) if frozen else None, ACTOR, preparation_id),
        )
        result = summary(select_preparation(cursor, preparation_id))
        db.commit()
        return result


def cancel_preparation(preparation_id: int, expected_version: int) -> dict:
    with connection() as db, db.cursor() as cursor:
        start = select_preparation(cursor, preparation_id)["cycle_start"]
    with cycle_transaction(start) as (db, cursor):
        row = select_preparation(cursor, preparation_id, lock=True)
        if row["version"] != expected_version:
            raise HTTPException(409, "准备记录已更新，请重新查询版本")
        if row["status"] != "cancelled":
            cursor.execute("UPDATE godp_ai_preparation SET status='cancelled', reservation_key=NULL, "
                           "version=version+1, update_by=%s WHERE id=%s", (ACTOR, preparation_id))
        result = summary(select_preparation(cursor, preparation_id))
        db.commit()
        return result


def load_frozen_inputs(cursor, row: dict) -> tuple[dict, list[dict]]:
    """Verify all inputs on the caller's snapshot, including locked task flows."""
    if not row["input_hash"]:
        raise HTTPException(409, "该准备记录尚未冻结完整匹配输入")
    accounts = load_preparation_accounts(cursor, row["id"])
    cursor.execute("SELECT id, snapshot_json FROM godp_ai_preparation_topic "
                   "WHERE preparation_id=%s AND del_flag='N' ORDER BY id", (row["id"],))
    rows = cursor.fetchall()
    try:
        inputs = frozen_input(row, accounts, [json.loads(topic["snapshot_json"]) for topic in rows])
        if len(rows) != row["topic_count"] or len(accounts) != row["account_count"] \
                or input_digest(inputs) != row["input_hash"] or any(p["status"] != "ready" for p in accounts):
            raise ValueError("输入指纹不一致")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(409, "冻结输入完整性校验未通过，请排查准备记录") from exc
    return inputs, rows


def read_inputs(preparation_id: int, after_id: int, limit: int) -> dict:
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        row = select_preparation(cursor, preparation_id)
        inputs, rows = load_frozen_inputs(cursor, row)
        page = [topic for topic in rows if topic["id"] > after_id][:limit]
        inputs["topics"] = [json.loads(topic["snapshot_json"]) for topic in page]
        return {**summary(row), "inputs": inputs,
                "next_after_id": page[-1]["id"] if page else after_id,
                "has_more": any(topic["id"] > page[-1]["id"] for topic in rows) if page else False}


def main():
    parser = argparse.ArgumentParser(description="正式AI输入准备管理；不生成运营结果")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--cycle-start", type=date.fromisoformat)
    create.add_argument("--account-id", action="append")
    for action in ("status", "advance", "cancel"):
        command = sub.add_parser(action)
        command.add_argument("--preparation-id", type=int, required=True)
        if action != "status":
            command.add_argument("--expected-version", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.action == "create":
            result = create_preparation(args.cycle_start, args.account_id)
        elif args.action == "status":
            result = read_preparation(args.preparation_id)
        else:
            handler = advance_preparation if args.action == "advance" else cancel_preparation
            result = handler(args.preparation_id, args.expected_version)
        print(json.dumps(result, ensure_ascii=False, default=str))
    except HTTPException as exc:
        parser.exit(2, f"准备操作未完成：{exc.detail}\n")
    except Exception as exc:
        # DB errors may contain credentials or source payloads.
        parser.exit(1, f"准备操作异常：{type(exc).__name__}；请检查数据库与建表状态\n")


if __name__ == "__main__":
    main()
