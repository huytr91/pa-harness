"""
quality_bt.py — Bradley-Terry (MM algorithm) để suy ra quality_estimate
TƯƠNG ĐỐI giữa các pipeline candidate từ một tập kết quả so sánh cặp
("A thắng B" / "A thua B" / hòa), KHÔNG cần ground truth tuyệt đối.

Đây đúng là khung toán học được chỉ định ở 04-fit-scoring-model.md mục 3
(Nhóm C, "Tổng hợp thành điểm quality tương đối — dùng mô hình Bradley-
Terry/Elo cục bộ") và mục 7 ("cùng một họ toán học" với belief update
P(A beats B) ở Evidence Hierarchy — thiết kế nhất quán để lên V2 gộp thẳng
dữ liệu mà không cần đổi định dạng).

Cài đặt: MM algorithm (Hunter, 2004) — hội tụ nhanh, không cần dependency
ngoài stdlib, phù hợp quy mô nhỏ (vài candidate mỗi lần benchmark).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PairwiseOutcome:
    """weight_a_wins / weight_b_wins có thể là số thực (0-1), không bắt buộc
    nhị phân — cho phép biểu diễn 'thắng mềm' (vd. agreement cao -> gần hòa
    -> mỗi bên 0.5) thay vì ép cứng 1/0."""

    pipeline_a: str
    pipeline_b: str
    weight_a_wins: float
    weight_b_wins: float


def bradley_terry_strengths(
    pipeline_ids: list[str],
    outcomes: list[PairwiseOutcome],
    iterations: int = 200,
    tol: float = 1e-9,
) -> dict[str, float]:
    """Trả về strength đã chuẩn hóa (tổng = 1) cho mỗi pipeline_id.
    Nếu không có outcome nào (0 so sánh), trả về đồng đều — đúng tinh thần
    'không có bằng chứng thì không giả vờ có' thay vì báo lỗi."""
    n = len(pipeline_ids)
    if n == 0:
        return {}
    if not outcomes:
        return {pid: 1.0 / n for pid in pipeline_ids}

    idx = {pid: i for i, pid in enumerate(pipeline_ids)}
    wins = [[0.0] * n for _ in range(n)]  # wins[i][j] = số lần (mềm) i thắng j
    for o in outcomes:
        if o.pipeline_a not in idx or o.pipeline_b not in idx:
            continue
        i, j = idx[o.pipeline_a], idx[o.pipeline_b]
        wins[i][j] += o.weight_a_wins
        wins[j][i] += o.weight_b_wins

    total_wins = [sum(wins[i]) for i in range(n)]
    n_games = [[wins[i][j] + wins[j][i] for j in range(n)] for i in range(n)]

    strengths = [1.0] * n
    for _ in range(iterations):
        new_strengths = [0.0] * n
        for i in range(n):
            denom = 0.0
            for j in range(n):
                if i == j or n_games[i][j] == 0:
                    continue
                denom += n_games[i][j] / (strengths[i] + strengths[j])
            if denom <= 0 or total_wins[i] == 0:
                # Không có dữ liệu liên quan đến i -> giữ nguyên (không suy diễn ảo).
                new_strengths[i] = strengths[i]
            else:
                new_strengths[i] = total_wins[i] / denom

        # Chuẩn hóa để tránh strengths trôi dạt tới 0/vô cực qua nhiều vòng lặp.
        mean_s = sum(new_strengths) / n
        if mean_s > 0:
            new_strengths = [s / mean_s for s in new_strengths]

        delta = max(abs(a - b) for a, b in zip(strengths, new_strengths))
        strengths = new_strengths
        if delta < tol:
            break

    total = sum(strengths)
    if total <= 0:
        return {pid: 1.0 / n for pid in pipeline_ids}
    return {pid: strengths[i] / total for pid, i in idx.items()}
