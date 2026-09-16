# pa-harness

**Local benchmark engine** for Pipeline Architect — run **multi-domain** AI pipelines on your machine,
measure latency/RAM, infer relative quality (Bradley-Terry), write observations to DuckDB.

Domains are selected via `problem_fingerprint.domain` (OCR, audio, vision, …) — not hardcoded to OCR.

Part of [Pipeline Architect](https://github.com/huytr91/pipeline-architect) (MIT).

**No API keys required.**

## Domains (examples in repo)

| `domain` | Problem file | Notes |
|----------|--------------|--------|
| `document-ocr` | `problem.example.yaml` | First reference vertical; sample pipelines in `pipelines/` |
| `audio-transcription` | `problem.audio.example.yaml` | Mock ASR components via pa-adapters |
| `image-classification` | `problem.image.example.yaml` | Mock vision components via pa-adapters |

See [multi-domain](https://github.com/huytr91/pa-schema/blob/main/docs/multi-domain.md).

## Install

```bash
git clone https://github.com/huytr91/pa-harness.git
cd pa-harness
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
# For local dev with sibling pa-adapters repo:
# pip install -e ../pa-adapters && pip install -e .
```

## Quick start (document-ocr — reference vertical)

```bash
python cli.py run \
  --problem problem.example.yaml \
  --pipelines pipelines/vn-ocr-native-fallback-v1.yaml pipelines/vn-ocr-baseline-v1.yaml \
  --samples-dir samples \
  --db benchmarks.duckdb \
  --runs 5

python cli.py query --db benchmarks.duckdb --min-quality 0.4
```

Other domains: point `--problem` at `problem.audio.example.yaml` or `problem.image.example.yaml` and supply matching `pipeline.yaml` definitions (mock components in pa-adapters).

## SAMPLE beachhead results (L2 operational)

Published metrics only (no PDFs): [`results/sample-ocr-vi/`](results/sample-ocr-vi/).

- **96 runs** = 16 multi-page VI PDFs × 3 × `vn-pdf-extract-lite-v1` / `vn-pdf-extract-deep-v1`
- Measures latency / RAM / success / extracted `text_chars` via **pypdf text-layer** (not scan OCR)
- Relative quality only — no ground-truth CER

```bash
# Requires local SAMPLE PDFs (not in git) +: pip install 'pa-adapters[pdf]'
python cli.py run \
  --problem problem.ocr-sample.yaml \
  --pipelines pipelines/vn-pdf-extract-lite-v1.yaml pipelines/vn-pdf-extract-deep-v1.yaml \
  --samples-dir ../SAMPLE \
  --db benchmarks-sample-full.duckdb \
  --runs 3
python export_sample_results.py benchmarks-sample-full.duckdb results/sample-ocr-vi
```

## What it measures

| Signal | Method |
|--------|--------|
| Latency | `time.perf_counter()` over N≥3 runs per sample |
| Peak RAM | RSS sampling during run |
| Quality | Cross-pipeline agreement + Bradley-Terry (no ground truth required) |

Hardware fingerprint is **auto-detected** — never self-reported.

## Mock vs real adapters

Built-in components come from [pa-adapters](https://github.com/huytr91/pa-adapters) (`builtin` mocks for OCR, ASR, vision, …).
Add real tools (PaddleOCR, Whisper, …) via `@register` — see pa-adapters README.

## Anti-fraud defaults

- `runs_per_sample` must be ≥ 3
- Pipeline config `checksum` stored with each observation
- `harness_version` stamped on every record

## Related repos

- [pa-schema](https://github.com/huytr91/pa-schema) — Observation + Solution Pipeline Packet JSON Schema
- [pa-adapters](https://github.com/huytr91/pa-adapters) — component wrappers (all domains)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
