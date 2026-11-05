# Verified Vanda results (5 November 2026)

[中文](RESULTS.zh-CN.md) · [한국어](RESULTS.ko.md)

The six complete jobs pass `python3 scripts/reproduce_rubric.py --verify-only`: **275 ordinary measurements and 75 independent profiles**. The checks cover source identity, evidence hashes, real CUDA execution, 256-core preflight, actual thread placement, workload and numerical consistency. Sealed evidence is under `../../benchmarks/rubric-202611/`.

## Method and interpretation

FP64, seed 42, 20 timed iterations, two warmup iterations/reset, five repeats per configuration. Runtimes below are medians; error bars are observed min–max, not confidence intervals. Strong/hybrid/communication use N=4,000,000,D=K=32. Weak scaling fixes 100,000 samples per rank, reaching N=25,600,000. C=64 actual physical CPU cores/node, up to four nodes/256 cores. GPU comparisons use one NVIDIA A40 (46,068 MiB reported memory), with CPU1/CPU8 baselines in the same job.

Recorded hosts use Intel Xeon Platinum 8452Y (72 exposed CPUs, two sockets, 36 cores/socket, one thread/core, two NUMA nodes). PBS normalized the CPU allocations to 64 CPUs/444 GB per node, and the GPU job to 36 CPUs/240 GB/one GPU. Active resources differ from reserved resources. Builds use GCC 11.3.0, Open MPI 4.1.8, CUDA 12.4.131/sm_86; the driver is 575.57.08.

Loop and internal end-to-end times are separate: the latter includes data preparation, initialization, setup, warmup and final evaluation, but excludes MPI initialization and external process launch. Independent profiles are not ordinary performance samples. MPI phase time includes waiting. These synthetic fixed-iteration results do not establish real-data clustering accuracy or convergence speed.

## Serial problem size

At D=K=32, increasing N from 100,000 to 4,000,000 (40×) increases loop time from 0.748800 to 29.963383 s (40.01×). D=8→128 multiplies time by 16.04; K=8→128 multiplies it by 14.74. O(INKD) describes nominal work, while normalized constants vary with shape; the figures do not establish a specific cache/vectorization mechanism.

## Pure MPI strong scaling

| Configuration | Median loop (s) | Speedup vs same-job V0 | Efficiency |
|---|---:|---:|---:|
| V0 | 29.975499 | 1.00 | — |
| V1 / 64 cores | 0.766059 | 39.13 | 61.14% |
| V1 / 128 cores | 0.402175 | 74.53 | 58.23% |
| V1 / 256 cores | 0.229259 | 130.75 | 51.07% |

Using same-job V1/P=1 (29.772404 s) instead gives 129.86× and 50.73% at 256 cores. P≤64 uses one node, P=128 two, P=256 four. Efficiency is already below ideal inside one node. The representative P=256 diagnostic reduction is 0.040181 s, 17.64% of that sample's 0.227751 s loop; this share is not pure network time or an ordinary-runtime estimate.

## Pure MPI weak scaling

P=1 loop median is 0.763801 s; P=256 is 1.331356 s. Weak efficiency T1/TP is **57.37%** and throughput speedup P×T1/TP is **146.87×**. They are not fixed-size serial speedups. In the P=256 diagnostic, reduction accounts for 4.93%, while local accumulation grows from 0.763034 s (P=1 profile) to 1.263653 s. Communication alone does not explain the loss; unmeasured system/NUMA/resource effects remain possible explanations.

## Communication

| P | Allreduce (s) | Reduce+Bcast (s) | Change |
|---|---:|---:|---:|
| 64 | 0.541884 | 0.541480 | -0.07% |
| 256 | 0.225697 | 0.224374 | -0.59% |

Ranges overlap, so no stable winner is established. Reduce+Bcast must include its broadcast/control stage; comparing reduction alone omits required work. This job's timings must not replace the separate strong-scaling baseline.

## Fixed-256-core MPI+OpenMP

Same-job V1/256 is 0.228162 s. The lowest V3 median is 0.225800 s at 64×4, only **1.04% lower**, with overlapping ranges. V2/32×8 is 0.694824 s, **204.53% slower** than pure MPI; matched V3/32×8 is 0.226163 s (3.07× faster than V2).

At 32×8, representative accumulation takes 0.639223 s for V2 and 0.191290 s for V3. V3 merge is 0.000208 s, 0.091% of its diagnostic loop. Private buffers avoid a large accumulation penalty, but the difference is not pure atomic waiting. V3/64×4 end-to-end time is 0.407674 s versus 0.316061 s for V1/256, so a small loop gain is not an application-level gain.

## Single GPU

| N | GPU loop (s) | Loop CPU1/GPU | Loop CPU8/GPU | Total CPU1/GPU | Total CPU8/GPU |
|---|---:|---:|---:|---:|---:|
| 100,000 | 0.057927 | 13.00 | 2.81 | 2.84 | 0.91 |
| 1,000,000 | 0.662906 | 11.26 | 2.10 | 4.48 | 1.31 |
| 4,000,000 | 2.704171 | 11.05 | 1.45 | 4.64 | 1.15 |

At N=100,000, GPU total is 0.349317 s versus CPU8's 0.318718 s. At N=4,000,000 the median-total GPU observation spends 4.789922 s in data preparation and 0.096223 s on initial upload, within an 8.488937 s total. These are components of one actual observation, not independent medians. Diagnostic events show assignment dominating device time: 2.705581 s versus 0.001045 s tile merge and 0.000806 s combined iterative transfers. Total-minus-loop time is not PCIe overhead alone. No multi-GPU claim or cross-job comparison with 256 CPU cores is made.

## Files

[Report figures: PNG/PDF/SVG](FIGURE_GUIDE.md) · [exact statistics](verified-20261105/statistics.csv) · [independent profiles](verified-20261105/profiles.csv). Ordinary statistics and independent diagnostics remain separate. Report formatting does not change the sealed observations.
