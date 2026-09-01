"""
pipeline_loader.py — Đọc pipeline.yaml và problem.yaml, validate qua Pydantic
trước khi đưa cho runner/feasibility. Không bao giờ để dữ liệu sai schema
lọt qua âm thầm — cùng nguyên tắc đã dùng ở pa-interview-agent/agent.py.
"""

from __future__ import annotations

import yaml

from schemas import PipelineConfig, ProblemFingerprint


def load_pipeline(path: str) -> PipelineConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return PipelineConfig(**raw)


def load_problem(path: str) -> ProblemFingerprint:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    # cli.py Interview Agent ghi ra dạng {"problem_fingerprint": {...}} —
    # chấp nhận cả 2 dạng (có/không bọc key ngoài) để problem.yaml gốc từ
    # pa-interview-agent dùng thẳng được, không cần chỉnh tay.
    payload = raw.get("problem_fingerprint", raw)
    return ProblemFingerprint(**payload)
