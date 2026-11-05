# November rubric campaign

[中文](RUBRIC_GUIDE.zh-CN.md) · [한국어](RUBRIC_GUIDE.ko.md)

All six studies completed on Vanda and passed local verification on 5 November 2026: **275 ordinary records plus 75 separate profiles**. The campaign includes serial N/D/K sweeps, 256-core pure MPI strong/weak scaling, fixed-resource MPI+OpenMP, communication and a single-GPU CUDA comparison. See the [verified results](analysis/rubric-202611/RESULTS.md).

Recorded Vanda hosts use Intel Xeon Platinum 8452Y processors (72 exposed CPUs, two sockets, 36 cores/socket, one thread/core, two NUMA nodes). CPU studies use 64 actual cores/node, up to four nodes. PBS normalizes CPU memory to 444 GB/node and the GPU allocation to 36 CPUs/240 GB/one A40; the GPU comparisons actively use CPU1, CPU8 or GPU1. Builds use GCC 11.3.0, Open MPI 4.1.8 and CUDA 12.4.131 (sm_86). These observed values supersede the planning examples below.

## Algorithm and scoring coverage

Each Lloyd iteration assigns each point to its nearest centroid, accumulates per-cluster coordinate sums/counts, globally reduces these sufficient statistics, and updates the centroids. Ties select the smallest cluster index; empty clusters keep their previous centroid. Fixed iteration count I gives O(I N K D) distance work and O(KD) global statistics per rank. Data are partitioned by global sample index, including uneven/empty partitions; the seeded generator is independent of rank count.

V0 is the true serial baseline. V1 performs serial local work plus MPI. V2 uses OpenMP atomic accumulation; V3 uses padded thread-private statistics followed by a local merge. V4 keeps points resident on one GPU, computes distances and block-private statistics in a CUDA kernel, then reduces the block tiles in a second kernel. FP64 statistics are copied to the host for the existing MPI reduction/centroid update, and updated centroids return to the GPU each iteration. V4 currently accepts **P=1 and one host thread only**. This is single-GPU testing alongside the multi-node MPI+OpenMP study; it is not multi-GPU scaling.

| Rubric | Evidence to produce |
|---|---|
| Algorithm, 5 | Lloyd steps, complexity, ownership, synchronization dependency |
| Serial scaling, 5 | V0 one-factor N/D/K sweeps and seconds/(I N K D) |
| MPI, 10 | V1 to 256 actual cores; strong/weak scaling, speedup, efficiency, communication |
| MPI+X, 10 | V2/V3 at 256 total cores plus real CUDA execution on at least one GPU |
| Discussion, 5 | Measured bottlenecks, choices, host/device transfers, limitations |

Synthetic data are sufficient; no Kaggle download is required. The fixed generator has 16 generating groups independently of solver K; a K sweep changes computational work and model capacity, not the data-generating process.

## Exact matrix

All formal configurations use FP64, seed 42, 20 timed iterations, 2 warmup iterations and 5 repeats. Warmup is followed by restoration of the original centroids. Correctness and phase profiling are separate from ordinary timing.

| Suite | Ordinary configurations | Independent profile configurations | Ordinary / profile records |
|---|---:|---:|---:|
| serial | V0: N={100k,200k,500k,1m,2m,4m}; D={8,16,32,64,128}; K={8,16,32,64,128}; base N=1m,D=K=32; deduplicate base | none | 70 / 0 |
| strong | V0 and V1/P={1,2,4,8,16,32,64,128,256}, N=4m,D=K=32 | V1/P={1,C,256} | 50 / 15 |
| weak | V1 at the same P list, N=100k×P,D=K=32 | P={1,C,256} | 45 / 15 |
| hybrid | V2 and V3 at P×T={256×1,128×2,64×4,32×8}, plus V1/256×1; N=4m | V2/V3 at 32×8 | 45 / 10 |
| communication | V1/P={C,256}, Allreduce vs Reduce+Bcast; N=4m | all four configurations | 20 / 20 |
| gpu | N={100k,1m,4m},D=K=32; V0/CPU1, V3/CPU8, V4/GPU1 in one job | three V4 sizes | 45 / 15 |
| Total | 55 | 15 | **275 / 75** |

C is a verified power of two in {8,16,32,64}. Choose the largest permitted value no greater than 64 and the available physical cores per node. Request 256/C distinct nodes for multi-node studies. Do not equate the entire KVM-visible topology with allocated cores. Serial/GPU jobs use one node; GPU jobs request 8 CPU cores and one GPU. `--dry-run` enumerates each unique configuration once, not all five repeats:

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 scripts/benchmark.py --suite sensitivity --variant v0 --processes 1 --threads 1 --dry-run
```

## Cluster preparation

First use an allocated CPU/GPU pilot to inspect queue walltime/node limits, `qstat -Qf`, `lscpu`, `mpiexec --version`, `mpicxx --showme`, `nvcc --version` and `nvidia-smi -q`. The new launcher explicitly targets **PBS + Open MPI + Linux**, with a shared project directory and Python available at the same path on every node. `PBS_NODEFILE` must expose at least C slots per node. If the site uses a different MPI launcher/PBS nodefile convention, adapt it and rerun placement preflight before collecting data.

Create an environment script outside the tracked source tree, for example `/absolute/path/kmeans-env.sh`, which loads the verified compiler/MPI/CUDA modules. For GPU jobs set `CUDA_HOME` and `CUDA_ARCH` (e.g. 80 only if the allocated device is compute capability 8.0). V4 requires capability >=6.0 and a compatible nvcc/host compiler; CUDA 13 may no longer compile older architectures. Confirm the toolkit-supported target instead of copying an example value. CPU jobs require a working C++17/OpenMP compiler and Open MPI. Allow multiple hours, subject to queue limits: confirm the walltime needed for each complete suite.

```sh
make all CXX=g++ MPICXX=mpicxx
# Optional, only on a CUDA-equipped environment:
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
# Replace queue names with the pilot's actual results before running this:
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue ACTUAL_CPU_QUEUE --gpu-queue ACTUAL_GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
```

The generator writes six reviewable PBS scripts and never submits them. From the repository root, review them, then submit one job per suite:

```sh
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/serial.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/strong.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/weak.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/hybrid.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/communication.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/gpu.pbs
```

Jobs request exclusive distinct nodes (`place=scatter:excl`). Each job records scheduler information and per-node physical-core inventory, builds, performs numerical/placement preflight, and only then runs the shuffled five-repeat schedule. Open MPI rank binding is disabled in favor of the explicit wrapper: it pins each rank to its own physical-core subset and sets singleton `OMP_PLACES`. The program observes the actual worker CPU/mask; preflight and every formal sample reject missing ranks, thread-count mismatch, SMT siblings, overlapping cores or wrong node packing. The 256-core preflight runs 256 actual single-thread ranks and all hybrid layouts. GPU failures/OOM/no device terminate execution; there is no CPU fallback. Keep the `.pbs` and scheduler `.o*` output with each run.

Outputs: `artifacts/rubric-202611/<suite>.<job-id>/probe/` and `measurements/`. Probe includes scheduler/toolchain logs, topology, allocation, numerical records, validated binary/source hashes and GPU device records when applicable. Measurements include ordinary `raw.jsonl`, independent `profiles.jsonl`, source manifest, allocation and every command's stdout/stderr. Runs cannot overwrite an existing directory. Failed/incomplete jobs are retained for diagnosis but do not count as complete formal comparisons; rerun the entire suite into a new job directory. A source or binary change invalidates preflight; all six accepted jobs must use one source snapshot.

## Validation and timing

```sh
make test
make test-mpi
# GPU allocation only; skipped tests on a laptop are not GPU acceptance:
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
```

CPU tests/preflights cover ties, empty clusters, uneven data, empty ranks, both collectives and cross-node execution. GPU checks compare labels/counts/centroids with V0 on small data; centroid tolerances are rtol=1e-8, atol=1e-10. Full GPU sizes compare fingerprints, initial indices, counts and final SSE with V0 (SSE relative tolerance 1e-8); CPU matched-workload SSE tolerance is 1e-10. CUDA events measure assignment, tile merge and transfers only in independent profile runs. CPU timing boundaries synchronize the device. See [NVIDIA timing guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#timing).

`kernel_seconds` is the maximum rank's complete timed loop, including local work, transfers, communication and host centroid updates. `total_seconds` includes generation, initialization, GPU allocation/upload, warmup, the loop and final evaluation, but excludes MPI initialization, process launch and teardown. `launch_seconds` additionally records external process-launch elapsed time. Initial upload has a separate CPU-wall-time field. Per-iteration H2D/D2H diagnostic fields are CUDA event intervals. Diagnostics add instrumentation and must not be mixed into ordinary statistics. CPU phase plots retain one real sample's complete critical-rank phase vector; MPI time includes waiting and is not pure network latency.

Strong scaling uses both same-job V0 and V1/P=1 baselines, with E=S/P. Weak scaling uses E=T1/TP and throughput speedup P*T1/TP; its small P=1 problem is not the serial baseline for the largest N. Hybrid comparisons fix 256 total cores and use the same-job V1/256 reference. All error ranges are observed min–max over five repeats.

## Archive, reproduce, deliver

Each PBS job now stages its own source/acceptance-test snapshot in `<job>/source/` before building, avoiding shared-build races. Per-sample checks verify source and executable hashes before and after execution. Preflight and measurement completion manifests require all invocation/probe logs; offline auditing also compares staged and delivered sources. Preserve `source/`, `job.pbs` and `job.stdout` alongside `probe/` and `measurements/`.

Copy the six **complete job directories**, each retaining both `probe/` and `measurements/`, into `benchmarks/rubric-202611/runs/`. Preserve PBS scripts/stdout there as well. Keep only one accepted full job per suite in the formal archive; put failed/alternative jobs outside it. Then:

```sh
python3 scripts/reproduce_rubric.py --status
python3 scripts/reproduce_rubric.py --seal --verify-only
python3 scripts/reproduce_rubric.py --verify-only
python3 scripts/reproduce_rubric.py --tables-only --output artifacts/rubric-tables
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
python3 scripts/package_rubric.py --output artifacts/kmeans-rubric-source.zip
python3 scripts/package_rubric.py --verify artifacts/kmeans-rubric-source.zip
```

`--seal` audits all 350 records before exclusively creating evidence checksums. Later verification rejects missing/altered/additional evidence. The package has its own file hashes; extract it, build, and run the same offline audit/regeneration commands. Plotting alone needs Matplotlib; numerical tools/audits use Python's standard library. Generated new figures go into the requested fresh output directory; retain reviewed PNG/PDF/SVG, exact CSV and captions under `analysis/rubric-202611/` when measurements exist. See [figure guide](analysis/rubric-202611/FIGURE_GUIDE.md).

## Report blueprint and protected material

Use results order: serial size scaling → MPI strong → MPI weak → communication → MPI+OpenMP → GPU. Explain data layout, sufficient-statistic communication (KD doubles + K 64-bit counts per reduction, excluding protocol overhead), atomic contention vs private-buffer memory/merge, node boundaries, and host/device costs. Synthetic results support performance conclusions, not claims about an external dataset. Do not claim speedups or 256-core/GPU completion until the new logs pass audit.

Add the new CPU/GPU environment in a separate paragraph sourced from new probes. Keep existing manual page breaks, three-line tables, References on its own page and the unchanged AI declaration on the final separate page:

> We used [GPT-6.1 sol] to [help code, create tables and beautify assignment]. We are responsible for the content and quality of the submitted work.

The report uses the locally verified Vanda results. The online paper and final delivery PDF are updated together.

The six-study campaign is complete and locally verified. The report now uses these Vanda results; the remaining submission steps are review and packaging. The assignment deadline is 13 November 2026. Multi-GPU scaling and additional GPU optimization variants remain outside this campaign.
