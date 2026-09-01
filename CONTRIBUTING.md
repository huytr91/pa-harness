# Contributing to pa-harness

Thank you for helping improve Pipeline Architect benchmarks.

## Observations must come from harness runs

- **Do not** submit hand-edited benchmark numbers.
- Run `python cli.py run` with `runs >= 3`.
- Observations include `checksum`, `harness_version`, and `run_count`.

## Hardware fingerprint

Auto-detected only. Do not override CPU/GPU/RAM in contributed data.

## Adapters

Add real tool wrappers in [pa-adapters](https://github.com/huytr91/pa-adapters) via PR.
Keep mock adapters for CI and offline demos.

## Community data (future central API)

When uploading observations (opt-in):

- You agree data may be used under **ODC-BY** or **CC-BY-4.0** (aggregate leaderboard).
- Default: **local-only** — nothing leaves your machine unless you opt in.

## Development

```bash
pip install -e ../pa-adapters
pip install -r requirements.txt
python -m pytest test_quality_signals.py -q
```
