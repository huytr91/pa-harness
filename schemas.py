"""
schemas.py — Cấu trúc dữ liệu chuẩn cho pa-harness.

Thiết kế bám sát 2 tài liệu:
- 01-project-overview.md, mục 3.2 (Schema quan sát / Observation) — trường
  bắt buộc cho MỌI observation ghi vào DuckDB, để dữ liệu benchmark V0 không
  bị vứt bỏ khi chuyển lên central DB sau này (nguyên tắc thiết kế quan trọng
  nhất của tài liệu gốc).
- 04-fit-scoring-model.md, mục 3 (Nhóm A/B/C/E) — các biến cụ thể cần đo được
  ngay ở V0, không cần dữ liệu cộng đồng.

HardwareFingerprint và ProblemFingerprint ở đây CỐ TÌNH trùng cấu trúc với
pa-interview-agent/schemas.py — đây là "hợp đồng" giữa 2 repo cho tới khi
pa-schema được tách riêng (xem 03-gtm-opensource-strategy.md, mục 3: pa-schema
là repo quan trọng nhất về mặt chiến lược). Khi tách, cả 2 nơi sẽ import từ
pa-schema thay vì tự định nghĩa.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Hardware Fingerprint — auto-detect only (xem hardware_detect.py).
# Khớp 1:1 với pa-interview-agent/schemas.py::HardwareFingerprint.
# ---------------------------------------------------------------------------

class GPUClass(str, Enum):
    none = "none"
    entry = "entry"
    mid = "mid"
    high = "high"
    datacenter = "datacenter"


class RamBucket(str, Enum):
    lt_8gb = "<8GB"
    r_8_16 = "8-16GB"
    r_16_32 = "16-32GB"
    r_32_64 = "32-64GB"
    gt_64 = ">64GB"


class HardwareFingerprint(BaseModel):
    cpu_class: str
    cores: int
    ram_bucket: RamBucket
    ram_total_mb: int
    gpu_class: GPUClass
    gpu_model: Optional[str] = None
    vram_mb: Optional[int] = None
    os: str
    detected_at: str
    detection_method: Literal["auto"] = "auto"


# ---------------------------------------------------------------------------
# Problem Fingerprint — đọc từ problem.yaml do pa-interview-agent sinh ra.
# Chỉ cần các field pa-harness thực sự dùng (feasibility filter + để ghi
# problem_fingerprint_id vào observation) — không copy toàn bộ field phụ.
# ---------------------------------------------------------------------------

class ProblemFingerprint(BaseModel):
    domain: str
    language: Optional[str] = None
    document_type: Optional[str] = None
    quality_target: float = Field(ge=0.0, le=1.0, default=0.9)
    throughput_target: str = "unspecified"
    budget_constraint_usd_per_unit: Optional[float] = None
    notes: Optional[str] = None

    @property
    def fingerprint_id(self) -> str:
        """Id ổn định cho một Problem Fingerprint — dùng làm khóa trong
        observation (xem 01-project-overview.md mục 3.2: problem_fingerprint_id).
        Băm theo nội dung để cùng 1 problem luôn ra cùng 1 id, khác problem thì
        khác id — không cần DB trung tâm cấp id ở V0."""
        payload = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False)
        return "pf-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Pipeline config — đọc từ pipeline.yaml theo format ở
# 03-gtm-opensource-strategy.md mục 4.2.
# ---------------------------------------------------------------------------

class PipelineStepConfig(BaseModel):
    component: str
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    pipeline_id: str
    pipeline_version: str = "0.1"
    steps: list[PipelineStepConfig]

    @property
    def num_steps(self) -> int:
        return len(self.steps)

    @property
    def checksum(self) -> str:
        """Checksum của config pipeline — chống sửa tay số liệu sau khi đo
        (bắt buộc theo 03-gtm-opensource-strategy.md mục 4.3)."""
        payload = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Kết quả 1 bước adapter — dùng nội bộ trong runner.py, không ghi thẳng vào DB.
# ---------------------------------------------------------------------------

from pa_adapters.types import ComponentResult


# ---------------------------------------------------------------------------
# Một lần chạy (1 pipeline × 1 sample document × 1 run index) — raw record,
# trước khi được BenchmarkEngine gộp lại thành Observation.
# ---------------------------------------------------------------------------

class RunRecord(BaseModel):
    run_id: str
    experiment_id: str
    pipeline_id: str
    pipeline_version: str
    sample_file: str
    run_index: int
    latency_ms: float
    peak_ram_mb: float
    cold_start_ms: Optional[float] = None
    success: bool
    error: Optional[str] = None
    output_text: str = ""
    self_confidence: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Observation — bản ghi cuối cùng vào DuckDB. Trường bắt buộc lấy nguyên văn
# từ 01-project-overview.md mục 3.2 (Định danh/Hardware/Benchmark/Kết quả/Meta),
# cộng thêm:
#  - source_type/evidence_weight (mục 4.2, Evidence Hierarchy)
#  - harness_version/run_count/variance/checksum (GTM mục 4.3, chống gian lận)
#  - latency_p50/p95, peak_vram_mb, success_rate, cold_start_time_ms (Fit
#    Scoring mục 3, Nhóm A — base schema chỉ có "latency" số ít, ở đây tách
#    p50/p95 vì đó là input thật của công thức FitScore, mục 6)
#  - num_steps/num_external_deps/has_paid_api_dependency (Fit Scoring mục 3,
#    Nhóm E — "gần như miễn phí để có", nên đưa vào ngay từ V0)
# ---------------------------------------------------------------------------

class ObservationRecord(BaseModel):
    # -- Định danh --
    experiment_id: str
    pipeline_id: str
    pipeline_version: str
    problem_fingerprint_id: str

    # -- Hardware fingerprint --
    cpu_class: str
    cores: int
    ram_bucket: str
    gpu_class: str

    # -- Benchmark --
    benchmark_id: str

    # -- Kết quả (Nhóm A performance, base schema) --
    latency: float           # = latency_p50, giữ tên "latency" khớp schema gốc
    latency_p50: float
    latency_p95: float
    peak_ram: float          # = peak_ram_mb, giữ tên "peak_ram" khớp schema gốc
    peak_ram_mb: float
    peak_vram_mb: Optional[float] = None
    cold_start_time_ms: Optional[float] = None
    success: bool             # true nếu success_rate == 1.0 trên toàn bộ run
    success_rate: float

    # -- Quality (Nhóm C — xem quality_signals.py + quality_bt.py) --
    quality: float                      # quality_estimate tương đối (Bradley-Terry), 0-1
    quality_confidence: float           # confidence_i cho FitScore — thấp vì đây là Level 5
                                         # nhưng dựa trên tín hiệu gián tiếp, không phải ground truth
    quality_signal_breakdown: str = ""  # JSON string: agreement/validator/self_confidence chi tiết

    # -- Complexity / Fragility (Nhóm E) --
    num_steps: int
    num_external_deps: int
    has_paid_api_dependency: bool

    # -- Evidence Hierarchy (mục 4.2) --
    source_type: Literal["internal", "external"] = "internal"
    evidence_weight: float = 1.0   # Level 5 = benchmark nội bộ, mặc định cao nhất

    # -- Meta / chống gian lận (GTM mục 4.3) --
    harness_version: str
    run_count: int
    variance: float
    checksum: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def _consistency(self) -> "ObservationRecord":
        if self.run_count < 3:
            # GTM mục 5.1: "Chạy N lần bắt buộc (tối thiểu 3-5 lần)".
            # Không raise cứng ở đây (cho phép chạy nhanh lúc dev/test), nhưng
            # đánh dấu confidence thấp hẳn để tầng Fit Score không bị đánh lừa.
            self.quality_confidence = min(self.quality_confidence, 0.3)
        return self
