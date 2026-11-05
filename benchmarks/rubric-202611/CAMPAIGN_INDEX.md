# Vanda campaign evidence index

[English](CAMPAIGN_INDEX.md) · [中文](CAMPAIGN_INDEX.zh-CN.md) · [한국어](CAMPAIGN_INDEX.ko.md)

All six jobs are complete and verified: **275 ordinary records and 75 independent profiles**. The sealed archive retains source snapshots, per-job PBS/stdout, resource and numerical preflight logs, placement, raw JSONL, invocation stdout/stderr and completion manifests. `evidence-sha256.json` checks every retained evidence file. Use `--verify-only` for the existing sealed campaign; do not reseal it.

```sh
python3 scripts/reproduce_rubric.py --verify-only
```

[Guide](../../RUBRIC_GUIDE.md) · [Results](../../analysis/rubric-202611/RESULTS.md)
