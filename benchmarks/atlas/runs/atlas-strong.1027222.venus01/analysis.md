# Atlas V3 single-node process strong-scaling results

Job `1027222.venus01`, 2026-10-24, compute node `cnode-33-43-39`. The analysis uses only data from this job, without combining it with the earlier N=100000 pilot.

## Verification results

- PBS Exit_status=0 and script exit_status=0; all 35 records are present, with 5 repeats for each of 7 configuration groups and no missing or duplicate IDs.
- Medians, minima and maxima in the raw JSONL and CSV match for every group.
- Data fingerprints, initial centroid sample IDs and final cluster counts are identical across all records, with counts summing to 1000000.
- SSE ranges from 73440053.240113213658 to 73440053.240119844675, with absolute span 6.63102e-06 and relative span 9.03e-14; independent verification passed a relative tolerance of 1e-12.
- This job did not rerun the entire numerical unit-test suite. The 12 tests in the preceding validation job 1027219 had passed; this round adds consistency checks for large-input results.
- All 140 rank-binding reports from 30 formal MPI launches are present and match the prechecks for each P.

## Environment and timing definition

AMD EPYC 7R13, KVM virtual machine; 96 CPUs, 2 sockets, 4 NUMA nodes and 1 hardware thread per core are visible. The job was allocated 12 cores and 8 GB, with a walltime of 5 minutes 11 seconds.

GCC 9.2.0, Open MPI 4.1.2, Python 3.8.5. Build options are `-O3 -std=c++17 -Wall -Wextra -Wpedantic`; the MPI program additionally uses `-fopenmp -DKM_MPI`. Full compilation commands are in the main PBS log. Python's self-reported build compiler, GCC 7.3.0, does not mean that version was used for the C++ algorithm in this experiment.

N=1000000, D=32, K=32 and seed=42 are fixed; initial centroids are restored after 2 warmup iterations, followed by 20 formally measured iterations. Each group has 5 repeats, with configurations shuffled in each batch. V3 uses 1 thread per process and Allreduce communication; V1, V2 and multithreaded V3 were not measured.

The table below uses the median of `kernel_seconds`, the maximum Lloyd-iteration time across ranks. Data generation, initialization, warmup, final evaluation, MPI launch and compilation are excluded; this must not be called whole-job or end-to-end time. Medians of total and external launch times for each group are saved separately in analysis.audit.json.

## Performance results

| Version | P (T=1) | Median kernel time/s | Minimum–maximum/s | Speedup over V0 | Efficiency over V0 | Speedup over V3(P=1) | Efficiency over V3(P=1) |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 | 1 | 11.232365 | 11.083708–11.268552 | 1.000× | 100.00% | — | — |
| V3 | 1 | 10.966528 | 10.801994–11.109828 | 1.024× | 102.42% | 1.000× | 100.00% |
| V3 | 2 | 5.455342 | 5.440761–5.619235 | 2.059× | 102.95% | 2.010× | 100.51% |
| V3 | 3 | 3.845761 | 3.606678–3.922051 | 2.921× | 97.36% | 2.852× | 95.05% |
| V3 | 4 | 2.701160 | 2.677779–2.829734 | 4.158× | 103.96% | 4.060× | 101.50% |
| V3 | 6 | 1.835040 | 1.809149–1.958218 | 6.121× | 102.02% | 5.976× | 99.60% |
| V3 | 12 | 0.949930 | 0.912044–0.997377 | 11.824× | 98.54% | 11.545× | 96.20% |

Relative to V0: S=T_V0/T_P, E=S/P. Relative to V3(P=1): S_MPI=T_V3,1/T_V3,P, E_MPI=S_MPI/P. Efficiency uses the P cores actually used by each run; PBS reserves 12 cores for the whole job, and the two must not be confused. Ranges are minima–maxima from 5 measured runs, not confidence intervals.

V3's median time with 12 processes is 0.949930 seconds, giving 11.824× speedup and 98.54% efficiency over V0; relative to the same V3 implementation with one process, speedup is 11.545× and efficiency 96.20%. This input exhibits near-linear scaling over 1–12 processes on this single node.

Single-process V3 has a median time about 2.37% below V0. They are separately compiled serial and MPI/OpenMP executables, so speed ratios relative to V0 include that difference. At P=2,4,6, efficiency over V0 slightly exceeds 100%; with the same-implementation baseline, P=2,4 also slightly exceed 100%. These ratios of raw measurements should be retained as observed. Changes in cache working sets, compilation paths and system variation are possible factors; hardware counters were not measured, so causality cannot be determined and stable superlinear benefits should not be claimed.

## CPU placement and limitations

PBS-available OS CPUs are `40-45,86-91`. V0 is pinned to CPU 40 with taskset; MPI rank 0 prechecks for every P are also on CPU 40. Each rank uses only one core, without overlap or oversubscription.

- P=1,2,3,4,6: CPUs are used consecutively from 40, all on socket 0, NUMA node 1.
- P=12: ranks 0–5 are on CPUs 40–45 and ranks 6–11 on CPUs 86–91; sockets 0/1 and NUMA nodes 1/3 are used.

No individual multithreaded rank spans sockets in this experiment, but the overall P=12 placement spans two sockets. The comparison from 6 to 12 processes therefore involves more cores, more cache/memory resources and cross-socket communication simultaneously; it cannot be interpreted as an experiment with strictly unchanged NUMA conditions or extrapolated across nodes.

Actual OS affinity was probed before formal timing with an independent Python rank probe; the 30 formal MPI launches additionally checked that logical binding reports matched probe reports. The timed program did not sample sched_getaffinity every iteration. The evidence supports consistent mapping in this experiment, not continuous monitoring or a guarantee of exclusive physical hardware use.

Warnings about missing optional MPI components libbat.so, libosmcomp.so.3 and libpsm_infinipath.so.1 were marked ignored and did not prevent these runs. Multi-node network performance has not been validated.

## Suggested wording for the report

On one AMD EPYC 7R13 compute node of Atlas, N=1000000, D=32 and K=32 were fixed, with 2 warmup iterations, 20 timed iterations and 5 repeats per configuration. Each process used 1 thread, and V3 used Allreduce. Median kernel time was 11.232365 seconds for V0 and 0.949930 seconds for V3 with 12 processes, corresponding to a speedup over serial of 11.824 and efficiency of 98.54%; using single-process V3 as the baseline, speedup was 11.545 and efficiency 96.20%. All runs used identical data and initial centroids, with identical final cluster counts and an SSE relative span below 1e-12. The 12-process configuration used two sockets while the other configurations used one, so these results describe single-node process strong scaling under this node allocation and placement.

## Subsequent experiments

Prioritize MPI+OpenMP layout experiments at a fixed total core count next, explicitly recording each rank's core set and socket; this will complete the hybrid-parallel part of the assignment. Then compare V2/V3, communication methods and weak scaling separately as needed. Small advantages should be judged alongside variation ranges and additional repeats.

This report provides no conclusions about hybrid thread scaling, cross-node scaling or communication bottlenecks. Retain the uploaded source package, raw results, compilation logs and analyze.py in this directory for verification.
