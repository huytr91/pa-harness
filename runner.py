"""
runner.py — Chạy MỘT pipeline nhiều lần (N≥3, theo GTM mục 5.1) trên tập
sample documents, đo latency + peak RAM trực tiếp trên máy user. Đây là
Nhóm A (Performance) ở 04-fit-scoring-model.md mục 3 — "luôn đo được cục bộ,
không phụ thuộc cộng đồng".

Đo peak RAM bằng cách lấy mẫu RSS của TOÀN BỘ tiến trình harness theo chu kỳ
ngắn trong lúc chạy (không chỉ đo trước/sau) — nếu chỉ đo trước/sau thì bỏ lỡ
đỉnh RAM giữa chừng (vd. lúc load model). Giới hạn đã biết: đo RSS cả tiến
trình, không tách riêng theo từng pipeline nếu chạy song song — vì vậy
BenchmarkEngine chạy các pipeline TUẦN TỰ, không song song, để số đo RAM
không bị lẫn giữa các candidate.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from schemas import ComponentResult, PipelineConfig, ProblemFingerprint, RunRecord
from pa_adapters.registry import instantiate

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


class _RamSampler:
    """Lấy mẫu RSS tiến trình hiện tại trên một thread nền, giữ lại giá trị
    lớn nhất quan sát được trong lúc chạy 1 run."""

    def __init__(self, interval_s: float = 0.02):
        self.interval_s = interval_s
        self._peak_mb = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc = psutil.Process() if psutil is not None else None

    def start(self) -> None:
        if self._proc is None:
            return
        self._peak_mb = self._proc.memory_info().rss / (1024 * 1024)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                rss_mb = self._proc.memory_info().rss / (1024 * 1024)
                self._peak_mb = max(self._peak_mb, rss_mb)
            except Exception:
                pass
            self._stop.wait(self.interval_s)

    def stop(self) -> float:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return self._peak_mb


class PipelineRunner:
    """1 instance = 1 pipeline đã 'load' (adapter được khởi tạo 1 lần, dùng lại
    cho mọi sample/run — giống hành vi thật: model chỉ load 1 lần, chạy nhiều
    request). Vì vậy warmup() phải gọi đúng 1 lần trước run_once() đầu tiên."""

    def __init__(self, pipeline: PipelineConfig, problem: ProblemFingerprint):
        self.pipeline = pipeline
        self.problem = problem
        self._adapters = [instantiate(step.component) for step in pipeline.steps]
        self._warmed_up = False
        self.last_context: dict = {}

    def warmup(self) -> float:
        total_ms = 0.0
        for adapter in self._adapters:
            total_ms += adapter.warmup()
        self._warmed_up = True
        return total_ms

    def run_once(self, sample_file: str, run_index: int, experiment_id: str) -> RunRecord:
        cold_start_ms = None
        if not self._warmed_up:
            cold_start_ms = self.warmup()

        context: dict = {"problem": self.problem.model_dump()}
        text = sample_file  # bước đầu tiên (thường pdf-native-parser) nhận path file
        self.last_context = context  # BenchmarkEngine đọc lại ngay sau run_once() để lấy
                                      # context (vd. table_likelihood) phục vụ quality_signals

        sampler = _RamSampler()
        sampler.start()
        t0 = time.perf_counter()
        success = True
        error: Optional[str] = None
        last_result: Optional[ComponentResult] = None

        try:
            for step, adapter in zip(self.pipeline.steps, self._adapters):
                result = adapter.process(text, step.config, context)
                last_result = result
                if not result.success:
                    success = False
                    error = result.error or f"component '{step.component}' thất bại không rõ lý do"
                    break
                text = result.output_text
        except Exception as e:  # adapter lỗi runtime ngoài dự kiến -> ghi nhận thất bại, không crash cả session
            success = False
            error = f"exception ở '{self.pipeline.pipeline_id}': {e}"

        latency_ms = (time.perf_counter() - t0) * 1000
        peak_ram_mb = sampler.stop()

        return RunRecord(
            run_id=f"run-{uuid.uuid4().hex[:12]}",
            experiment_id=experiment_id,
            pipeline_id=self.pipeline.pipeline_id,
            pipeline_version=self.pipeline.pipeline_version,
            sample_file=sample_file,
            run_index=run_index,
            latency_ms=latency_ms,
            peak_ram_mb=peak_ram_mb,
            cold_start_ms=cold_start_ms,
            success=success,
            error=error,
            output_text=text if success else "",
            self_confidence=last_result.self_confidence if last_result else None,
        )
