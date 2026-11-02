# Atlas V2/V3 thread-accumulation strategy comparison results

[English](analysis.md) | [简体中文](analysis.zh-CN.md) | [한국어](analysis.ko.md)

Job `1027231.venus01`, 2026-10-24, node `cnode-33-43-39`. Strategy comparisons use only timings from matched configurations within this job.

## Verification findings

- Both PBS and script exit statuses are 0; checksums passed for all 27 uploaded source files.
- There are 30 formal records, covering 6 configuration groups with 5 repeats each; original chunk files match the merged file, and the statistics in CSV and comparisons.json have all been independently recalculated.
- Data fingerprints and initial centroids match this job's V0 numerical reference; all formal runs have identical final cluster counts, totaling 1000000.
- SSE ranges from 73440053.240119844675 to 73440053.240119874477; the maximum absolute error against V0 is 6.66082e-06 and the scaled error is 9.07e-14. Here scaled error means absolute error/max(1,abs(V0 SSE)).
- Centroid, label, count and SSE comparisons passed for all 6 small-data groups; specific errors are in preflight-check.json and analysis.audit.json.
- Checked 120 rank records and 360 OpenMP thread-probe records taken before formal launches. Both strategies and all repeats at the same P/T use identical rank/thread core placements, without overlap or allocation violations.

## Environment and comparison scope

GCC 9.2.0, Open MPI 4.1.2, Python 3.8.5, on an AMD EPYC 7R13 KVM node. N=1000000, D=32, K=32 and seed=42 are fixed; initial centroids are restored after 2 warmup iterations, followed by 20 timed iterations. All configurations use P×T=12 on one node.

For all 3 layouts, every V3 run is faster than every corresponding V2 run, with no overlap in timing ranges.

## Performance results

Times are medians of kernel_seconds; data generation, initialization, warmup, final evaluation and launch probing are excluded from kernel time. Within each P/T, the two strategies are interleaved with randomized order in every round; P/T groups run in blocks, rather than globally interleaving all configurations.

| P×T | V2 atomic-update median/s | Minimum–maximum/s | V3 private-buffer median/s | Minimum–maximum/s | First strategy time/second strategy time | Second strategy time reduction |
|---|---:|---:|---:|---:|---:|---:|
| 2×6 | 1.501355 | 1.431110–1.544514 | 0.897849 | 0.862031–0.954998 | 1.672× | 40.20% |
| 4×3 | 1.373188 | 1.340761–1.394033 | 0.893993 | 0.872011–0.981837 | 1.536× | 34.90% |
| 6×2 | 1.155894 | 1.097906–1.196416 | 0.943962 | 0.920078–0.980020 | 1.225× | 18.33% |

The median V2/V3 time ratios are 1.672 at P=2, T=6; 1.536 at P=4, T=3; and 1.225 at P=6, T=2. The observed trend of increasing benefit with more threads is consistent with the design motivation of using private buffers to reduce shared atomic updates.

The process count changes at the same time, altering data partitioning, communication and cache conditions. Atomic wait time and hardware counters were not directly recorded, so the entire timing difference cannot be quantitatively attributed to atomic contention. Further breakdown of causes requires separate profiling, keeping diagnostic samples out of formal timings.

The OS CPU allocation is `40,41,42,43,44,45,86,87,88,89,90,91`, spanning sockets 0,1. Cross-socket ranks for the measured layouts are `{"2": [], "4": [], "6": []}`. It is therefore necessary to distinguish a job spanning sockets from an individual rank's threads spanning sockets; matched strategies maintain identical placements.

These ratios compare strategies at fixed resources, rather than strong-scaling speedups relative to serial execution. The large-input V0 was run only once within this job for numerical checks; it is not a repeated timing baseline.

## Limitations and next steps

Thread affinity comes from an independent OpenMP probe before algorithm execution; the wrapper subsequently executes the algorithm with the same CPU mask and environment, while the algorithm also checks actual team size. These records are not live thread samples inside the algorithm's timing loop.

Nodes, socket/NUMA allocations and system states may differ between jobs; small differences between these V3 times and those of the earlier hybrid job must not be interpreted as optimization gains. No V0 time from another job was used to calculate speedup here.

The conclusions cover only the current synthetic data size, node allocation and tested strategies. All raw records, compilation logs and placement records are retained; analysis can be recalculated with HPC/analyze-atlas-strategy-results.py. The prepared communication-method comparison can be run next, retaining the same representative P/T layouts.
