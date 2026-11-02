# Lloyd K-means with MPI + OpenMP

C++17 implementations of Lloyd K-means for comparing process and thread parallelism. Includes a serial reference, MPI/OpenMP variants, numerical tests, and benchmark scripts. The clustering algorithm is implemented directly without a clustering library.

| Variant | Local accumulation | Purpose |
| --- | --- | --- |
| V0 | Serial | Numerical reference and single-core baseline |
| V1 | Serial within each MPI process | Pure MPI baseline |
| V2 | OpenMP shared atomic updates | Measure contention |
| V3 | OpenMP thread-private buffers, then merge | Reduce synchronization inside the sample loop |

The parallel executable supports Allreduce and Reduce + Bcast for global centroid updates.

## Build

Requirements: a C++17 compiler and Make; MPI-3+ and OpenMP for the parallel executable; Python 3.8+ for tests and scripts. Build tests, benchmarks and offline audits use only the Python standard library. Optional report plotting uses Python 3.9+ and Matplotlib; see `requirements.txt`.

On Linux/HPC, load matching compiler and MPI modules, then run:

```sh
make all CXX=g++ MPICXX=mpicxx
```

Use `make serial` for a serial-only build. On macOS with Apple Clang, Homebrew Open MPI, and libomp:

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

Default flags: `-O3 -std=c++17 -Wall -Wextra -Wpedantic`. Use the same underlying compiler and floating-point options for both executables. Add `-B` when changing compilers or flags to force a rebuild.

## Quick start

Run the hand-checkable example:

```sh
./build/kmeans_serial --input examples/tiny.txt --k 2 \
  --init-indices 0,2 --iterations 1 --dump --trace
```

Expected final centroids: `[0, 1, 10, 11]` (row-major), counts: `[2, 2]`, labels: `[0, 0, 1, 1]`, and SSE: `4`.

Run generated data with two MPI processes and two threads per process:

```sh
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 50
```

Use `--variant v1 --threads 1` for pure MPI, `--variant v2` for atomic accumulation, or `--comm reduce-bcast` for the alternative communication strategy. Each successful run writes one JSON object to stdout; errors go to stderr.

## Data and options

Synthetic data is determined by the seed and global sample indices, so changing the process count preserves the dataset within the same build environment. No download is needed. The generator uses 16 Gaussian groups, independently of the requested number of clusters `K`. `--skew` assigns 90% of samples to one generating group.

For external data, use a whitespace-separated text file with `N D` on the first line and exactly `N * D` finite coordinates afterward. Remove IDs and labels, and apply scaling consistently beforehand. File dimensions override `--n` and `--d`. Rank 0 reads the file and distributes it with Scatterv; the total number of coordinates must fit in `INT_MAX`.

| Option | Default / meaning |
| --- | --- |
| `--n`, `--d`, `--k` | `10000`, `8`, `16`; require `N,D > 0` and `1 <= K <= N` |
| `--seed` | `42`; data generation and initial sample selection |
| `--input FILE` | Prepared text dataset |
| `--init-indices 0,2,...` | `K` distinct global sample indices |
| `--variant` | Serial: `v0`; parallel: `v1`, `v2`, or `v3` (default) |
| `--comm` | `allreduce` (default) or `reduce-bcast` |
| `--threads` | `1`; V0 and V1 require one thread |
| `--mode` | `fixed` (default) or `converge` |
| `--iterations` | `50` in fixed mode; maximum `300` in convergence mode |
| `--tol` | `1e-6`; relative maximum centroid displacement |
| `--warmup` | `0`; warmup iterations followed by a reset to the initial state |
| `--skew` | Enable the skewed synthetic distribution |
| `--dump` | Include initial/final centroids and final labels |
| `--trace` | Per-iteration SSE, counts, and updated centroids |
| `--profile` | Accumulation, merge, reduction, update, and broadcast times |

Run either executable with `--help` for the CLI summary. `--dump` and `--trace` require both `N` and `K * D` to be at most `100000`.

Distances and sums use `double`; counts use 64-bit integers. Exact ties select the lowest cluster index; empty clusters retain their previous centroids. Final labels, counts, and SSE are recomputed using the final centroids. Compare floating-point results with tolerances. Gaussian generation can differ across math libraries; use `data_fingerprint` to check inputs.

## Tests

```sh
make test
make test-mpi
```

`make test` runs serial and experiment-tool tests, skipping MPI integration cases. `make test-mpi` also runs real MPI/OpenMP comparisons, including uneven partitions, processes without samples, both communication strategies, and distributed error handling.

To customize the launcher:

```sh
TEST_MPI=1 MPIEXEC=mpiexec MPIEXEC_FLAGS='--bind-to none' \
  python3 -m unittest discover -s tests -v
```

On HPC, run parallel tests and benchmarks inside a scheduler allocation with enough cores. `--threads` sets the team size; the program disables dynamic teams and checks the actual thread count.

## Benchmarks

Preview the workload, then run and summarize a strong-scaling experiment:

```sh
python3 scripts/benchmark.py --suite smoke --processes 1,2 --threads 2 \
  --n 10000 --d 8 --k 16 --iterations 5 --dry-run

python3 scripts/benchmark.py --suite strong --processes 1,2,4 --threads 1 \
  --n 100000 --d 32 --k 32 --repeats 5 --output results/strong.jsonl
python3 scripts/summarize.py results/strong.jsonl --output results/strong.csv
```

| Suite | Comparison |
| --- | --- |
| `serial` | V0 only |
| `smoke` | V0–V3, plus both communication strategies for V3 |
| `strong` | Fixed problem size, varying processes, with a V0 baseline |
| `weak` | Fixed samples per process: total `N = --n * P` |
| `hybrid` | Fixed `--total-cores`; set `T = total_cores / P` for valid process counts |
| `threads` | V2 versus V3 with the same process/thread configuration |
| `communication` | Allreduce versus Reduce + Bcast for V3 |
| `sensitivity` | Vary one of N, D, or K at a time |

Defaults: 50 measured iterations, 2 warmup iterations, and 5 repetitions per configuration. Configuration order is shuffled within each repetition. `--launcher` accepts a tokenized command with `{p}` and `{t}` placeholders; no shell is used.

`--serial-launcher` sets an optional command prefix for V0, such as `taskset --cpu-list 40` on Linux. Choose the CPU from the scheduler allocation and verify affinity before timing. Both launchers are recorded in raw results and CSV grouping; older results without a serial launcher remain readable.

For example, with Open MPI and an appropriate core allocation:

```sh
export OMP_PLACES=cores
export OMP_PROC_BIND=close
python3 scripts/benchmark.py --suite communication --processes 1,2 --threads 2 \
  --launcher 'mpiexec -n {p} --map-by slot:PE={t} --bind-to core --report-bindings' \
  --output results/communication.jsonl
```

Check the launcher's binding report and record the allocation. Environment variables alone do not establish affinity. Avoid oversubscription for performance measurements. Scheduler and module setup depend on the cluster.

Raw JSONL and stderr logs are saved separately. CSV summaries report median/minimum/maximum kernel times, repetition counts, and SSE ranges. Existing output files are never overwritten; overlapping measurements are rejected.

## Timing and reproducibility

- `kernel_seconds` measures Lloyd iterations after warmup/reset and a starting barrier, taking the maximum elapsed time across processes.
- Data preparation, initialization, warmup, and final evaluation have separate timers. `total_seconds` starts after MPI initialization and ends after final evaluation; `launch_seconds` measures the external command.
- `--trace` and `--profile` add diagnostic work and are rejected by the benchmark summary. Separate phase maxima cannot be added to reconstruct total time.
- Strong-scaling speedup is `t_serial / t_parallel`; efficiency is `speedup / (P * T)`. Weak-scaling efficiency compares `P=1` and `P>1` with fixed samples and threads per process. Use matching workloads and environments.

Benchmark records include hostnames, executable paths, launch commands, and job IDs. New results, external datasets, local notes, credentials, caches, and build outputs are excluded by `.gitignore`; the retained evidence under `benchmarks/atlas/` is explicitly included.

## Recorded Atlas experiments

The repository includes five completed Atlas CPU studies with **175 ordinary measurements** and **50 separate diagnostic profiles**, plus the validation/pilot evidence. The formal workload uses N=1,000,000, D=32, K=32, seed=42, **20 measured iterations**, 2 warmup iterations and 5 repeats/configuration; these settings differ from the generic defaults above.

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
python3 hpc/build-atlas-strategy-packages.py
```

The first two commands verify archived evidence and regenerate analyses locally without MPI or an HPC login. The third creates standalone packages for new HPC runs. See [HPC instructions](hpc/ATLAS_RUN_GUIDE.md) and [the evidence index](benchmarks/atlas/EXPERIMENT_INDEX.md). Archives preserve the source versions used for the measured jobs. New packages use the current checkout. Results retain original hostnames, usernames and paths.

## New fixed-P thread-scaling study

The new [P=2 thread-scaling guide](hpc/THREAD_SCALING_GUIDE.md) prepares one independent CPU job at T=1,2,3,4,6 for V2/V3: 50 ordinary measurements plus 50 separate diagnostic profiles. The earlier four studies need no rerun. Current `--profile` output retains each rank's kernel and phase times; analysis uses all phases from the maximum-kernel rank. Job `1028185.venus01` is now archived and revalidated: 50 timing measurements, 50 separate profiles and 20 small-data preflights. See the [evidence manifest](benchmarks/atlas/manifest.json) and [supplementary analysis](analysis/atlas/THREAD_SCALING.md). There are now **175 ordinary performance measurements** (125 earlier + 50 new); profiles are counted separately. Run `python3 -B scripts/reproduce_atlas_thread_scaling.py` to audit a new copy.

## Report figures and tables

Seven report figures are included: the original five as PNG/PDF/SVG and the two fixed-P figures as PNG/SVG, together with exact CSV statistics and captions. See the [figure index](analysis/atlas/Figure/FIGURE_GUIDE.md), [overview](analysis/atlas/overview.png) and [report results](analysis/atlas/report_results.md). To regenerate them in a new directory after installing the optional dependencies:

```sh
python3 -m pip install -r requirements.txt
python3 scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

Only rendering needs Matplotlib. `--tables-only` derives statistics and all three documentation language editions with the standard library. Whiskers show observed ranges, not confidence intervals; comparisons stay within each job and use explicitly named baselines.

## Repository layout

```text
src/          C++ algorithm, data generation, MPI runtime, JSON output
scripts/      Benchmark runner and CSV summary
tests/       Numerical and experiment-tool tests
examples/     Small input with a hand-computed expected result
hpc/          PBS scripts, placement tools and standalone package builder
benchmarks/   Original Atlas results, source snapshots and audit evidence
analysis/     Report figures, exact tables, captions and reproduction guide
Makefile      Serial/parallel builds and tests
```

OpenAI Codex assisted with the implementation, tests, and documentation. Recorded Atlas results are included with their original evidence; new performance claims require measurements on the target system.
