# Rubric campaign evidence index

[中文](CAMPAIGN_INDEX.zh-CN.md) · [한국어](CAMPAIGN_INDEX.ko.md)

Status: **awaiting new HPC measurements**. No new runtime results or plots are claimed.

Place six complete job directories under `runs/`, one per suite: serial, strong, weak, hybrid, communication, gpu. Each retains `probe/` and `measurements/`, PBS script and scheduler output. Ordinary and diagnostic files remain separate. Expected totals: 275 ordinary and 75 independent diagnostic records.

See [execution, validation, archival and packaging](../../RUBRIC_GUIDE.md). Run `python3 scripts/reproduce_rubric.py --status` from the repository root. Only after all six jobs pass the full audit, use `--seal --verify-only` to create `evidence-sha256.json`; subsequent verification checks every retained evidence file. The source ZIP has a separate `PACKAGE-SHA256.json`.

`campaign.json` records the planned matrix and pending status. It is not a measurement manifest. Do not change its status to complete before real HPC acceptance.
