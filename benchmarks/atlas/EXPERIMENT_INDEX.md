# Recorded Atlas experiments

[English](EXPERIMENT_INDEX.md) | [简体中文](EXPERIMENT_INDEX.zh-CN.md) | [한국어](EXPERIMENT_INDEX.ko.md)

These are the original, **unredacted** records copied from the sibling `HPC/`
folder on 2026-10-25. Hostnames, usernames, job IDs, commands and paths remain as
recorded. The final bundle retains raw runs and measured-source snapshots; superseded planning notes are excluded.
The original sibling folder was left intact.

## Contents

```text
manifest.json       Formal workloads, record counts and evidence paths
checksums.sha256    SHA-256 inventory of this evidence bundle
runs/               Five job directories: validation/pilot and four formal studies
source-packages/    Six original standalone source snapshots, kept byte for byte
```

| Study | Job ID | Formal records | Raw measurements |
| --- | --- | ---: | --- |
| Strong scaling | 1027222.venus01 | 35 | [strong.jsonl](runs/atlas-strong.1027222.venus01/strong.jsonl) |
| Fixed 12-core hybrid | 1027229.venus01 | 30 | [hybrid.jsonl](runs/atlas-hybrid.1027229.venus01/hybrid.jsonl) |
| V2/V3 thread strategies | 1027231.venus01 | 30 | [raw.jsonl](runs/atlas-threads.1027231.venus01/raw.jsonl) |
| Communication strategies | 1027272.venus01 | 30 | [raw.jsonl](runs/atlas-communication.1027272.venus01/raw.jsonl) |

All 125 formal measurements use N=1,000,000, D=32, K=32, seed=42, fixed 20
measured iterations, 2 warmup iterations and 5 repeats/configuration. The data
fingerprint is `7fcf2e8b0cc1a222`. Validation job `1027219.venus01` and its
smaller pilot workload are retained separately and excluded from this total.

The environment records identify the actual hardware, CPU allocations, compiler
and MPI versions. Allocation/NUMA layout differs between jobs; use matched
within-job comparisons. The hybrid comparison measures a fixed total of 12 cores;
it does not provide a new serial strong-scaling baseline. Full-size V0 runs in
the strategy studies are numerical references, not repeated timing baselines.

## Reproduce the analysis

Run from the repository root with Python 3.8+ (standard library only):

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py --output artifacts/atlas-audit
```

Integrity checking covers all files listed in `checksums.sha256`. The second
command copies the four formal studies into a new directory, restores the helper
versions from each study's source snapshot and reruns the original audit scripts.
Outputs include recalculated statistics, placement/numerical checks, Chinese
analysis reports and `summary.json`. It never modifies this bundle or reruns the
HPC timing experiments. Existing output directories are rejected.

Validation/pilot records receive integrity checks; their saved analysis remains
historical evidence rather than a newly regenerated fifth audit. Result interpretation is in [the report results](../../analysis/atlas/report_results.en.md) and each job's `analysis.md`; each document links to its Chinese and Korean editions.

## Rerun the computation

Use an original archive in `source-packages/` to rerun the measured source, or
use [the package builder](../../hpc/ATLAS_RUN_GUIDE.md) for the current checkout. In either
case, submit from a separate extracted package directory. Data is generated in
memory; downloading or uploading a large input dataset is unnecessary.

The saved paths in raw records and historical notes describe the original runs.
They are not dependencies on those accounts or local folders. The new package
builder and offline analysis commands work relative to the cloned repository.

Historical run instructions remain inside the original source snapshot archives. Current commands are consolidated in the HPC guide linked above. `checksums.sha256` covers the retained evidence and documentation; all 125 formal measurements remain unchanged.
