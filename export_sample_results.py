# -*- coding: utf-8 -*-
"""Export public benchmark summary from DuckDB (no PDF content / paths)."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent


def _safe_mean(vals: list[float]) -> float | None:
    return float(sum(vals) / len(vals)) if vals else None


def main() -> None:
    db = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "benchmarks-sample-full.duckdb")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "results" / "sample-ocr-vi")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db), read_only=True)
    obs = con.execute(
        """
        SELECT pipeline_id, pipeline_version, problem_fingerprint_id,
               cpu_class, cores, ram_bucket, gpu_class,
               latency_p50, latency_p95, peak_ram_mb, success_rate, quality,
               quality_confidence, run_count, variance, checksum,
               num_steps, has_paid_api_dependency, source_type,
               harness_version, timestamp
        FROM observations
        ORDER BY pipeline_id, run_count DESC
        """
    ).fetchdf()
    runs = con.execute(
        """
        SELECT pipeline_id, sample_file, run_index, latency_ms, peak_ram_mb,
               success, error, self_confidence,
               CASE WHEN output_text IS NULL THEN 0 ELSE length(output_text) END AS text_chars
        FROM runs
        ORDER BY pipeline_id, sample_file, run_index
        """
    ).fetchdf()
    con.close()

    runs["sample_file"] = runs["sample_file"].map(lambda p: Path(str(p)).name)

    by_sample_rows = []
    for (pid, sample), g in runs.groupby(["pipeline_id", "sample_file"]):
        chars = [float(x) for x in g["text_chars"].tolist()]
        lats = [float(x) for x in g["latency_ms"].tolist()]
        rams = [float(x) for x in g["peak_ram_mb"].tolist()]
        mean_chars = _safe_mean(chars) or 0.0
        # Heuristic aligned with pdf-native-parser: very low chars → likely scan/image PDF
        likely_scan = mean_chars < 400
        by_sample_rows.append(
            {
                "pipeline_id": pid,
                "sample_file": sample,
                "n": int(len(g)),
                "latency_mean_ms": round(_safe_mean(lats) or 0.0, 1),
                "latency_min_ms": round(min(lats), 1) if lats else None,
                "latency_max_ms": round(max(lats), 1) if lats else None,
                "ram_mean_mb": round(_safe_mean(rams) or 0.0, 1),
                "text_chars_mean": round(mean_chars, 0),
                "likely_scan_heuristic": likely_scan,
                "success_rate": round(float(g["success"].mean()), 3),
            }
        )

    by_pipeline = []
    for pid, g in runs.groupby("pipeline_id"):
        by_pipeline.append(
            {
                "pipeline_id": pid,
                "n": int(len(g)),
                "latency_mean_ms": round(float(g["latency_ms"].mean()), 1),
                "latency_p50_ms": round(float(g["latency_ms"].quantile(0.5)), 1),
                "latency_p95_ms": round(float(g["latency_ms"].quantile(0.95)), 1),
                "ram_mean_mb": round(float(g["peak_ram_mb"].mean()), 1),
                "text_chars_mean": round(float(g["text_chars"].mean()), 0),
                "likely_scan_share": round(
                    float(
                        sum(
                            1
                            for s in by_sample_rows
                            if s["pipeline_id"] == pid and s["likely_scan_heuristic"]
                        )
                        / max(
                            1,
                            len([s for s in by_sample_rows if s["pipeline_id"] == pid]),
                        )
                    ),
                    3,
                ),
                "success_rate": round(float(g["success"].mean()), 3),
            }
        )

    obs_records = []
    for row in obs.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean[k] = None
            else:
                clean[k] = v
        obs_records.append(clean)

    hw = {}
    if obs_records:
        r0 = obs_records[0]
        hw = {
            "cpu_class": r0.get("cpu_class"),
            "cores": r0.get("cores"),
            "ram_bucket": r0.get("ram_bucket"),
            "gpu_class": r0.get("gpu_class"),
        }

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "evidence_level": "L2_operational_measurement",
        "disclaimer": (
            "Latency/RAM/success measured on contributor machine via PDF text-layer extract (pypdf). "
            "Not full scan-OCR (Tesseract/Paddle). Quality is relative cross-pipeline agreement, "
            "not ground-truth CER/accuracy. No PDF bytes or document text included. "
            "likely_scan_heuristic = mean extracted text_chars < 400."
        ),
        "workload": {
            "domain": "document-ocr",
            "language": "vi",
            "document_type": "mixed-scan-table",
            "sample_count": 16,
            "runs_per_sample": 3,
            "pipelines": ["vn-pdf-extract-lite-v1", "vn-pdf-extract-deep-v1"],
            "tags": ["multi-page", "table", "text", "financial", "regulation", "vi"],
            "ground_truth": False,
        },
        "hardware": hw,
        "observations": obs_records,
        "runs_summary": {
            "n_runs": int(len(runs)),
            "by_pipeline": by_pipeline,
            "by_sample": by_sample_rows,
        },
    }

    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# SAMPLE OCR beachhead — operational results",
        "",
        f"Exported: `{payload['exported_at']}`",
        "",
        "## Evidence level",
        "",
        payload["disclaimer"],
        "",
        f"**Hardware:** `{hw.get('cpu_class')}` · {hw.get('cores')} cores · RAM `{hw.get('ram_bucket')}` · GPU `{hw.get('gpu_class')}`",
        "",
        f"**Workload:** {payload['workload']['sample_count']} PDFs × {payload['workload']['runs_per_sample']} runs × 2 pipelines = **{payload['runs_summary']['n_runs']}** measured runs.",
        "",
        "## Observations (aggregated)",
        "",
        "| pipeline | p50 ms | p95 ms | RAM MB | success | quality* | runs |",
        "|----------|--------|--------|--------|---------|----------|------|",
    ]
    for row in payload["observations"]:
        lines.append(
            f"| `{row['pipeline_id']}` | {row['latency_p50']:.1f} | {row['latency_p95']:.1f} | "
            f"{row['peak_ram_mb']:.1f} | {row['success_rate']:.0%} | {row['quality']:.3f} | "
            f"{row['run_count']} |"
        )
    lines.extend(
        [
            "",
            "\\*quality = relative cross-pipeline agreement on extracted text, **not** CER/accuracy.",
            "",
            "## Per-pipeline extract detail",
            "",
            "| pipeline | n | mean lat ms | p50 | p95 | RAM MB | mean text_chars | likely_scan share |",
            "|----------|---|-------------|-----|-----|--------|-----------------|-------------------|",
        ]
    )
    for row in by_pipeline:
        lines.append(
            f"| `{row['pipeline_id']}` | {row['n']} | {row['latency_mean_ms']} | "
            f"{row['latency_p50_ms']} | {row['latency_p95_ms']} | {row['ram_mean_mb']} | "
            f"{int(row['text_chars_mean'])} | {row['likely_scan_share']:.0%} |"
        )
    lines.extend(
        [
            "",
            "## Per-sample means",
            "",
            "| pipeline | sample | mean lat ms | RAM MB | text_chars | likely_scan | success |",
            "|----------|--------|-------------|--------|------------|-------------|---------|",
        ]
    )
    for row in sorted(by_sample_rows, key=lambda r: (r["sample_file"], r["pipeline_id"])):
        scan = "yes" if row["likely_scan_heuristic"] else "no"
        lines.append(
            f"| `{row['pipeline_id']}` | `{row['sample_file']}` | "
            f"{row['latency_mean_ms']} | {row['ram_mean_mb']} | "
            f"{int(row['text_chars_mean'])} | {scan} | {row['success_rate']:.0%} |"
        )
    lines.extend(
        [
            "",
            "## Reproduce",
            "",
            "```bash",
            "cd pa-harness",
            "python cli.py run \\",
            "  --problem problem.ocr-sample.yaml \\",
            "  --pipelines pipelines/vn-pdf-extract-lite-v1.yaml pipelines/vn-pdf-extract-deep-v1.yaml \\",
            "  --samples-dir ../SAMPLE \\",
            "  --db benchmarks-sample-full.duckdb \\",
            "  --runs 3",
            "python export_sample_results.py benchmarks-sample-full.duckdb results/sample-ocr-vi",
            "```",
            "",
            "PDFs stay local (gitignored). Only metrics are published.",
            "",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {out_dir / 'README.md'}")


if __name__ == "__main__":
    main()
