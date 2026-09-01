"""
cli.py — Entrypoint dòng lệnh cho pa-harness.

    $ python cli.py run --problem problem.yaml --pipelines a.yaml b.yaml \\
          --samples-dir ./samples --db benchmarks.duckdb --runs 5

    $ python cli.py query --db benchmarks.duckdb \\
          --problem-fingerprint-id pf-xxxxxxxx --min-quality 0.6

`problem.yaml` dùng thẳng file do pa-interview-agent/cli.py sinh ra — không
cần chỉnh tay (xem pipeline_loader.load_problem).
"""

from __future__ import annotations

import argparse
import sys

import pa_adapters  # noqa: F401 — register builtin adapters

from benchmark_engine import run_experiment
from contribute import export_contribution_bundle
from pipeline_loader import load_pipeline, load_problem
from storage import connect, rank_by_latency


def _cmd_run(args: argparse.Namespace) -> None:
    problem = load_problem(args.problem)
    pipelines = [load_pipeline(p) for p in args.pipelines]

    print(f"=== pa-harness run — {len(pipelines)} pipeline(s), {args.runs} lần/sample ===")
    print(f"Problem: domain={problem.domain} quality_target={problem.quality_target} "
          f"language={problem.language} fingerprint_id={problem.fingerprint_id}\n")

    report = run_experiment(
        pipelines=pipelines,
        problem=problem,
        samples_dir=args.samples_dir,
        db_path=args.db,
        runs_per_sample=args.runs,
    )

    print(f"Experiment: {report.experiment_id}")
    print(f"Hardware: {report.hardware.cpu_class} ({report.hardware.cores} cores), "
          f"{report.hardware.ram_bucket.value}, GPU={report.hardware.gpu_class.value}\n")

    for outcome in report.outcomes:
        pid = outcome.pipeline.pipeline_id
        if not outcome.feasible:
            print(f"❌ {pid} — LOẠI ở Tầng 1 (hard constraint filter):")
            for reason in outcome.reasons_excluded:
                print(f"     - {reason}")
            continue

        obs = outcome.observation
        print(f"✅ {pid}")
        print(f"     latency_p50={obs.latency_p50:.1f}ms  latency_p95={obs.latency_p95:.1f}ms  "
              f"peak_ram={obs.peak_ram_mb:.1f}MB")
        print(f"     success_rate={obs.success_rate:.0%}  quality={obs.quality:.3f} "
              f"(confidence={obs.quality_confidence:.2f})")
        print(f"     num_steps={obs.num_steps}  num_external_deps={obs.num_external_deps}  "
              f"has_paid_api_dependency={obs.has_paid_api_dependency}")
        print(f"     run_count={obs.run_count}  variance={obs.variance:.2f}  "
              f"checksum={obs.checksum}\n")

    print(f"→ Đã ghi vào {args.db} (bảng `observations` + `runs`).")


def _cmd_query(args: argparse.Namespace) -> None:
    con = connect(args.db)
    rows = rank_by_latency(
        con,
        problem_fingerprint_id=args.problem_fingerprint_id,
        min_quality=args.min_quality,
        limit=args.limit,
    )
    con.close()

    if not rows:
        print("Không có observation nào khớp filter.")
        return

    headers = ["pipeline_id", "version", "p50(ms)", "p95(ms)", "ram(MB)", "quality", "conf", "success_rate"]
    print(" | ".join(headers))
    for r in rows:
        print(" | ".join(str(v) for v in r))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pa-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Chạy benchmark 1+ pipeline candidate trên 1 problem")
    run_p.add_argument("--problem", required=True, help="Đường dẫn problem.yaml")
    run_p.add_argument("--pipelines", required=True, nargs="+", help="1+ đường dẫn pipeline.yaml")
    run_p.add_argument("--samples-dir", required=True, help="Thư mục chứa sample documents")
    run_p.add_argument("--db", default="benchmarks.duckdb", help="Đường dẫn file DuckDB")
    run_p.add_argument("--runs", type=int, default=5, help="Số lần chạy mỗi sample (tối thiểu 3)")
    run_p.set_defaults(func=_cmd_run)

    query_p = sub.add_parser("query", help="Xếp hạng observation theo latency (ví dụ OLAP)")
    query_p.add_argument("--db", default="benchmarks.duckdb")
    query_p.add_argument("--problem-fingerprint-id", default=None)
    query_p.add_argument("--min-quality", type=float, default=None)
    query_p.add_argument("--limit", type=int, default=20)
    query_p.set_defaults(func=_cmd_query)

    contrib_p = sub.add_parser(
        "contribute",
        help="Opt-in export benchmark evidence for community (pipeline metrics only)",
    )
    contrib_sub = contrib_p.add_subparsers(dest="contrib_command", required=True)

    export_p = contrib_sub.add_parser(
        "export",
        help="Export contribution bundle JSON — no notes, samples, or AI agent data",
    )
    export_p.add_argument("--db", default="benchmarks.duckdb")
    export_p.add_argument("--experiment-id", required=True)
    export_p.add_argument("--problem", required=True, help="problem.yaml used for the run")
    export_p.add_argument("--pipelines", required=True, nargs="+", help="pipeline.yaml files used")
    export_p.add_argument("--out", default="contribution.json")
    export_p.add_argument(
        "--i-agree-to-terms",
        action="store_true",
        help="Required: ODC-BY-1.0, pipeline benchmark metrics only (see pa-schema contribution-privacy)",
    )
    export_p.set_defaults(func=_cmd_contribute_export)

    return parser


def _cmd_contribute_export(args: argparse.Namespace) -> None:
    path = export_contribution_bundle(
        db_path=args.db,
        experiment_id=args.experiment_id,
        problem_path=args.problem,
        pipeline_paths=args.pipelines,
        out_path=args.out,
        terms_accepted=args.i_agree_to_terms,
    )
    print(f"=== pa-harness contribute export ===")
    print(f"Wrote {path}")
    print("Pipeline benchmark evidence only — NOT for AI interview/architecture agents.")
    print("Upload API: coming soon. For now, share bundle only via explicit opt-in channels.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"Lỗi: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
