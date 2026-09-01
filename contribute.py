"""
contribute.py — Export opt-in benchmark bundles for community evidence.

STRICT PRIVACY: only pipeline benchmark metrics and structural fingerprints.
Never includes notes, sample content, run outputs, paths, or session/chat data.
Forbidden for interview_agent / architecture_agent / LLM context (see pa-schema
docs/contribution-privacy.md).
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _version import HARNESS_VERSION
from pipeline_loader import load_pipeline, load_problem
from schemas import ObservationRecord, PipelineConfig, ProblemFingerprint
from storage import connect

_DATA_USE_POLICY: dict[str, Any] = {
    "purpose": "pipeline_benchmark_evidence_only",
    "allowed_consumers": [
        "benchmark_leaderboard",
        "evidence_aggregation",
        "outlier_detection",
        "community_stats",
    ],
    "forbidden_consumers": [
        "interview_agent",
        "architecture_agent",
        "web_chat_context",
        "llm_training",
        "llm_fine_tuning",
        "marketing",
        "user_profiling",
    ],
    "notes": (
        "This bundle is pipeline benchmark evidence only. "
        "AI interview/architecture agents must not ingest this data."
    ),
}
def public_problem_fingerprint(problem: ProblemFingerprint) -> dict[str, Any]:
    """Structural workload fields only — excludes notes."""
    payload = {
        "domain": problem.domain,
        "language": problem.language,
        "document_type": problem.document_type,
        "quality_target": problem.quality_target,
        "throughput_target": problem.throughput_target,
        "budget_usd_per_unit": problem.budget_constraint_usd_per_unit,
    }
    fid = "pf-" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return {**payload, "fingerprint_id_public": fid}


def public_pipeline_summary(pipeline: PipelineConfig) -> dict[str, Any]:
    """Topology identity only — component names + checksum, no config values."""
    return {
        "pipeline_id": pipeline.pipeline_id,
        "pipeline_version": pipeline.pipeline_version,
        "checksum": pipeline.checksum,
        "component_names": [s.component for s in pipeline.steps],
    }


def _coarse_os_family() -> str:
    sys_name = platform.system().lower()
    if "windows" in sys_name:
        return "windows"
    if "linux" in sys_name:
        return "linux"
    if "darwin" in sys_name or "mac" in sys_name:
        return "macos"
    return "other"


def public_hardware_from_observation(obs: ObservationRecord) -> dict[str, Any]:
    return {
        "cpu_class": obs.cpu_class,
        "cores": obs.cores,
        "ram_bucket": obs.ram_bucket,
        "gpu_class": obs.gpu_class,
        "gpu_model": None,
        "vram_mb": obs.peak_vram_mb,
        "os_family": _coarse_os_family(),
        "detection_method": "auto",
    }


def public_observation_row(obs: ObservationRecord, fingerprint_id_public: str) -> dict[str, Any]:
    if obs.run_count < 3:
        raise ValueError(
            f"Observation pipeline={obs.pipeline_id} run_count={obs.run_count} < 3 — "
            "not eligible for community contribution."
        )
    return {
        "pipeline_id": obs.pipeline_id,
        "pipeline_version": obs.pipeline_version,
        "problem_fingerprint_id_public": fingerprint_id_public,
        "checksum": obs.checksum,
        "latency_p50": obs.latency_p50,
        "latency_p95": obs.latency_p95,
        "peak_ram_mb": obs.peak_ram_mb,
        "peak_vram_mb": obs.peak_vram_mb,
        "cold_start_time_ms": obs.cold_start_time_ms,
        "success_rate": obs.success_rate,
        "quality": obs.quality,
        "quality_confidence": obs.quality_confidence,
        "num_steps": obs.num_steps,
        "num_external_deps": obs.num_external_deps,
        "has_paid_api_dependency": obs.has_paid_api_dependency,
        "run_count": obs.run_count,
        "variance": obs.variance,
        "harness_version": obs.harness_version,
        "source_type": "internal",
        "timestamp": obs.timestamp,
    }


def fetch_observations_for_experiment(
    con, experiment_id: str
) -> list[ObservationRecord]:
    rows = con.execute(
        "SELECT * FROM observations WHERE experiment_id = ? ORDER BY pipeline_id",
        [experiment_id],
    ).fetchdf()
    if rows.empty:
        return []
    records: list[ObservationRecord] = []
    for _, row in rows.iterrows():
        d = row.to_dict()
        for k, v in d.items():
            if hasattr(v, "item"):
                d[k] = v.item() if v is not None else None
        records.append(ObservationRecord(**d))
    return records


def build_contribution_bundle(
    *,
    db_path: str,
    experiment_id: str,
    problem_path: str,
    pipeline_paths: list[str],
    terms_accepted: bool,
) -> dict[str, Any]:
    if not terms_accepted:
        raise PermissionError(
            "Contribution export requires --i-agree-to-terms (ODC-BY-1.0, pipeline metrics only)."
        )

    problem = load_problem(problem_path)
    pipelines = [load_pipeline(p) for p in pipeline_paths]
    problem_public = public_problem_fingerprint(problem)
    fp_public = problem_public["fingerprint_id_public"]

    con = connect(db_path)
    try:
        observations = fetch_observations_for_experiment(con, experiment_id)
    finally:
        con.close()

    if not observations:
        raise ValueError(f"No observations found for experiment_id={experiment_id}")

    public_rows = [public_observation_row(o, fp_public) for o in observations]
    hw = public_hardware_from_observation(observations[0])

    return {
        "format": "pa_observation_contribution",
        "version": "1.0",
        "data_use_policy": _DATA_USE_POLICY,
        "harness_version": HARNESS_VERSION,
        "experiment_id": experiment_id,
        "hardware_fingerprint": hw,
        "problem_fingerprint_public": problem_public,
        "pipelines_public": [public_pipeline_summary(p) for p in pipelines],
        "observations": public_rows,
        "terms_accepted": {
            "license": "ODC-BY-1.0",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def export_contribution_bundle(
    *,
    db_path: str,
    experiment_id: str,
    problem_path: str,
    pipeline_paths: list[str],
    out_path: str,
    terms_accepted: bool,
) -> Path:
    bundle = build_contribution_bundle(
        db_path=db_path,
        experiment_id=experiment_id,
        problem_path=problem_path,
        pipeline_paths=pipeline_paths,
        terms_accepted=terms_accepted,
    )
    # Guard: no user content fields in exportable sections
    for section in ("problem_fingerprint_public", "observations", "pipelines_public"):
        section_blob = json.dumps(bundle.get(section, {}), ensure_ascii=False)
        for key in ("output_text", "sample_file", "session_id", "markdown", "notes"):
            if f'"{key}"' in section_blob:
                raise RuntimeError(f"Contribution bundle leaked forbidden field: {key}")

    path = Path(out_path)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
