# -*- coding: utf-8 -*-
"""Pack one evidence-case out/ into public evidence/runs/<id>/ (no PDFs)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CASE_META = {
    "001-vietnamese-scanned-report": {
        "title": "Vietnamese scanned / annual reports",
        "question": (
            "Which extract pipeline is faster and more stable for multi-page "
            "Vietnamese report PDFs on a CPU-only machine?"
        ),
        "workload_summary": "4 multi-page VI report/scan PDFs · CPU-only · local",
        "prior": (
            "Prior guess: deeper page budget (deep) should always win on quality; "
            "probe is only for smoke checks."
        ),
        "sample_count": 4,
    },
    "002-financial-table": {
        "title": "Financial statements (BCTC / tables)",
        "question": (
            "On Vietnamese financial PDFs (often image/table heavy), does a deeper "
            "text-layer extract actually yield more usable text_chars — or just more latency/RAM?"
        ),
        "workload_summary": "7 Vietnamese financial-report PDFs · CPU-only · local",
        "prior": (
            "Prior guess: financial PDFs need deep extract + layout; probe should fail quality."
        ),
        "sample_count": 7,
    },
    "003-mixed-pdf-batch": {
        "title": "Mixed PDF batch (regulation + financial + scan)",
        "question": (
            "Which pipeline stays stable across a mixed batch — success rate, "
            "latency spread, peak RAM — when file types differ?"
        ),
        "workload_summary": "10 mixed VI PDFs · CPU-only · local · batch-style",
        "prior": (
            "Prior guess: one pipeline ranks best on every file type in a mixed batch."
        ),
        "sample_count": 10,
    },
}


def fmt_ms(ms: float) -> str:
    if ms >= 60000:
        return f"{ms/60000:.1f} min"
    if ms >= 1000:
        return f"{ms/1000:.1f} s"
    return f"{ms:.0f} ms"


def pack(case_id: str, out_src: Path, dest: Path) -> None:
    meta = CASE_META[case_id]
    src_json = out_src / "results.json"
    data = json.loads(src_json.read_text(encoding="utf-8"))
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_json, dest / "result.json")

    obs = {o["pipeline_id"]: o for o in data["observations"]}
    by_pipe = {p["pipeline_id"]: p for p in data["runs_summary"]["by_pipeline"]}
    hw = data.get("hardware") or {}

    order = [
        "vn-pdf-extract-probe-v1",
        "vn-pdf-extract-lite-v1",
        "vn-pdf-extract-deep-v1",
    ]
    labels = {
        "vn-pdf-extract-probe-v1": "A · probe (max 2 pages)",
        "vn-pdf-extract-lite-v1": "B · lite (max 5 pages)",
        "vn-pdf-extract-deep-v1": "C · deep (max 20 pages)",
    }

    # command.txt
    (dest / "command.txt").write_text(
        "\n".join(
            [
                f"# Evidence case {case_id}",
                f"# exported {datetime.now(timezone.utc).isoformat()}",
                "cd pa-harness",
                "python cli.py run \\",
                f"  --problem evidence-cases/{case_id}/problem.yaml \\",
                "  --pipelines pipelines/vn-pdf-extract-probe-v1.yaml \\",
                "             pipelines/vn-pdf-extract-lite-v1.yaml \\",
                "             pipelines/vn-pdf-extract-deep-v1.yaml \\",
                f"  --samples-dir evidence-cases/{case_id}/samples \\",
                f"  --db evidence-cases/{case_id}/bench.duckdb \\",
                "  --runs 3",
                f"python export_sample_results.py evidence-cases/{case_id}/bench.duckdb evidence-cases/{case_id}/out",
                "",
                "PDFs are NOT in git. Metrics only.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # environment.json
    env = {
        "hardware": hw,
        "harness_version": next(iter(obs.values()), {}).get("harness_version"),
        "runs_per_sample": 3,
        "pipelines": order,
        "sample_count": meta["sample_count"],
        "measurement": "pypdf text-layer extract (operational)",
        "not_measured": [
            "ground-truth CER/WER",
            "DOCX reconstruction quality",
            "table cell accuracy",
            "PaddleOCR / Tesseract scan OCR",
        ],
        "evidence_level": "L2_operational_measurement",
    }
    (dest / "environment.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # problem.yaml copy if exists
    prob = ROOT / "evidence-cases" / case_id / "problem.yaml"
    if prob.is_file():
        shutil.copy2(prob, dest / "problem.yaml")

    rows = []
    for pid in order:
        o = obs.get(pid, {})
        p = by_pipe.get(pid, {})
        rows.append(
            {
                "id": pid,
                "label": labels[pid],
                "latency_p50": o.get("latency_p50"),
                "latency_p95": o.get("latency_p95"),
                "peak_ram_mb": o.get("peak_ram_mb"),
                "success_rate": o.get("success_rate"),
                "quality_relative": o.get("quality"),
                "text_chars_mean": p.get("text_chars_mean"),
                "likely_scan_share": p.get("likely_scan_share"),
                "run_count": o.get("run_count"),
            }
        )

    # Interpretation: find fastest p50 with success=1, deepest text chars
    measured_lines = []
    valid = [r for r in rows if r["latency_p50"] is not None]
    if valid:
        fastest = min(valid, key=lambda r: r["latency_p50"])
        most_text = max(valid, key=lambda r: r["text_chars_mean"] or 0)
        heaviest = max(valid, key=lambda r: r["peak_ram_mb"] or 0)
        measured_lines.append(
            f"- Fastest p50 latency: **{labels[fastest['id']]}** ({fmt_ms(fastest['latency_p50'])})."
        )
        measured_lines.append(
            f"- Most extracted text_chars (mean): **{labels[most_text['id']]}** "
            f"({int(most_text['text_chars_mean'] or 0)})."
        )
        measured_lines.append(
            f"- Highest peak RAM: **{labels[heaviest['id']]}** "
            f"({heaviest['peak_ram_mb']:.0f} MB)."
        )
        if (fastest["id"] != most_text["id"]) or (
            most_text.get("likely_scan_share", 0) and most_text["likely_scan_share"] > 0.4
        ):
            measured_lines.append(
                "- **Prior ≠ Measured:** deeper/more complex is not automatically the winner "
                "on this workload/hardware — and many files look like scans (low text_chars)."
            )

    table = [
        "| Pipeline | p50 latency | p95 | Peak RAM | Success | Rel. quality* | Mean text_chars | Likely-scan share |",
        "|----------|------------:|----:|---------:|--------:|--------------:|----------------:|------------------:|",
    ]
    for r in rows:
        table.append(
            f"| {r['label']} | {fmt_ms(r['latency_p50'] or 0)} | {fmt_ms(r['latency_p95'] or 0)} | "
            f"{(r['peak_ram_mb'] or 0):.0f} MB | {(r['success_rate'] or 0):.0%} | "
            f"{(r['quality_relative'] or 0):.3f} | {int(r['text_chars_mean'] or 0)} | "
            f"{(r['likely_scan_share'] or 0):.0%} |"
        )

    readme = "\n".join(
        [
            f"# Evidence {case_id} — {meta['title']}",
            "",
            f"**Question:** {meta['question']}",
            "",
            "## Workload",
            "",
            meta["workload_summary"],
            "",
            f"- Samples: **{meta['sample_count']}** PDFs (bytes not published)",
            "- Runs per sample: **3**",
            "- Pipelines: probe / lite / deep (pypdf text-layer)",
            f"- Hardware: `{hw.get('cpu_class')}` · {hw.get('cores')} cores · "
            f"RAM `{hw.get('ram_bucket')}` · GPU `{hw.get('gpu_class')}`",
            "",
            "## Prior (recommendation — not evidence)",
            "",
            meta["prior"],
            "",
            "## Measured (this machine, this workload)",
            "",
            *table,
            "",
            "\\*Rel. quality = cross-pipeline agreement on extracted text — **not** CER/accuracy.",
            "",
            "## What happened?",
            "",
            *measured_lines,
            "",
            "## Honesty boundary",
            "",
            "- Measured: latency, RAM, success, extracted `text_chars`",
            "- **Not** measured: scan-OCR accuracy, DOCX fidelity, table cell correctness",
            "- Adapter: `pdf-native-parser` via **pypdf** (text layer). Image-only scans → ~0 chars.",
            "",
            "## Files",
            "",
            "- [`result.json`](./result.json) — raw export",
            "- [`environment.json`](./environment.json)",
            "- [`command.txt`](./command.txt) — reproduce",
            "- [`problem.yaml`](./problem.yaml)",
            "",
            "The result is specific to this workload and hardware. "
            "It is not a universal ranking.",
            "",
        ]
    )
    (dest / "README.md").write_text(readme, encoding="utf-8")
    print(f"Packed {dest}")


def main() -> None:
    dest_root = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT.parent / "oss" / "pipeline-architect" / "evidence" / "runs")
    for case_id in CASE_META:
        out_src = ROOT / "evidence-cases" / case_id / "out"
        if not (out_src / "results.json").is_file():
            print(f"SKIP {case_id}: no results yet")
            continue
        pack(case_id, out_src, dest_root / case_id)


if __name__ == "__main__":
    main()
