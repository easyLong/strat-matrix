"""Versioned policy and executor contracts; no implicit algorithm formula."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .account_profile import canonical_json


AlgorithmCode = Literal["ALG-01", "ALG-02", "ALG-03", "ALG-04", "ALG-05", "ALG-06", "ALG-07", "ALG-08", "ALG-09"]
ALGORITHM_CODES = set(AlgorithmCode.__args__)
SUPPORTED_INPUTS = {"accounts", "topics", "config", "positions"}


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


class MatchingPolicyDocument(StrictModel):
    schema_version: Literal[1] = 1
    implementation_key: str = Field(min_length=1, max_length=100)
    vector_space: PolicyVectorSpace | None = None
    required_inputs: list[str] = Field(default_factory=list, max_length=20)
    decisions: dict[AlgorithmCode, RuleDecision] = Field(default_factory=dict)

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
        if set(self.required_inputs) - SUPPORTED_INPUTS:
            problems.append("策略要求的额外输入尚未冻结，不能批准执行")
        if not {"accounts", "topics", "config", "positions"} <= set(self.required_inputs):
            problems.append("普通匹配必须声明账号、选题、配置和日期输入")
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
