"""
quality_signals.py — Tầng 1 (tín hiệu tự động, KHÔNG cần ground truth) của
04-fit-scoring-model.md mục 3, Nhóm C:

  1. Cross-pipeline agreement — so sánh output giữa các candidate pipeline
     trên CÙNG một tài liệu.
  2. Structural/self-consistency validator — rule-based, rẻ, không cần LLM.
  3. Model self-confidence — passthrough từ ComponentResult.self_confidence
     (đã có sẵn miễn phí từ adapter, xem adapters/builtin.py::OcrEngineAdapter).

  KHÔNG cài LLM/VLM-as-judge ở bản này (tài liệu liệt kê là kỹ thuật thứ 2
  trong Tầng 1) — nó cần gọi model qua ModelRouter giống pa-interview-agent,
  để dành cho lúc benchmark_engine tích hợp trực tiếp với providers.py. Hàm
  `llm_judge_score()` dưới đây là điểm mở rộng (trả None nếu chưa cấu hình),
  aggregate_quality_signals() đã có sẵn chỗ cắm nó vào mà không cần đổi
  interface khi thêm sau.

Toàn bộ tín hiệu được quy về PairwiseOutcome (A thắng/thua/hòa B) — đúng định
hướng "quality_estimate dưới dạng kết quả so sánh cặp" ở mục 7 tài liệu gốc,
rồi đưa qua quality_bt.bradley_terry_strengths() để ra quality_estimate cuối.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from typing import Callable, Optional

from quality_bt import PairwiseOutcome, bradley_terry_strengths

# ---------------------------------------------------------------------------
# 1. Cross-pipeline agreement
# ---------------------------------------------------------------------------


def pairwise_agreement(text_a: str, text_b: str) -> float:
    """0-1, càng cao càng giống nhau. difflib.SequenceMatcher đủ tốt cho mục
    đích 'đo độ đồng thuận', không cần thư viện edit-distance ngoài."""
    if not text_a and not text_b:
        return 1.0
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


# ---------------------------------------------------------------------------
# 2. Structural / self-consistency validators — rule-based, pluggable.
# Mỗi validator: (text: str, context: dict) -> float điểm 0-1 (1 = hợp lệ).
# ---------------------------------------------------------------------------

StructuralValidator = Callable[[str, dict], float]

_VALIDATORS: dict[str, StructuralValidator] = {}


def register_validator(name: str, fn: StructuralValidator) -> None:
    _VALIDATORS[name] = fn


def _v_non_empty(text: str, context: dict) -> float:
    return 1.0 if text and text.strip() else 0.0


def _v_no_corruption_markers(text: str, context: dict) -> float:
    """Ví dụ generic: tỉ lệ ký tự lỗi encoding/placeholder ('\\ufffd' hoặc '#'
    do adapters/builtin.py dùng để mô phỏng noise OCR). Domain thật nên thay
    bằng validator riêng (vd. tổng dòng hóa đơn khớp tổng cộng, số cột bảng
    nhất quán qua các trang — xem 04-fit-scoring-model.md mục 3 Nhóm C)."""
    if not text:
        return 0.0
    bad = text.count("�") + text.count("#")
    ratio_bad = bad / max(1, len(text))
    return max(0.0, 1.0 - ratio_bad * 5)  # phạt nặng: 20% ký tự lỗi -> score 0


def _v_table_line_consistency(text: str, context: dict) -> float:
    """Chỉ áp dụng khi layout-detector đánh dấu table_likelihood cao — kiểm
    tra độ nhất quán độ dài dòng (proxy rẻ cho 'bảng có đều cột không'). Nếu
    không phải tài liệu dạng bảng, trả 1.0 (không phạt oan)."""
    if context.get("table_likelihood", 0.0) < 0.2:
        return 1.0
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return 1.0
    lengths = [len(l) for l in lines]
    mean_len = sum(lengths) / len(lengths)
    if mean_len == 0:
        return 1.0
    variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / mean_len  # hệ số biến thiên — thấp = nhất quán
    return max(0.0, 1.0 - min(cv, 1.0))


def _parse_money_token(s: str) -> float | None:
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return None
    return float(digits)


def _v_invoice_line_totals(text: str, context: dict) -> float:
    """Domain-specific: tổng dòng khớp 'Tong cong' — ví dụ đúng như
    04-fit-scoring-model.md mục 3 Nhóm C. Không phải hóa đơn → 1.0 (không phạt).
    Sample `samples/invoice_*.txt` dùng đúng format này."""
    if not re.search(r"tong\s*cong", text, re.IGNORECASE):
        return 1.0
    line_sum = 0.0
    n_lines = 0
    for line in text.splitlines():
        parts = [p.strip() for p in re.split(r"\t+", line)]
        if len(parts) >= 5 and parts[0].isdigit():
            val = _parse_money_token(parts[-1])
            if val is not None:
                line_sum += val
                n_lines += 1
    m = re.search(r"tong\s*cong\s*[:\s]*([\d.,]+)", text, re.IGNORECASE)
    if not m or n_lines == 0:
        return 0.5
    total = _parse_money_token(m.group(1))
    if total is None or total <= 0:
        return 0.5
    rel = abs(line_sum - total) / total
    return max(0.0, 1.0 - min(rel, 1.0))


register_validator("non_empty", _v_non_empty)
register_validator("no_corruption_markers", _v_no_corruption_markers)
register_validator("table_line_consistency", _v_table_line_consistency)
register_validator("invoice_line_totals", _v_invoice_line_totals)


def run_structural_validators(
    text: str, context: dict, validator_names: Optional[list[str]] = None
) -> dict[str, float]:
    names = validator_names or list(_VALIDATORS)
    return {name: _VALIDATORS[name](text, context) for name in names if name in _VALIDATORS}


# ---------------------------------------------------------------------------
# 3. LLM/VLM-as-judge — điểm mở rộng, CHƯA implement (xem docstring module).
# ---------------------------------------------------------------------------


def llm_judge_score(source_image_path: str, output_text: str) -> Optional[float]:
    """Trả None = chưa cấu hình judge model. aggregate_quality_signals() bỏ
    qua tín hiệu này khi None, không coi là lỗi. Cắm model thật ở đây bằng
    cách tái dùng pa-interview-agent/providers.py::ModelProvider khi cần."""
    return None


# ---------------------------------------------------------------------------
# Tổng hợp: nhiều candidate pipeline chạy trên CÙNG 1 sample -> pairwise
# outcomes -> Bradley-Terry -> quality_estimate mỗi pipeline.
# ---------------------------------------------------------------------------


@dataclass
class QualitySignalReport:
    quality_estimate: dict[str, float]          # pipeline_id -> 0-1, tổng = 1 (BT strength)
    structural_scores: dict[str, dict[str, float]]  # pipeline_id -> {validator_name: score}
    agreement_matrix: dict[tuple[str, str], float]
    self_confidence: dict[str, Optional[float]]  # pipeline_id -> self_confidence bước cuối

    def to_json(self) -> str:
        return json.dumps(
            {
                "quality_estimate": self.quality_estimate,
                "structural_scores": self.structural_scores,
                "agreement_matrix": {f"{a}::{b}": v for (a, b), v in self.agreement_matrix.items()},
                "self_confidence": self.self_confidence,
            },
            ensure_ascii=False,
        )


def aggregate_quality_signals(
    outputs: dict[str, str],
    contexts: dict[str, dict],
    self_confidence: dict[str, Optional[float]],
    validator_names: Optional[list[str]] = None,
    structural_weight: float = 0.7,
    agreement_weight: float = 0.3,
) -> QualitySignalReport:
    """outputs/contexts/self_confidence đều khóa theo pipeline_id, tất cả chạy
    trên CÙNG một sample document (BenchmarkEngine đảm bảo điều này)."""
    pipeline_ids = list(outputs)
    structural_scores = {
        pid: run_structural_validators(outputs[pid], contexts.get(pid, {}), validator_names)
        for pid in pipeline_ids
    }
    structural_avg = {
        pid: (sum(scores.values()) / len(scores) if scores else 0.5)
        for pid, scores in structural_scores.items()
    }

    agreement_matrix: dict[tuple[str, str], float] = {}
    outcomes: list[PairwiseOutcome] = []
    for i, pid_a in enumerate(pipeline_ids):
        for pid_b in pipeline_ids[i + 1 :]:
            agreement = pairwise_agreement(outputs[pid_a], outputs[pid_b])
            agreement_matrix[(pid_a, pid_b)] = agreement

            struct_a, struct_b = structural_avg[pid_a], structural_avg[pid_b]
            struct_gap = struct_a - struct_b  # >0 nghĩa A có validator tốt hơn B

            # Trộn 2 tín hiệu: validator quyết ai thắng khi 2 bên khác biệt rõ
            # (structural_weight); agreement kéo kết quả về "hòa" khi 2 output
            # gần giống nhau (agreement_weight) — agreement cao tự nó không nói
            # ai đúng hơn, chỉ củng cố việc "không nên phạt nhau nặng".
            base_a_wins = 0.5 + max(-0.5, min(0.5, struct_gap)) * structural_weight
            pulled_to_tie = base_a_wins * (1 - agreement_weight * agreement) + 0.5 * (
                agreement_weight * agreement
            )
            weight_a_wins = max(0.0, min(1.0, pulled_to_tie))
            outcomes.append(
                PairwiseOutcome(
                    pipeline_a=pid_a,
                    pipeline_b=pid_b,
                    weight_a_wins=weight_a_wins,
                    weight_b_wins=1.0 - weight_a_wins,
                )
            )

    quality_estimate = bradley_terry_strengths(pipeline_ids, outcomes)
    return QualitySignalReport(
        quality_estimate=quality_estimate,
        structural_scores=structural_scores,
        agreement_matrix=agreement_matrix,
        self_confidence=self_confidence,
    )
