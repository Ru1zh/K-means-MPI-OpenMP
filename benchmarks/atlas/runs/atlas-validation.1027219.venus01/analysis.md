# Atlas CPU validation and initial trial results

Job: `1027219.venus01`. This document analyzes only this job's output, without combining earlier small examples that lacked binding.

## Conclusions

- The job exited normally with `exit_status=0`.
- All 12 existing tests passed in 23.478 seconds, with no MPI tests skipped.
- There are 27 complete records across 9 configurations, each repeated 3 times; medians in the raw JSONL and CSV match.
- Data fingerprints, initial sample indices and final cluster counts match across all records. Cluster counts sum to 100000 in every run.
- V3 outperforms V2 in this trial; timing ranges for the two V3 communication methods overlap, so a stable advantage has not been established.
- The results are suitable as evidence that correctness checks and the experimental workflow run successfully. Formal speedup experiments still require pinning the serial baseline to a fixed CPU and further controlling cross-socket process placement.

## Environment and workload

- Node: `cnode-33-43-39`; AMD EPYC 7R13; KVM virtual machine.
- The node exposes 96 CPUs, 2 sockets and 4 NUMA nodes, with one hardware thread per core. The actual job was allocated only 12 cores and 8GB memory.
- The job shell's OS CPU affinity is `40-45,86-91`, on NUMA nodes 1 and 3 respectively.
- GCC 9.2.0; Open MPI 4.1.2; Python 3.8.5.
- N=100000, D=32, K=32 and seed=42 are fixed; 20 timed iterations and 2 warmup iterations; each configuration is repeated 3 times with interleaved execution.
- The table below uses the program's `kernel_seconds` output, excluding compilation, data generation, warmup and final evaluation from kernel time.

## Numerical consistency

The data fingerprint is `af0e4e99df2f2b9f`. Initial indices and final cluster counts are identical across all 27 runs.

SSE range: 7278124.14503207 to 7278124.14503219; the relative span is 1.66e-14, a small floating-point difference arising from different accumulation orders in this experiment. Every SSE passed comparison at relative tolerance `1e-12`.

This means that existing tests and this input revealed no numerical inconsistency; it does not prove correctness for every possible input.

## Timing comparison

P is the MPI process count and T the OpenMP threads per process; the core count used is P×T. V1 has only one compute thread per process. Ranges are minima and maxima of 3 measured runs, not confidence intervals.

| Version | P × T | Cores | Communication | Median time (seconds) | Minimum–maximum (seconds) | V0/this configuration's time |
|---|---:|---:|---|---:|---:|---:|
| V0 | 1 × 1 | 1 | — | 1.057740 | 1.022997–1.060406 | 1.00× |
| V1 | 1 × 1 | 1 | Allreduce | 1.052644 | 1.050617–1.101021 | 1.00× |
| V1 | 3 × 1 | 3 | Allreduce | 0.375743 | 0.356962–0.380635 | 2.82× |
| V2 | 1 × 4 | 4 | Allreduce | 0.351516 | 0.350265–0.386462 | 3.01× |
| V2 | 3 × 4 | 12 | Allreduce | 0.183623 | 0.182263–0.185220 | 5.76× |
| V3 | 1 × 4 | 4 | Allreduce | 0.259835 | 0.258280–0.267922 | 4.07× |
| V3 | 1 × 4 | 4 | Reduce+Bcast | 0.265874 | 0.261278–0.273635 | 3.98× |
| V3 | 3 × 4 | 12 | Allreduce | 0.103808 | 0.090803–0.110508 | 10.19× |
| V3 | 3 × 4 | 12 | Reduce+Bcast | 0.097674 | 0.088740–0.102100 | 10.83× |

The last column is an observed time ratio within this job; the serial baseline was not explicitly pinned to a CPU, so it is not a final speedup or parallel efficiency with all conditions controlled.

- At the same P=3, T=4 and Allreduce, V3's median time is about 56.5% of V2's, corresponding to an observed speed ratio of about 1.77. This trend is consistent with V3's design of using thread-private accumulation buffers to reduce shared atomic updates; confirming bottleneck causes still requires phase timing or profiling.
- V3 Reduce+Bcast has a median about 5.9% below Allreduce. Their ranges clearly overlap and there are only 3 repeats, so this does not establish a stable advantage for either communication strategy.
- Time ratios of about 4 or 10 apply only to this input, code, node and parameter set; they cannot be extrapolated to all data sizes or multiple nodes.

## Binding checks

All 24 MPI launches have complete binding reports. Every launch satisfies the following: the rank count matches the request, each rank is bound to T logical cores, and core sets of different ranks do not overlap.

There are two limitations:

1. In the 3 rank × 4 thread configuration, rank 1 is bound to 2+2 cores across sockets; this type of cross-socket rank appears 9 times in the trial logs. NUMA placement of its thread buffers and data may affect timings, and the current evidence cannot fully separate this effect from algorithmic optimization gains.
2. Core numbers in MPI logs are logical numbers from MPI's topology view and cannot be directly treated as OS CPU numbers. This trial did not record `sched_getaffinity` per rank, so item-by-item mapping between each binding set and the PBS allocation set has not yet been completed. Serial V0 is launched directly and, although constrained by the job's available CPU set, is not explicitly pinned to one CPU within it.

Component-loading warnings for `libbat.so`, `libosmcomp.so.3` and `libpsm_infinipath.so.1` were marked ignored by MPI and did not prevent this single-node run; these logs also do not establish availability of multi-node network components.

## Recommendations for the next phase

1. Retain the current compilation and test environment; do not overwrite the present raw files.
2. First record per-rank and OpenMP-thread OS CPU affinity, and pin V0 to one CPU within the PBS allocation set.
3. For hybrid layouts, prioritize comparisons that keep individual ranks within a socket; treat the cross-socket 3×4 case as a separate NUMA-sensitivity comparison, or clearly distinguish it in the report.
4. Initially try N=1000000, D=32 and K=32 with fixed iteration and warmup counts, repeating each configuration at least 5 times. Measure one run's duration before expanding to the full experiment matrix.
5. Organize pure-MPI strong scaling, fixed-core hybrid parallelism, communication strategies, weak scaling and data-distribution experiments separately; parameter comparisons should change only the target factor. Do not mix trace/profile diagnostic runs into formal performance data.
6. Validate MPI launch and communication separately for the multi-node phase; single-node results cannot replace multi-node validation.

## Local evidence

- `status.txt`: job exit code.
- `correctness.log`: individual results for the 12 tests.
- `environment.txt`: modules, compiler, Python, hardware topology, PBS slots and shell affinity.
- `binding-probe.json` and `binding-probe.stderr.log`: the first small binding example.
- `pilot.jsonl`: 27 raw records.
- `pilot.csv`: medians and ranges for 9 groups.
- `pilot.stderr.log`: parameters and binding information for 24 MPI launches.
- `analysis.audit.json`: verification results and derived statistics for this analysis.
