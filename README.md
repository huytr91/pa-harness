# pa-harness

**Local benchmark engine** for Pipeline Architect — run pipelines on your machine,
measure latency/RAM, infer relative quality (Bradley-Terry), write observations to DuckDB.

Part of [Pipeline Architect](https://github.com/huytr91/pipeline-architect) (MIT).

**No API keys required.**

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

## Quick start

```bash
python cli.py run \
  --problem problem.example.yaml \
  --pipelines pipelines/vn-ocr-native-fallback-v1.yaml pipelines/vn-ocr-baseline-v1.yaml \
  --samples-dir samples \
  --db benchmarks.duckdb \
  --runs 5

python cli.py query --db benchmarks.duckdb --min-quality 0.4
```

## What it measures

| Signal | Method |
|--------|--------|
| Latency | `time.perf_counter()` over N≥3 runs per sample |
| Peak RAM | RSS sampling during run |
| Quality | Cross-pipeline agreement + Bradley-Terry (no ground truth required) |

Hardware fingerprint is **auto-detected** — never self-reported.

## Mock vs real adapters

Built-in components come from [pa-adapters](https://github.com/huytr91/pa-adapters) (`builtin` mocks).
Replace with real OCR/parser adapters via `@register` — see pa-adapters README.

## Anti-fraud defaults

- `runs_per_sample` must be ≥ 3
- Pipeline config `checksum` stored with each observation
- `harness_version` stamped on every record

## Related repos

- [pa-schema](https://github.com/huytr91/pa-schema) — Observation + Solution Pipeline Packet JSON Schema
- [pa-adapters](https://github.com/huytr91/pa-adapters) — component wrappers

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
