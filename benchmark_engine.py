"""
benchmark_engine.py — Điều phối toàn bộ luồng benchmark: đọc problem +
N candidate pipelines, lọc khả thi (feasibility.py), chạy từng pipeline N≥3
lần trên tập sample documents (runner.py), tính quality bằng so sánh chéo
giữa các pipeline trên cùng tài liệu (quality_signals.py), gộp lại thành
Observation và ghi vào DuckDB (storage.py).

Đây là "Benchmark Engine" được nhắc tới ở README.md gốc của dự án (mục "Bước
tiếp theo đề xuất" #2): "đọc problem.yaml, chạy 1 pipeline cụ thể, đo
latency/RAM/quality, ghi vào DuckDB theo schema". Mở rộng nhận NHIỀU pipeline
cùng lúc (không chỉ 1) vì quality tầng 1 (cross-pipeline agreement) CẦN ít
nhất 2 candidate chạy trên cùng tài liệu để so sánh — chạy từng pipeline đơn
lẻ vẫn hoạt động (xem ghi chú ở _aggregate_quality), chỉ là quality_confidence
sẽ thấp hơn vì thiếu đối chứng.
"""

from __future__ import annotations

import json
import os
import statistics
import uuid
from dataclasses import dataclass, field

from _version import BENCHMARK_PROTOCOL_ID, HARNESS_VERSION
from pa_adapters.registry import get_adapter_spec
from feasibility import check_feasibility
from hardware_detect import detect_hardware
from quality_signals import aggregate_quality_signals
from runner import PipelineRunner
from schemas import HardwareFingerprint, ObservationRecord, PipelineConfig, ProblemFingerprint, RunRecord
from storage import connect, insert_observation, insert_runs

SUPPORTED_SAMPLE_EXT = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".docx", ".txt",
    ".wav", ".mp3", ".flac",  # audio-transcription domain
}
# .txt thêm ngoài tập mà pa-interview-agent/hardware_detect.py dùng để scan —
# pa-harness đọc nội dung file thật (không chỉ đếm), .txt hữu ích để test
# harness/adapter mock mà không cần file PDF/ảnh thật.


@dataclass
class PipelineOutcome:
    pipeline: PipelineConfig
    feasible: bool
    reasons_excluded: list[str] = field(default_factory=list)
    observation: ObservationRecord | None = None
    runs: list[RunRecord] = field(default_factory=list)


@dataclass
class ExperimentReport:
    experiment_id: str
    hardware: HardwareFingerprint
    outcomes: list[PipelineOutcome]


def _list_samples(samples_dir: str) -> list[str]:
    if not os.path.isdir(samples_dir):
        raise FileNotFoundError(f"samples_dir không tồn tại: {samples_dir}")
    files = [
        os.path.join(samples_dir, f)
        for f in sorted(os.listdir(samples_dir))
        if os.path.splitext(f)[1].lower() in SUPPORTED_SAMPLE_EXT
    ]
    if not files:
        raise ValueError(
            f"Không tìm thấy sample document nào trong {samples_dir} "
            f"(hỗ trợ: {sorted(SUPPORTED_SAMPLE_EXT)})"
        )
    return files


def _percentiles(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]
    q = statistics.quantiles(values, n=100, method="inclusive")
    return q[49], q[94]  # p50, p95 (index 0 = percentile 1)


def _complexity_stats(pipeline: PipelineConfig) -> tuple[int, int, bool]:
    """Nhóm E (04-fit-scoring-model.md mục 3) — 'gần như miễn phí để có', tính
    thẳng từ AdapterSpec của từng component, không cần chạy benchmark."""
    num_external_deps = 0
    has_paid_api = False
    for step in pipeline.steps:
        spec = get_adapter_spec(step.component)
        if spec is None:
            continue
        if spec.requires_network or spec.requires_paid_api:
            num_external_deps += 1
        if spec.requires_paid_api:
            has_paid_api = True
    return pipeline.num_steps, num_external_deps, has_paid_api


def run_experiment(
    pipelines: list[PipelineConfig],
    problem: ProblemFingerprint,
    samples_dir: str,
    db_path: str = "benchmarks.duckdb",
    runs_per_sample: int = 5,
) -> ExperimentReport:
    if runs_per_sample < 3:
        raise ValueError(
            "runs_per_sample phải >= 3 — GTM mục 5.1 yêu cầu chạy N lần tối thiểu "
            "3-5 lần để phát hiện variance bất thường, không nhận benchmark 1 lần."
        )

    hardware = detect_hardware()
    sample_files = _list_samples(samples_dir)
    experiment_id = f"exp-{uuid.uuid4().hex[:12]}"

    outcomes: list[PipelineOutcome] = []
    feasible_pipelines: list[PipelineConfig] = []

    for pipeline in pipelines:
        feas = check_feasibility(pipeline, problem, hardware)
        outcomes.append(
            PipelineOutcome(pipeline=pipeline, feasible=feas.feasible, reasons_excluded=feas.reasons_excluded)
        )
        if feas.feasible:
            feasible_pipelines.append(pipeline)

    # -- Chạy TUẦN TỰ từng pipeline khả thi (không song song — xem runner.py
    #    docstring: đo RAM bằng RSS cả tiến trình, chạy song song sẽ lẫn số) --
    all_runs: dict[str, list[RunRecord]] = {}
    representative_output: dict[str, dict[str, str]] = {}
    representative_context: dict[str, dict[str, dict]] = {}
    representative_confidence: dict[str, dict[str, float | None]] = {}

    for pipeline in feasible_pipelines:
        runner = PipelineRunner(pipeline, problem)
        runs: list[RunRecord] = []
        out_by_sample: dict[str, str] = {}
        ctx_by_sample: dict[str, dict] = {}
        conf_by_sample: dict[str, float | None] = {}

        for sample_file in sample_files:
            for run_index in range(runs_per_sample):
                run = runner.run_once(sample_file, run_index, experiment_id)
                runs.append(run)
                if run_index == 0 and run.success:
                    out_by_sample[sample_file] = run.output_text
                    ctx_by_sample[sample_file] = dict(runner.last_context)
                    conf_by_sample[sample_file] = run.self_confidence

        all_runs[pipeline.pipeline_id] = runs
        representative_output[pipeline.pipeline_id] = out_by_sample
        representative_context[pipeline.pipeline_id] = ctx_by_sample
        representative_confidence[pipeline.pipeline_id] = conf_by_sample

    # -- Quality: so sánh chéo TRÊN CÙNG 1 sample giữa các pipeline khả thi đã
    #    chạy thành công trên sample đó, gộp qua nhiều sample bằng trung bình. --
    per_pipeline_quality_samples: dict[str, list[float]] = {pid: [] for pid in all_runs}
    per_pipeline_breakdowns: dict[str, list[dict]] = {pid: [] for pid in all_runs}

    for sample_file in sample_files:
        outputs = {
            pid: representative_output[pid][sample_file]
            for pid in all_runs
            if sample_file in representative_output.get(pid, {})
        }
        if not outputs:
            continue
        contexts = {pid: representative_context[pid].get(sample_file, {}) for pid in outputs}
        confidences = {pid: representative_confidence[pid].get(sample_file) for pid in outputs}
        report = aggregate_quality_signals(outputs, contexts, confidences)
        for pid, q in report.quality_estimate.items():
            per_pipeline_quality_samples[pid].append(q)
            per_pipeline_breakdowns[pid].append(
                {
                    "sample": os.path.basename(sample_file),
                    "structural_scores": report.structural_scores.get(pid, {}),
                    "self_confidence": report.self_confidence.get(pid),
                    "num_candidates_compared": len(outputs),
                }
            )

    # -- Gộp runs -> Observation cho mỗi pipeline khả thi --
    con = connect(db_path)
    outcome_by_id = {o.pipeline.pipeline_id: o for o in outcomes}

    for pipeline in feasible_pipelines:
        runs = all_runs[pipeline.pipeline_id]
        successful = [r for r in runs if r.success]
        latencies = [r.latency_ms for r in successful]
        rams = [r.peak_ram_mb for r in successful]
        success_rate = len(successful) / len(runs) if runs else 0.0
        p50, p95 = _percentiles(latencies)
        variance = statistics.variance(latencies) if len(latencies) > 1 else 0.0
        cold_start = next((r.cold_start_ms for r in runs if r.cold_start_ms is not None), None)

        quality_samples = per_pipeline_quality_samples.get(pipeline.pipeline_id, [])
        quality = sum(quality_samples) / len(quality_samples) if quality_samples else 0.0

        confidences = [c for c in representative_confidence[pipeline.pipeline_id].values() if c is not None]
        self_conf_avg = sum(confidences) / len(confidences) if confidences else 0.5
        avg_candidates_compared = (
            sum(b["num_candidates_compared"] for b in per_pipeline_breakdowns[pipeline.pipeline_id])
            / len(per_pipeline_breakdowns[pipeline.pipeline_id])
            if per_pipeline_breakdowns[pipeline.pipeline_id]
            else 1
        )
        # Chưa có đối chứng (chỉ 1 pipeline được benchmark) -> hạ confidence rõ
        # rệt, đúng tinh thần "không giả vờ có bằng chứng khi không có" của
        # Evidence Hierarchy.
        comparison_penalty = 1.0 if avg_candidates_compared > 1 else 0.5
        quality_confidence = round(self_conf_avg * comparison_penalty, 4)

        num_steps, num_external_deps, has_paid_api = _complexity_stats(pipeline)

        obs = ObservationRecord(
            experiment_id=experiment_id,
            pipeline_id=pipeline.pipeline_id,
            pipeline_version=pipeline.pipeline_version,
            problem_fingerprint_id=problem.fingerprint_id,
            cpu_class=hardware.cpu_class,
            cores=hardware.cores,
            ram_bucket=hardware.ram_bucket.value,
            gpu_class=hardware.gpu_class.value,
            benchmark_id=BENCHMARK_PROTOCOL_ID,
            latency=p50,
            latency_p50=p50,
            latency_p95=p95,
            peak_ram=max(rams) if rams else 0.0,
            peak_ram_mb=max(rams) if rams else 0.0,
            peak_vram_mb=None,  # chưa đo VRAM ở V0 — adapter mock không dùng GPU thật
            cold_start_time_ms=cold_start,
            success=success_rate == 1.0,
            success_rate=success_rate,
            quality=quality,
            quality_confidence=quality_confidence,
            quality_signal_breakdown=json.dumps(
                per_pipeline_breakdowns[pipeline.pipeline_id], ensure_ascii=False
            ),
            num_steps=num_steps,
            num_external_deps=num_external_deps,
            has_paid_api_dependency=has_paid_api,
            harness_version=HARNESS_VERSION,
            run_count=len(runs),
            variance=variance,
            checksum=pipeline.checksum,
        )
        insert_observation(con, obs)
        insert_runs(con, runs)
        outcome_by_id[pipeline.pipeline_id].observation = obs
        outcome_by_id[pipeline.pipeline_id].runs = runs

    con.close()
    return ExperimentReport(experiment_id=experiment_id, hardware=hardware, outcomes=outcomes)
