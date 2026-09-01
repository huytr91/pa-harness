"""
feasibility.py — Tầng 1 (Hard Constraint Filter) của Fit Scoring Model.

Xem 04-fit-scoring-model.md mục 2, "Tầng 1 — Hard Constraint Filter (không
tính điểm, chỉ loại)": bước rẻ và quan trọng nhất — tránh lãng phí việc
benchmark (chạy thật, tốn thời gian/điện) cho pipeline không khả thi trên máy
user. Đặt ở pa-harness (không đợi Architecture Agent) vì đây chính là nơi
biết rõ nhất "chạy được hay không" — chạy thử trước khi đo thật.

Đây KHÔNG phải Fit Score — không tính điểm, chỉ trả về feasible / lý do loại.
Tính điểm (Tầng 2) là việc của Architecture Agent, không phải pa-harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from schemas import HardwareFingerprint, PipelineConfig, ProblemFingerprint

# Adapter khai báo yêu cầu qua ADAPTER_REQUIREMENTS trong adapters/registry.py
# (requires_gpu, requires_min_ram_mb, supported_languages, os_allowlist...).
# Import muộn để tránh vòng lặp import với adapters/registry.py.


@dataclass
class FeasibilityResult:
    feasible: bool
    reasons_excluded: list[str] = field(default_factory=list)


def check_feasibility(
    pipeline: PipelineConfig,
    problem: ProblemFingerprint,
    hardware: HardwareFingerprint,
) -> FeasibilityResult:
    from pa_adapters.registry import get_adapter_spec  # late import, tránh vòng lặp

    reasons: list[str] = []
    estimated_ram_mb = 0

    for step in pipeline.steps:
        spec = get_adapter_spec(step.component)
        if spec is None:
            reasons.append(f"component '{step.component}' chưa có adapter đăng ký")
            continue

        # RAM — 04-fit-scoring-model.md mục 2, bảng constraint đầu tiên.
        estimated_ram_mb += spec.estimated_ram_mb

        # VRAM/GPU — loại trừ khi pipeline cần GPU nhưng máy không có, TRỪ KHI
        # component có fallback CPU (spec.gpu_optional=True).
        if spec.requires_gpu and hardware.gpu_class.value == "none" and not spec.gpu_optional:
            reasons.append(
                f"component '{step.component}' cần GPU nhưng hardware.gpu_class=none "
                f"(không có fallback CPU)"
            )

        # OS — vd. component chỉ chạy Linux nhưng máy user Windows.
        if spec.os_allowlist and hardware.os.split()[0] not in spec.os_allowlist:
            reasons.append(
                f"component '{step.component}' chỉ hỗ trợ OS {spec.os_allowlist}, "
                f"máy hiện tại: {hardware.os}"
            )

        # Ngôn ngữ/domain — component không hỗ trợ ngôn ngữ problem yêu cầu.
        if (
            problem.language
            and spec.supported_languages is not None
            and problem.language not in spec.supported_languages
        ):
            reasons.append(
                f"component '{step.component}' không hỗ trợ ngôn ngữ "
                f"'{problem.language}' (hỗ trợ: {spec.supported_languages})"
            )

        # Budget cứng — nếu problem đặt max_cost và step có API trả phí không rõ giá trần.
        if (
            spec.requires_paid_api
            and problem.budget_constraint_usd_per_unit is not None
            and spec.cost_per_unit_usd is not None
            and spec.cost_per_unit_usd > problem.budget_constraint_usd_per_unit
        ):
            reasons.append(
                f"component '{step.component}' cost_per_unit_usd="
                f"{spec.cost_per_unit_usd} vượt budget_constraint_usd_per_unit="
                f"{problem.budget_constraint_usd_per_unit}"
            )

    if hardware.ram_total_mb and estimated_ram_mb > hardware.ram_total_mb * 0.9:
        # Chừa 10% RAM cho OS — không loại sát nút mà không có biên an toàn.
        reasons.append(
            f"ước lượng peak_ram={estimated_ram_mb}MB vượt quá 90% RAM khả dụng "
            f"({hardware.ram_total_mb}MB)"
        )

    return FeasibilityResult(feasible=not reasons, reasons_excluded=reasons)
