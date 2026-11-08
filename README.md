# Lloyd K-means: MPI + OpenMP + CUDA

[English](README.md) · [简体中文](README.zh-CN.md) · [한국어](README.ko.md)

C++17 implementation of Lloyd K-means, with serial, MPI, MPI+OpenMP and optional CUDA versions. The algorithm is implemented directly; no clustering library is used. Vanda experiments cover 256 CPU cores and one NVIDIA A40.

## Versions

| Version | Implementation |
|---|---|
| V0 | Serial reference |
| V1 | Serial local work per MPI rank |
| V2 | OpenMP shared atomic accumulation |
| V3 | OpenMP thread-private buffers followed by a merge |
| V4 | CUDA assignment and two-stage statistics merge; P=1, one GPU |

## Build

Requires C++17 and Make; MPI/OpenMP for parallel CPU execution; compatible CUDA toolkit and nvcc for V4. CPU builds do not require CUDA. Load matching compiler/MPI modules on HPC.

```sh
git clone https://github.com/Ru1zh/K-means-MPI-OpenMP.git
cd Code
make all CXX=g++ MPICXX=mpicxx
# Serial only:
make serial
```

Optional GPU build: 86 matches the measured A40; select the architecture of your actual GPU.

```sh
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

macOS with Homebrew Open MPI and libomp:

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

## Run

Synthetic data are generated in memory; no download or examples folder is needed.

```sh
./build/kmeans_serial --n 10000 --d 8 --k 16 --iterations 20
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 20
./build/kmeans_cuda --variant v4 --n 10000 --d 8 --k 16 --iterations 20
```

Use `--variant v1 --threads 1` for pure MPI, `v2` for atomic accumulation, and `--comm reduce-bcast` for the alternative collective strategy. Run an executable with `--help` for all options. Successful runs write one JSON object to stdout.

## Data and correctness

The seeded generator chooses one of 16 equally likely Gaussian groups, with centers in (-10,10) and standard-normal noise (sigma=1, Box-Muller). Values depend on global sample index and coordinate, so MPI partitioning preserves the input within the same build environment. Initial centroids are K distinct sampled points; generating groups and solver K are independent. Formal runs use seed=42 and disable `--skew`.

FP64 coordinates/sums; 64-bit counts. Exact ties select the lowest cluster index; empty clusters keep their previous centroids. Final labels/counts/SSE are recomputed using final centers. `--warmup` restores the initial state before timing. External text input is optional: first line `N D`, followed by exactly N×D finite coordinates.

## Tests

Python 3.8+ standard library only. Eleven CPU/MPI test methods cover hand-computed results, ties, empty clusters, unequal/empty partitions, convergence, warmup reset and phase timers; three optional GPU methods compare CPU/GPU outputs and verify failure without a device. Run MPI/GPU tests inside suitable allocations; skipped GPU tests do not constitute GPU validation.

```sh
make test
make test-mpi
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

## HPC experiments

The launcher targets Linux + PBS + Open MPI with shared project storage. Confirm queues, modules, walltime and physical-core allocation first. Put site-specific module commands in an external environment script. GPU jobs also need `CUDA_HOME` and `CUDA_ARCH`. The commands below generate six PBS files; inspect them before submitting.

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue CPU_QUEUE --gpu-queue GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
for suite in serial strong weak hybrid communication gpu; do
  qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh "artifacts/rubric-jobs/$suite.pbs"
done
```

Replace queue placeholders and the absolute environment-file path. Set C to the largest usable power of two in {8,16,32,64}; multi-node jobs request 256/C distinct nodes. Each job stages sources, builds, checks numerical results and actual affinity, then runs five shuffled repeats. Errors, overlapping CPU cores, insufficient resources or GPU failures stop the job; there is no CPU fallback. New results go to a fresh `artifacts/rubric-202611/<suite>.<job-id>/` directory.

## Formal matrix

All runs use FP64, seed=42, 20 timed iterations, two warmup iterations/reset and five repeats; D=K=32 unless varied. Total: 275 ordinary observations and 75 independent profiles.

| Study | Configuration | Ordinary / diagnostic records |
|---|---|---:|
| Serial | V0: N={100k,200k,500k,1M,2M,4M}; D,K={8,16,32,64,128}, one factor at a time; base N=1M,D=K=32 | 70 / 0 |
| Strong | V0 baseline + V1/P={1,2,4,8,16,32,64,128,256}; N=4M | 50 / 15 |
| Weak | V1, same P; N=100k×P | 45 / 15 |
| Hybrid | V2/V3 at P×T={256×1,128×2,64×4,32×8}, plus V1/256 | 45 / 10 |
| Communication | V1/P={C,256}, Allreduce vs Reduce+Bcast | 20 / 20 |
| GPU | N={100k,1M,4M}; V0/CPU1, V3/CPU8, V4/GPU1 in one job | 45 / 15 |

## Timing and interpretation

`kernel_seconds` is the maximum rank-local complete loop; `total_seconds` additionally includes data preparation, initialization, GPU setup/upload, warmup and final evaluation, excluding MPI initialization and external launch. Use `--profile` only in independent diagnostic runs. CPU attribution retains one actual critical rank’s complete phase vector; GPU device intervals use CUDA events. MPI intervals include waiting.

Strong speedup uses same-job V0 or V1/P=1, with efficiency S/P. Weak efficiency is T1/TP and throughput speedup P×T1/TP. Hybrid comparisons fix P×T=256. Compare only within matched jobs; error ranges are five-repeat observed min-max, not confidence intervals.

<!-- LOCAL_ARCHIVE_START -->

## Local results and figures

The GitHub repository includes code, aggregate tables and report figures. Raw job logs and frozen snapshots are excluded from the current Git tree and retained locally; raw-evidence audit commands require that local archive. The six Vanda jobs were verified on 5 November 2026: Intel Xeon Platinum 8452Y, C=64 active physical cores/node, up to four nodes, one A40; GCC 11.3.0, Open MPI 4.1.8, CUDA 12.4.131.

Strong scaling reaches 130.75× V0-relative speedup and 51.07% efficiency at 256 cores; weak efficiency is 57.37%. V3 avoids V2’s accumulation penalty, while its 1.04% loop advantage over pure MPI has overlapping ranges. GPU loop speedups over CPU1 are 11.05–13.00×; end-to-end gains are smaller.

| Figure | Content | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | Serial N/D/K scaling | [PNG](analysis/rubric-202611/paper-figures/figure-1-serial.png) | [PDF](analysis/rubric-202611/paper-figures/figure-1-serial.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-1-serial.svg) |
| 2 | MPI strong scaling | [PNG](analysis/rubric-202611/paper-figures/figure-2-strong.png) | [PDF](analysis/rubric-202611/paper-figures/figure-2-strong.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-2-strong.svg) |
| 3 | MPI weak scaling | [PNG](analysis/rubric-202611/paper-figures/figure-3-weak.png) | [PDF](analysis/rubric-202611/paper-figures/figure-3-weak.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-3-weak.svg) |
| 4 | Communication and phase shares | [PNG](analysis/rubric-202611/paper-figures/figure-4-communication.png) | [PDF](analysis/rubric-202611/paper-figures/figure-4-communication.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-4-communication.svg) |
| 5 | Fixed-256-core MPI+OpenMP | [PNG](analysis/rubric-202611/paper-figures/figure-5-hybrid.png) | [PDF](analysis/rubric-202611/paper-figures/figure-5-hybrid.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-5-hybrid.svg) |
| 6 | Same-job CPU/GPU comparison | [PNG](analysis/rubric-202611/paper-figures/figure-6-gpu.png) | [PDF](analysis/rubric-202611/paper-figures/figure-6-gpu.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-6-gpu.svg) |

[Exact statistics](analysis/rubric-202611/verified-20261105/statistics.csv) · [Independent phase summaries](analysis/rubric-202611/verified-20261105/profiles.csv)

```sh
python3 scripts/reproduce_rubric.py --verify-only
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py \
  --from-tables analysis/rubric-202611/verified-20261105 \
  --output artifacts/report-figures-new
```

`--verify-only` requires the complete sealed local raw archive; do not reseal or edit measured snapshots. Aggregate-table redraw requires the local CSVs and is not a raw-evidence audit. Time, problem-size and numerical CPU-count axes are logarithmic; phase percentages and efficiency remain linear. See the report for full discussion. OpenAI Codex assisted with implementation and documentation.

<!-- LOCAL_ARCHIVE_END -->
