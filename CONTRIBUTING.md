# Contributing to pa-harness

Thank you for helping improve Pipeline Architect benchmarks.

## Pipeline evidence only — not for AI agents

Community contributions are **benchmark metrics for pipeline ranking / leaderboard only**.

**Never used by:**
- Interview agent (phỏng vấn / chat)
- Architecture agent (sinh candidate / LLM routing)
- Web chat context or LLM training

See [pa-schema contribution-privacy](https://github.com/huytr91/pa-schema/blob/main/docs/contribution-privacy.md).

### Export (opt-in)

```bash
python cli.py contribute export \
  --db benchmarks.duckdb \
  --experiment-id <from-run-output> \
  --problem problem.yaml \
  --pipelines pipelines/a.yaml pipelines/b.yaml \
  --out contribution.json \
  --i-agree-to-terms
```

**Included:** latency, RAM, quality, hardware class, domain/language constraints, pipeline checksum.  
**Excluded:** `problem.notes`, sample files, OCR output, paths, sessions, chat.

## Observations must come from harness runs

- **Do not** submit hand-edited benchmark numbers.
- Run `python cli.py run` with `runs >= 3`.
- Observations include `checksum`, `harness_version`, and `run_count`.

## Hardware fingerprint

Auto-detected only. Do not override CPU/GPU/RAM in contributed data.

## Adapters

Add real tool wrappers in [pa-adapters](https://github.com/huytr91/pa-adapters) via PR.
Keep mock adapters for CI and offline demos.

## Community data license

When exporting with `--i-agree-to-terms`:

- **ODC-BY-1.0** — anonymized pipeline metrics may appear on aggregate leaderboard.
- Default: **local-only** — nothing leaves your machine unless you export/upload.

Upload API: planned; export JSON is the contract today.

## Development

```bash
pip install -e ../pa-adapters
pip install -r requirements.txt
python -m pytest test_quality_signals.py test_contribute.py -q
```
