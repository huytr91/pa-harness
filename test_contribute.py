"""Tests for contribution export — privacy allowlist."""

from __future__ import annotations

import json

import pytest

from contribute import (
    build_contribution_bundle,
    public_problem_fingerprint,
)
from pipeline_loader import load_problem
from schemas import ObservationRecord


def _sample_obs(**overrides) -> ObservationRecord:
    base = {
        "experiment_id": "exp-1",
        "pipeline_id": "vn-ocr-baseline-v1",
        "pipeline_version": "0.1",
        "problem_fingerprint_id": "pf-local",
        "cpu_class": "mid",
        "cores": 8,
        "ram_bucket": "16-32GB",
        "gpu_class": "none",
        "benchmark_id": "bench-1",
        "latency": 100.0,
        "latency_p50": 100.0,
        "latency_p95": 120.0,
        "peak_ram": 512.0,
        "peak_ram_mb": 512.0,
        "success": True,
        "success_rate": 1.0,
        "quality": 0.8,
        "quality_confidence": 0.7,
        "num_steps": 2,
        "num_external_deps": 0,
        "has_paid_api_dependency": False,
        "harness_version": "0.1.0-test",
        "run_count": 5,
        "variance": 1.2,
        "checksum": "abc123",
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return ObservationRecord(**base)


def test_public_problem_excludes_notes():
    problem = load_problem("problem.example.yaml")
    pub = public_problem_fingerprint(problem)
    assert "notes" not in pub
    assert pub["domain"] == "document-ocr"
    assert pub["fingerprint_id_public"].startswith("pf-")


def test_contribution_requires_terms():
    with pytest.raises(PermissionError, match="i-agree-to-terms"):
        build_contribution_bundle(
            db_path="benchmarks.duckdb",
            experiment_id="nonexistent",
            problem_path="problem.example.yaml",
            pipeline_paths=["pipelines/vn-ocr-baseline-v1.yaml"],
            terms_accepted=False,
        )


def test_data_use_policy_forbids_ai_agents():
    from contribute import _DATA_USE_POLICY

    forbidden = set(_DATA_USE_POLICY["forbidden_consumers"])
    assert "interview_agent" in forbidden
    assert "architecture_agent" in forbidden
    assert "web_chat_context" in forbidden


def test_public_observation_rejects_low_run_count():
    from contribute import public_observation_row

    obs = _sample_obs(run_count=2)
    with pytest.raises(ValueError, match="run_count"):
        public_observation_row(obs, "pf-public")
