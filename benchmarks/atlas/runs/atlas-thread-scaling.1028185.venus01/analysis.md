# Atlas fixed-P thread scaling

Job `1028185.venus01`; host `cnode-33-43-32`; compiler `9.2.0`; MPI `Open MPI v4.1.2, package: Open MPI root@atlas7-c01 Distribution, ident: 4.1.2, repo rev: v4.1.2, Nov 24, 2021`.

P=2; T=1,2,3,4,6; N=1000000; D=32; K=32; seed=42; iterations=20; warmup=2.

All workload, numerical, matrix and placement checks passed, including 20 small-data preflight runs with labels, centroids and both measurement modes. This is a new independent job; timings must not be compared directly with older jobs. V0 is a numerical reference only.

Formal timings use only diagnostic=false timing records. Speedup is the same variant’s T=1 median divided by its T median; thread efficiency is speedup/T. Min–max ranges are not confidence intervals.

SSE: 73440053.2401–73440053.2401; max |SSE−V0|: 6.78003e-06; 50 timing + 50 profile records; 5 repeats/configuration.

| Variant | T | Median / s | Min / s | Max / s | Speedup T=1 | Efficiency |
|---|---:|---:|---:|---:|---:|---:|
| V2 | 1 | 5.932525 | 5.899510 | 5.961822 | 1.000 | 100.00% |
| V2 | 2 | 3.239149 | 3.204542 | 3.299726 | 1.832 | 91.58% |
| V2 | 3 | 2.706680 | 2.705456 | 2.786131 | 2.192 | 73.06% |
| V2 | 4 | 2.130149 | 2.114199 | 2.151687 | 2.785 | 69.63% |
| V2 | 6 | 1.488148 | 1.479371 | 1.503290 | 3.987 | 66.44% |
| V3 | 1 | 5.298626 | 5.265328 | 5.338572 | 1.000 | 100.00% |
| V3 | 2 | 2.635595 | 2.622310 | 2.664717 | 2.010 | 100.52% |
| V3 | 3 | 1.780568 | 1.749308 | 1.819223 | 2.976 | 99.19% |
| V3 | 4 | 1.323602 | 1.310441 | 1.343187 | 4.003 | 100.08% |
| V3 | 6 | 0.886366 | 0.875813 | 0.888638 | 5.978 | 99.63% |

Separate diagnostic profile samples are excluded from formal timing. Every sample attributes all phases to the rank with maximum kernel time (ties: smaller rank); percentages use that rank’s kernel time. Independent phase maxima across ranks cannot be summed. This is not a direct measurement of pure atomic waiting time. Cells below show median seconds and median percentages; their independent medians need not sum to the median kernel or 100%. Residual is kernel minus that rank’s phase sum.

| Variant | T | Kernel / s | accumulate | thread_merge | mpi_reduce | centroid_update | control_bcast | residual |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V2 | 1 | 5.919797 | 5.913905 (99.97%) | 0.000001 (0.00%) | 0.001415 (0.02%) | 0.000480 (0.01%) | 0.000001 (0.00%) | 0.000030 (0.00%) |
| V2 | 2 | 3.230638 | 3.217499 (99.69%) | 0.000002 (0.00%) | 0.009437 (0.29%) | 0.000514 (0.02%) | 0.000001 (0.00%) | 0.000027 (0.00%) |
| V2 | 3 | 2.702206 | 2.701160 (99.96%) | 0.000001 (0.00%) | 0.000307 (0.01%) | 0.000727 (0.03%) | 0.000001 (0.00%) | 0.000025 (0.00%) |
| V2 | 4 | 2.142938 | 2.141867 (99.95%) | 0.000002 (0.00%) | 0.000317 (0.01%) | 0.000721 (0.03%) | 0.000001 (0.00%) | 0.000021 (0.00%) |
| V2 | 6 | 1.488169 | 1.487167 (99.93%) | 0.000002 (0.00%) | 0.000214 (0.01%) | 0.000730 (0.05%) | 0.000001 (0.00%) | 0.000018 (0.00%) |
| V3 | 1 | 5.294189 | 5.248764 (99.36%) | 0.000020 (0.00%) | 0.033083 (0.63%) | 0.000488 (0.01%) | 0.000001 (0.00%) | 0.000035 (0.00%) |
| V3 | 2 | 2.648877 | 2.620389 (99.05%) | 0.000024 (0.00%) | 0.024468 (0.93%) | 0.000483 (0.02%) | 0.000001 (0.00%) | 0.000033 (0.00%) |
| V3 | 3 | 1.774273 | 1.773291 (99.94%) | 0.000039 (0.00%) | 0.000358 (0.02%) | 0.000704 (0.04%) | 0.000001 (0.00%) | 0.000020 (0.00%) |
| V3 | 4 | 1.324181 | 1.310940 (99.27%) | 0.000054 (0.00%) | 0.008961 (0.67%) | 0.000690 (0.05%) | 0.000001 (0.00%) | 0.000018 (0.00%) |
| V3 | 6 | 0.891704 | 0.875472 (99.88%) | 0.000073 (0.01%) | 0.000269 (0.03%) | 0.000710 (0.08%) | 0.000001 (0.00%) | 0.000018 (0.00%) |

Raw inputs are read-only; rerun `python3 hpc/analyze-atlas-thread-scaling.py RESULT_DIRECTORY` to regenerate.
