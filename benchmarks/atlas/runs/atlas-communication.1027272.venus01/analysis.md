# Atlas V3 communication-strategy comparison results

[English](analysis.md) | [简体中文](analysis.zh-CN.md) | [한국어](analysis.ko.md)

Job `1027272.venus01`, 2026-10-24 (Singapore time), node `cnode-33-43-32`. Strategy comparisons use only timings from matched configurations within this job.

## Verification findings

- Both PBS and script exit statuses are 0; checksums passed for all 27 uploaded source files.
- There are 30 formal records, covering 6 configuration groups with 5 repeats each; original chunk files match the merged file, and the statistics in CSV and comparisons.json have all been independently recalculated.
- Data fingerprints and initial centroids match this job's V0 numerical reference; all formal runs have identical final cluster counts, totaling 1000000.
- SSE ranges from 73440053.240119844675 to 73440053.240119844675; the maximum absolute error against V0 is 6.63102e-06 and the scaled error is 9.03e-14. Here scaled error means absolute error/max(1,abs(V0 SSE)).
- Centroid, label, count and SSE comparisons passed for the selected small-data configurations; specific errors are in preflight-check.json and analysis.audit.json.
- Checked 120 rank records and 360 OpenMP thread-probe records taken before formal launches. Both strategies and all repeats at the same P/T use identical rank/thread core placements, without overlap or allocation violations.

## Environment and comparison scope

GCC 9.2.0, Open MPI 4.1.2, Python 3.8.5, on an AMD EPYC 7R13 KVM node. N=1000000, D=32, K=32 and seed=42 are fixed; initial centroids are restored after 2 warmup iterations, followed by 20 timed iterations. All configurations use P×T=12 on one node.

Specific performance differences between layouts appear below; minimum–maximum ranges are not confidence intervals.

## Performance results

Times are medians of kernel_seconds; data generation, initialization, warmup, final evaluation and launch probing are excluded from kernel time. Within each P/T, the two strategies are interleaved with randomized order in every round; P/T groups run in blocks, rather than globally interleaving all configurations.

| P×T | Allreduce median/s | Minimum–maximum/s | Reduce+Bcast median/s | Minimum–maximum/s | First strategy time/second strategy time | Second strategy time reduction |
|---|---:|---:|---:|---:|---:|---:|
| 2×6 | 0.910166 | 0.906586–0.930287 | 0.913610 | 0.888920–0.947241 | 0.996× | -0.38% |
| 4×3 | 0.919556 | 0.916105–0.929694 | 0.935007 | 0.886339–0.949262 | 0.983× | -1.68% |
| 6×2 | 0.923267 | 0.889835–0.927843 | 0.922502 | 0.887874–0.927026 | 1.001× | 0.08% |

A negative value for “second strategy time reduction” means the second strategy has a longer observed median time.

Only the communication strategy changes at a given P/T; differences should be judged alongside repeat ranges. These results do not directly measure communication-phase costs in isolation; separate profiling is required to analyze bottlenecks.

Median time changes for Reduce+Bcast relative to Allreduce are +0.38% at 2×6, +1.68% at 4×3 and -0.08% at 6×2. The two timing ranges overlap in every layout; this experiment provides insufficient evidence that either communication strategy has a stable performance advantage. The default Allreduce may be retained, but that choice must not be described as proof of performance superiority. The reduction/broadcast phases were not measured separately, so similar total kernel times do not imply equal times for the communication phases themselves.

The OS CPU allocation is `60,61,62,63,64,65,66,67,68,69,70,71`, entirely on socket 1. Cross-socket ranks for the measured layouts are `{"2": [], "4": [], "6": []}`. It is therefore necessary to distinguish a job spanning sockets from an individual rank's threads spanning sockets; matched strategies maintain identical placements.

These ratios compare strategies at fixed resources, rather than strong-scaling speedups relative to serial execution. The large-input V0 was run only once within this job for numerical checks; it is not a repeated timing baseline.

## Limitations and next steps

Thread affinity comes from an independent OpenMP probe before algorithm execution; the wrapper subsequently executes the algorithm with the same CPU mask and environment, while the algorithm also checks actual team size. These records are not live thread samples inside the algorithm's timing loop.

Nodes, socket/NUMA allocations and system states may differ between jobs; small differences between these V3 times and those of the earlier hybrid job must not be interpreted as optimization gains. No V0 time from another job was used to calculate speedup here.

The conclusions cover only the current synthetic data size, node allocation and tested strategies. All raw records, compilation logs and placement records are retained; analysis can be recalculated with HPC/analyze-atlas-strategy-results.py. The main experimental data have been collected, so figures and report preparation can begin; weak scaling, profiling and multi-node experiments can be added as required by the report.
