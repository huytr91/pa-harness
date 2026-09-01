"""
storage.py — Ghi Observation vào DuckDB, đúng lựa chọn công nghệ và schema ở
01-project-overview.md mục 3.1-3.3: "DuckDB (local, embedded) vì workload
chính là analytical/quant, không phải transactional".

Nguyên tắc thiết kế quan trọng (mục 3.1): schema DuckDB V0 phải giống hệt
schema telemetry tương lai — nên bảng `observations` bám sát 1:1
schemas.ObservationRecord, không "tiện tay" đổi tên cột.

Có thêm bảng `runs` (không nằm trong tài liệu gốc) để giữ lại raw per-run
data (mỗi lần chạy 1 pipeline trên 1 sample) — cần thiết để tính lại
latency_p50/p95/variance sau này nếu muốn (vd. đổi công thức percentile),
thay vì chỉ giữ số đã tổng hợp sẵn. `observations` vẫn là bảng chính mọi
truy vấn ranking/Fit Score dùng.
"""

from __future__ import annotations

from typing import Optional

import duckdb

from schemas import ObservationRecord, RunRecord

_OBSERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS observations (
    experiment_id            VARCHAR,
    pipeline_id               VARCHAR,
    pipeline_version           VARCHAR,
    problem_fingerprint_id      VARCHAR,

    cpu_class                  VARCHAR,
    cores                       INTEGER,
    ram_bucket                  VARCHAR,
    gpu_class                   VARCHAR,

    benchmark_id                 VARCHAR,

    latency                       DOUBLE,
    latency_p50                   DOUBLE,
    latency_p95                   DOUBLE,
    peak_ram                       DOUBLE,
    peak_ram_mb                    DOUBLE,
    peak_vram_mb                   DOUBLE,
    cold_start_time_ms              DOUBLE,
    success                          BOOLEAN,
    success_rate                     DOUBLE,

    quality                          DOUBLE,
    quality_confidence                DOUBLE,
    quality_signal_breakdown           VARCHAR,

    num_steps                          INTEGER,
    num_external_deps                   INTEGER,
    has_paid_api_dependency               BOOLEAN,

    source_type                           VARCHAR,
    evidence_weight                        DOUBLE,

    harness_version                         VARCHAR,
    run_count                                INTEGER,
    variance                                  DOUBLE,
    checksum                                   VARCHAR,
    timestamp                                   TIMESTAMP
);
"""

_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id            VARCHAR,
    experiment_id      VARCHAR,
    pipeline_id          VARCHAR,
    pipeline_version      VARCHAR,
    sample_file            VARCHAR,
    run_index                INTEGER,
    latency_ms                 DOUBLE,
    peak_ram_mb                  DOUBLE,
    cold_start_ms                  DOUBLE,
    success                          BOOLEAN,
    error                             VARCHAR,
    output_text                        VARCHAR,
    self_confidence                    DOUBLE,
    timestamp                            TIMESTAMP
);
"""


def connect(db_path: str = "benchmarks.duckdb") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute(_OBSERVATIONS_DDL)
    con.execute(_RUNS_DDL)
    return con


def insert_observation(con: duckdb.DuckDBPyConnection, obs: ObservationRecord) -> None:
    d = obs.model_dump()
    columns = list(d.keys())
    placeholders = ", ".join("?" for _ in columns)
    con.execute(
        f"INSERT INTO observations ({', '.join(columns)}) VALUES ({placeholders})",
        [d[c] for c in columns],
    )


def insert_runs(con: duckdb.DuckDBPyConnection, runs: list[RunRecord]) -> None:
    if not runs:
        return
    columns = list(runs[0].model_dump().keys())
    placeholders = ", ".join("?" for _ in columns)
    con.executemany(
        f"INSERT INTO runs ({', '.join(columns)}) VALUES ({placeholders})",
        [[r.model_dump()[c] for c in columns] for r in runs],
    )


# ---------------------------------------------------------------------------
# Query helper mẫu — minh họa 2 loại truy vấn OLAP nêu ở 01-project-overview.md
# mục 3.3. Không phải API đầy đủ, chỉ để cli.py `pa-harness query` dùng thử và
# làm ví dụ cho Architecture Agent sau này viết truy vấn phức tạp hơn.
# ---------------------------------------------------------------------------


def rank_by_latency(
    con: duckdb.DuckDBPyConnection,
    problem_fingerprint_id: Optional[str] = None,
    min_quality: Optional[float] = None,
    limit: int = 20,
):
    """Tương ứng câu hỏi ví dụ: 'Pipeline nào nhanh nhất trên CPU 8-core,
    RAM ≤16GB, OCR tiếng Việt, table-heavy, quality ≥96%?' — filter theo
    problem_fingerprint_id (đã gộp domain/language/document_type/quality_target
    vào 1 id) + min_quality, rồi sort theo latency_p50."""
    clauses, params = [], []
    if problem_fingerprint_id:
        clauses.append("problem_fingerprint_id = ?")
        params.append(problem_fingerprint_id)
    if min_quality is not None:
        clauses.append("quality >= ?")
        params.append(min_quality)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT pipeline_id, pipeline_version, latency_p50, latency_p95,
               peak_ram_mb, quality, quality_confidence, success_rate
        FROM observations
        {where}
        ORDER BY latency_p50 ASC
        LIMIT ?
    """
    params.append(limit)
    return con.execute(query, params).fetchall()


def latest_observations_per_pipeline(con: duckdb.DuckDBPyConnection):
    """Observation mới nhất cho mỗi (pipeline_id, problem_fingerprint_id,
    cpu_class/ram_bucket/gpu_class) — dùng khi muốn so sánh candidate hiện tại,
    bỏ qua các lần đo cũ đã lỗi thời (vd. harness_version thay đổi)."""
    query = """
        SELECT * FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY pipeline_id, problem_fingerprint_id, cpu_class, ram_bucket, gpu_class
                ORDER BY timestamp DESC
            ) AS rn
            FROM observations
        )
        WHERE rn = 1
    """
    return con.execute(query).fetchall()
