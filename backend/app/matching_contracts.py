"""Versioned policy and executor contracts; no implicit algorithm formula."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .account_profile import canonical_json


AlgorithmCode = Literal["ALG-01", "ALG-02", "ALG-03", "ALG-04", "ALG-05", "ALG-06", "ALG-07", "ALG-08", "ALG-09"]
ALGORITHM_CODES = set(AlgorithmCode.__args__)
SUPPORTED_INPUTS = {"accounts", "topics", "config", "positions"}
SUPPLEMENTAL_INPUTS = {"fallback_topics", "history", "official_usage"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleDecision(StrictModel):
    definition: str = Field(min_length=1, max_length=4000)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    acceptance_examples: list[str] = Field(default_factory=list, max_length=20)


class PolicyVectorSpace(StrictModel):
    vector_model: str = Field(min_length=1, max_length=100)
    dimension: int = Field(strict=True, ge=1, le=4096)
    semantic_space_id: str = Field(min_length=1, max_length=100)


class MatchingInputOptions(StrictModel):
    history_window_days: int | None = Field(default=None, strict=True, ge=1, le=3650)
    history_completeness: Literal["allow_unknown", "require_complete"] | None = None
    history_unknown_references: Literal["allow_unknown", "block"] | None = None
    official_usage_unknown: Literal["allow_unknown", "block"] | None = None
    fallback_unknown_heat: Literal["allow_unknown", "block"] | None = None


class MatchingPortfolioOptions(StrictModel):
    relevance_weight: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    coverage_weight: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    balance_weight: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    redundancy_weight: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    mmr_relevance_weight: float = Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    shortlist_per_slot: int = Field(strict=True, ge=1, le=1000)
    max_improvement_passes: int = Field(strict=True, ge=1, le=1000)

    @model_validator(mode="after")
    def objective_weights_sum_to_one(self):
        weights = (self.relevance_weight, self.coverage_weight,
                   self.balance_weight, self.redundancy_weight)
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("portfolio objective weights must sum to 1")
        return self


class MatchingPolicyDocument(StrictModel):
    schema_version: Literal[1, 2] = 1
    implementation_key: str = Field(min_length=1, max_length=100)
    vector_space: PolicyVectorSpace | None = None
    required_inputs: list[str] = Field(default_factory=list, max_length=20)
    decisions: dict[AlgorithmCode, RuleDecision] = Field(default_factory=dict)
    input_options: MatchingInputOptions | None = None
    portfolio: MatchingPortfolioOptions | None = None

    @model_validator(mode="after")
    def finite_document(self):
        if len(canonical_json(self.model_dump()).encode("utf-8")) > 256_000:
            raise ValueError("算法策略文档超过256KB")
        if not self.implementation_key.strip():
            raise ValueError("算法实现标识不能为空")
        return self

    def approval_errors(self) -> list[str]:
        problems = [f"缺少{code}规则" for code in sorted(ALGORITHM_CODES - self.decisions.keys())]
        for code, rule in sorted(self.decisions.items()):
            if not rule.definition.strip() or not rule.acceptance_examples \
                    or any(not example.strip() or len(example) > 4000 for example in rule.acceptance_examples):
                problems.append(f"{code}须提供明确规则与验收样例")
        if self.vector_space is None or not self.vector_space.vector_model.strip() \
                or not self.vector_space.semantic_space_id.strip():
            problems.append("须声明双侧向量模型、维度和语义空间")
        if not self.required_inputs or len(set(self.required_inputs)) != len(self.required_inputs):
            problems.append("须声明不重复的输入依赖")
        supported = SUPPORTED_INPUTS | (SUPPLEMENTAL_INPUTS if self.schema_version == 2 else set())
        if set(self.required_inputs) - supported:
            problems.append("策略要求的额外输入尚未冻结，不能批准执行")
        if not {"accounts", "topics", "config", "positions"} <= set(self.required_inputs):
            problems.append("普通匹配必须声明账号、选题、配置和日期输入")
        if self.schema_version == 1 and self.input_options is not None:
            problems.append("第一版策略不支持补充输入选项，请创建第二版策略")
        if self.schema_version == 2:
            options = self.input_options or MatchingInputOptions()
            if "history" in self.required_inputs and (options.history_window_days is None
                    or options.history_completeness is None or options.history_unknown_references is None):
                problems.append("历史输入须明确时间窗口、完整性与未知选题引用的处理")
            if "official_usage" in self.required_inputs and options.official_usage_unknown is None:
                problems.append("正式使用次数输入须明确未知计数处理")
            if "fallback_topics" in self.required_inputs and options.fallback_unknown_heat is None:
                problems.append("兜底池须明确未知热度处理")
            if "history" not in self.required_inputs and any(value is not None for value in (
                    options.history_window_days, options.history_completeness, options.history_unknown_references)):
                problems.append("历史输入选项与输入依赖声明不一致")
            if "official_usage" not in self.required_inputs and options.official_usage_unknown is not None:
                problems.append("正式计数输入选项与输入依赖声明不一致")
            if "fallback_topics" not in self.required_inputs and options.fallback_unknown_heat is not None:
                problems.append("兜底输入选项与输入依赖声明不一致")
        return problems


class PolicyCreate(StrictModel):
    policy_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    expected_latest_version: int = Field(strict=True, ge=0)
    document: MatchingPolicyDocument


class PolicyConfirmation(StrictModel):
    expected_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_by: str = Field(min_length=1, max_length=50)


class MatchingTaskCreate(StrictModel):
    preparation_id: int = Field(strict=True, ge=1)
    expected_preparation_version: int = Field(strict=True, ge=1)
    policy_id: int = Field(strict=True, ge=1)


class ClaimTask(StrictModel):
    after_id: int = Field(default=0, strict=True, ge=0)
    lease_seconds: int = Field(default=300, strict=True, ge=30, le=3600)


class TaskVersion(StrictModel):
    expected_version: int = Field(strict=True, ge=1)


class LeaseIdentity(StrictModel):
    lease_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class LeaseHeartbeat(LeaseIdentity):
    lease_seconds: int = Field(default=300, strict=True, ge=30, le=3600)


class StageAudit(StrictModel):
    stage: Literal["hard_gate", "recall", "fit", "global_allocation", "composition"]
    summary: dict[str, JsonValue]


class ProposedPosition(StrictModel):
    account_id: str = Field(min_length=1, max_length=64)
    publish_date: date
    outcome: Literal["matched", "fallback", "failed"]
    topic_id: str | None = Field(default=None, min_length=1, max_length=64)
    content_role: Literal["流量", "转化"] | None = None
    fit_score: float | None = Field(default=None, strict=True, ge=0, le=100, allow_inf_nan=False)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def consistent_position(self):
        if self.outcome == "failed":
            if self.topic_id is not None or self.content_role is not None or self.fit_score is not None or not self.reason.strip():
                raise ValueError("失败位置须说明原因，不能提供选题、经营作用或评分")
        else:
            if not self.topic_id or self.content_role is None:
                raise ValueError("匹配或兜底位置须提供选题和经营作用")
            if self.outcome == "matched" and self.fit_score is None:
                raise ValueError("匹配位置须提供Fit评分")
            if self.outcome == "fallback" and (self.fit_score is not None or not self.reason.strip()):
                raise ValueError("兜底位置须说明原因，不能伪造Fit评分")
        return self


class MatchingEvaluation(LeaseIdentity):
    implementation_key: str = Field(min_length=1, max_length=100)
    stages: list[StageAudit] = Field(min_length=5, max_length=5)
    positions: list[ProposedPosition] = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def complete_trace(self):
        if [stage.stage for stage in self.stages] != ["hard_gate", "recall", "fit", "global_allocation", "composition"]:
            raise ValueError("执行记录须按顺序包含完整匹配主链")
        if len(canonical_json(self.model_dump(mode="json")).encode("utf-8")) > 2_000_000:
            raise ValueError("执行结果超过2MB")
        return self


class MatchingFailure(LeaseIdentity):
    error_code: Literal["engine_unavailable", "execution_failed", "invalid_response"]
