# Recorded Atlas experiments

Five performance studies now share one directory layout. The earlier four were archived on 25 October 2026; the fixed-P=2 study was merged on 27 October. Raw run files and submitted source archives remain byte-for-byte intact. Indexes, the manifest and checksums were updated for this layout migration. Original downloads remain in the project HPC folder.

```text
atlas/
  manifest.json
  checksums.sha256
  runs/
    atlas-validation.1027219.venus01/
    atlas-strong.1027222.venus01/
    atlas-hybrid.1027229.venus01/
    atlas-threads.1027231.venus01/
    atlas-communication.1027272.venus01/
    atlas-thread-scaling.1028185.venus01/
  source-packages/
    project3-atlas-<study>.tar.gz
```

| Study | Job ID | Ordinary observations | Raw measurements |
|---|---|---:|---|
| Strong scaling | 1027222.venus01 | 35 | [strong.jsonl](runs/atlas-strong.1027222.venus01/strong.jsonl) |
| Fixed 12-core hybrid layouts | 1027229.venus01 | 30 | [hybrid.jsonl](runs/atlas-hybrid.1027229.venus01/hybrid.jsonl) |
| V2/V3 thread strategies | 1027231.venus01 | 30 | [raw.jsonl](runs/atlas-threads.1027231.venus01/raw.jsonl) |
| Communication strategies | 1027272.venus01 | 30 | [raw.jsonl](runs/atlas-communication.1027272.venus01/raw.jsonl) |
| Fixed P=2 thread scaling | 1028185.venus01 | 50 | [timing.jsonl](runs/atlas-thread-scaling.1028185.venus01/timing.jsonl) |

175 ordinary performance observations; 50 independent diagnostic profiles counted separately. Validation/pilot observations and the latest 20 small-data preflights are excluded from the performance total.

N=1,000,000; D=32; K=32; seed=42; 20 timed iterations; 2 warmups; 5 repeats/configuration.

One command audits all five studies. Use --verify-only for integrity checks. Full audits regenerate results in a new output directory, preserving archived inputs. The specialized thread-scaling entry point remains available for a single-study audit.

```sh
python3 -B scripts/reproduce_atlas.py --verify-only
python3 -B scripts/reproduce_atlas.py --output artifacts/atlas-audit-new
# Optional single-study entry point:
python3 -B scripts/reproduce_atlas_thread_scaling.py --output artifacts/thread-scaling-audit-new
```

The latest study uses timing.jsonl for ordinary observations and profile.jsonl for separate profiles. Every profile attributes all phases to its same-sample maximum-kernel rank. Diagnostics are not performance observations. Missing PBS history/stdout and absent executable binaries are documented in this study’s manifest entry.

See [unified report results](../../analysis/atlas/report_results.md) and the [fixed-P=2 study](../../analysis/atlas/THREAD_SCALING.md).
