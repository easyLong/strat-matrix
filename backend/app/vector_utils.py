"""Validate embeddings without assuming a particular model or dimension."""

import math


def normalized_vector(values: object, model: object, subject: str) -> list[float]:
    if not isinstance(model, str) or not model.strip() or len(model.strip()) > 100:
        raise ValueError(f"{subject}向量模型标识必须为 1–100 字")
    if not isinstance(values, list) or not 1 <= len(values) <= 4096:
        raise ValueError(f"{subject}向量维度必须在 1–4096 之间")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise ValueError(f"{subject}向量必须全部是数值")
    vector = [float(value) for value in values]
    if any(not math.isfinite(value) or abs(value) > 1e6 for value in vector):
        raise ValueError(f"{subject}向量存在无效数值")
    length = math.sqrt(math.fsum(value * value for value in vector))
    if length == 0 or not math.isfinite(length):
        raise ValueError(f"{subject}向量不能是零向量")
    return [value / length for value in vector]
