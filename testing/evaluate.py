"""Run the actual V19 executor with replayed external boundaries only."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import subprocess
import time
from unittest.mock import patch

from .datasets import ROOT, PERSONAS, canonical, digest
from hashlib import sha256


@contextmanager
def offline_boundary():
    """Fail immediately if an executor accidentally reaches a real DB or network."""
    def deny(*_args, **_kwargs):
        raise RuntimeError("离线回归禁止网络和数据库访问")
    with ExitStack() as stack:
        for target in ("pymysql.connect", "socket.socket.connect", "socket.socket.connect_ex"):
            stack.enter_context(patch(target, side_effect=deny))
        yield


class ReplayRuntime:
    """In-memory replacement of the model cache/progress I/O, not the algorithm."""
    def __init__(self, context, renew):
        self.context, self.renew, self.cache = context, renew, {}
        self.stats = {"model_calls": 0, "replay_batches": 0, "cache_hits": 0, "cache_writes": 0}

    def find(self, kind, payload, **_options):
        key = (kind, canonical(payload))
        if key in self.cache:
            self.stats["cache_hits"] += 1
            return deepcopy(self.cache[key])
        return None

    def save(self, kind, payload, value):
        self.cache[(kind, canonical(payload))] = deepcopy(value)
        self.stats["cache_writes"] += 1
        return deepcopy(value)

    def call(self, compute):
        self.stats["replay_batches"] += 1
        self.renew()
        return compute()

    def cached(self, kind, payload, compute, validate=lambda value: value):
        value = self.find(kind, payload)
        if value is None:
            value = self.save(kind, payload, validate(self.call(compute)))
        return validate(value)


def job_for(dataset, engine, candidate_policy=None):
    from app.matching_contracts import MatchingPolicyDocument
    from app.matching_policy import implementation_approval_errors
    policy = deepcopy(candidate_policy or dataset["policies"][engine])
    expected_key = {"v19": "builtin-v19-quality-v1"}[engine]
    document = MatchingPolicyDocument.model_validate(policy)
    if document.implementation_key != expected_key or document.vector_space.vector_model != dataset["vector_space"] or document.vector_space.dimension != 8:
        raise ValueError("候选策略的算法或向量空间与测试集不一致")
    errors = implementation_approval_errors(document)
    if errors:
        raise ValueError("候选策略契约无效：" + ";".join(errors))
    selected = set(dataset["frozen_topic_ids"])
    topics = [deepcopy(t) for t in dataset["topics"] if t["topic_id"] in selected]
    inputs = dict(accounts=deepcopy(dataset["accounts"]), topics=topics, positions=deepcopy(dataset["positions"]),
                  config=deepcopy(dataset["config"]), supplemental={"fallback_topics": [],
                  "history": {"observed_records": deepcopy(dataset["history"])},
                  "official_usage": {"records": [{"topic_id": t["topic_id"], "known": True, "official_use_count": 0} for t in topics]}})
    if engine == "v19":
        inputs["supplemental"]["quality_context"] = dict(
            taxonomy=deepcopy(dataset["taxonomy"]), taxonomy_version=1,
            mapping_rules=deepcopy(dataset["mapping_rules"]), options=document.quality.model_dump(mode="json", exclude_none=True),
            chat_model=dataset["replay"]["chat_model"], embedding_model=dataset["vector_space"], topic_needs={})
    return dict(task_id=1, lease_id="a" * 32, input_hash=digest(inputs), policy_hash=digest(policy), policy=policy, inputs=inputs)


def quality_replay(job, dataset):
    from app import matching_quality_executor as executor
    from app.matching_quality_model import PairJudgment, checked_annotation
    replay = dataset["replay"]
    by_title = {t["source_payload"]["title"]: t["topic_id"] for t in dataset["topics"]}
    captured, phases = {}, []

    def annotations(context, topics):
        return {key: checked_annotation(replay["annotations"][by_title[value["title"]]], context)
                for key, value in topics.items()}

    def judgments(_context, account, topics):
        persona = account["raw"]["persona"]
        return {key: PairJudgment.model_validate(replay["pairs_by_persona"][persona][by_title[value["content"]["title"]]]).model_dump()
                for key, value in topics.items()}

    def checkpoint(_job, report, status, phase):
        phases.append((status, phase))
        if status == "ready":
            captured.update(deepcopy(report))

    def no_account_inference(*_args):
        raise ValueError("固定映射不足，禁止测试工具自行推测账号画像")

    with ExitStack() as stack:
        for name, value in {
            "QualityRuntime": ReplayRuntime, "annotate_batch": annotations, "judge_batch": judgments,
            "map_account": no_account_inference, "save_quality_report": checkpoint,
            "topic_need_vectors": lambda _context: {str(i + 1): v for i, v in enumerate(replay["need_vectors"].values())},
            "_need_vector": lambda _runtime, text, dimension: replay["need_vectors"][text],
        }.items():
            stack.enter_context(patch.object(executor, name, value))
        stack.enter_context(patch("app.matching_tasks.heartbeat_task", lambda *_args: None))
        result = executor.execute_quality_job(job)
    if not captured:
        raise ValueError("V19未形成完整回放报告")
    return result, captured, phases


def metrics(dataset, result, engine, quality):
    from app.core.matching_common import city_allowed, role_plan, stage_targets
    accounts = {a["account_id"]: a for a in dataset["accounts"]}
    topics = {t["topic_id"]: t for t in dataset["topics"]}
    history = {(r["account_id"], r["topic_id"]) for r in dataset["history"]}
    roles, assigned, seen = {}, [], set()
    targets = stage_targets({"config": dataset["config"]})
    for account in accounts.values():
        positions = [p for p in dataset["positions"] if p["account_id"] == account["account_id"]]
        roles.update(role_plan(account, positions, targets[account["profile"]["lifecycle_stage"]]))
    output = dict(total_positions=len(result.positions), matched_positions=0, fallback_positions=0, failed_positions=0,
                  history_violations=0, city_violations=0, role_violations=0, duplicate_account_topics=0,
                  source_scope_violations=0, persona_violations=0, rejected_precision_used=0)
    expected_slots = {(p["account_id"], p["publish_date"]) for p in dataset["positions"]}
    actual_slots = {(p.account_id, str(p.publish_date)) for p in result.positions}
    output["position_shape_violations"] = len(expected_slots ^ actual_slots) + len(result.positions) - len(actual_slots)
    for p in result.positions:
        if p.outcome == "failed":
            output["failed_positions"] += 1
            continue
        output["matched_positions" if p.outcome == "matched" else "fallback_positions"] += 1
        topic, account = topics[p.topic_id], accounts[p.account_id]
        key = (p.account_id, p.topic_id)
        output["history_violations"] += int(key in history)
        output["city_violations"] += int(not city_allowed(account, topic))
        output["role_violations"] += int(topic["tags"]["T2"][0] != roles[(p.account_id, str(p.publish_date))])
        output["source_scope_violations"] += int(p.topic_id not in dataset["frozen_topic_ids"])
        output["duplicate_account_topics"] += int(key in seen)
        seen.add(key)
        output["persona_violations"] += int(account["profile"]["account"]["persona"] != PERSONAS[topic["fixture_domain"]])
        if engine == "v19":
            precision = {r["topic_id"]: r for r in quality["accounts"][p.account_id]["precision"]}
            output["rejected_precision_used"] += int(not precision.get(p.topic_id, {}).get("accepted"))
        assigned.append(p.fit_score or 0)
    output["coverage_rate"] = (output["matched_positions"] + output["fallback_positions"]) / max(1, output["total_positions"])
    output["distinct_topics"] = len({p.topic_id for p in result.positions if p.topic_id})
    output["mean_fit_score"] = sum(assigned) / max(1, len(assigned))
    return output


def evaluate(dataset, candidate_policy=None, engine_filter=None):
    if engine_filter not in (None, ("v19",), ["v19"]):
        raise ValueError("Only V19 is supported")
    if candidate_policy and set(candidate_policy) - {"v19"}:
        raise ValueError("Only V19 is supported")
    engines = {}
    with offline_boundary():
        for engine in engine_filter or ("v19",):
            job = job_for(dataset, engine, (candidate_policy or {}).get(engine))
            started = time.monotonic()
            result, quality = None, {}
            result, quality, _ = quality_replay(job, dataset)
            values = metrics(dataset, result, engine, quality)
            thresholds = {**dataset["expected"]["shared"], **dataset["expected"].get(engine, {})}
            checks = [{"metric": key[:-4], "value": values[key[:-4]], "maximum": maximum,
                       "passed": values[key[:-4]] <= maximum} for key, maximum in thresholds.items()]
            engines[engine] = dict(implementation_key=job["policy"]["implementation_key"], policy_hash=job["policy_hash"],
                input_hash=job["input_hash"], policy=job["policy"], metrics=values, checks=checks,
                duration_seconds=round(time.monotonic() - started, 4),
                positions=[p.model_dump(mode="json", exclude_none=True) for p in result.positions],
                stages=[s.model_dump(mode="json") for s in result.stages], quality=quality)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    sources = ["matching_quality_executor.py", "matching_quality.py",
               "matching_portfolio.py", "matching_allocation.py", "account_mapping.py", "core/matching_common.py"]
    source_hashes = {name: sha256((ROOT / "python-backend/app" / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in sources}
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    return dict(schema_version=1, dataset_id=dataset["dataset_id"], dataset_hash=digest(dataset),
                vector_space=dataset["vector_space"], mode="synthetic_replay", real_model_calls=0,
                production_writes=0, git_commit=revision.stdout.strip() if revision.returncode == 0 else "unknown",
                git_dirty=bool(dirty.stdout), source_hashes=source_hashes,
                models={"chat": dataset["replay"]["chat_model"], "embedding": dataset["vector_space"]},
                taxonomy_version=1, mapping_version=1,
                accounts=[{k: a[k] for k in ("account_id", "account_name", "um_no")} for a in dataset["accounts"]],
                topics=[dict(topic_id=t["topic_id"], **{k: t["source_payload"][k] for k in ("title", "outline", "content_type")}) for t in dataset["topics"]],
                engines=engines)
