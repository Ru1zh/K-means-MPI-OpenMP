# Fixed P=2 thread scaling

One CPU job compares V2 and V3 at P=2 and T=1,2,3,4,6 with Allreduce: 50 ordinary timings, 50 separate diagnostic profiles and 20 small-data preflights. Archived results and evidence are not included in this code-only snapshot.

## Design

- N=1,000,000, D=32, K=32, seed=42; 20 measured iterations after 2 warmup iterations.
- Request 12 cores. Each rank keeps the same six socket-local cores; only the nested OpenMP places change with T, so the active core count is 2T.
- Five repetitions per configuration, with randomized order within each repetition.
- Generate a fresh full-size V0 reference and 20 small-data preflights covering both modes, variants and thread counts. V0 is not a repeated performance baseline.
- Speedup = median(T=1) / median(T) for the same variant; thread efficiency = speedup / T.

## Run

```sh
python3 hpc/atlas-thread-scaling.py --dry-run
python3 hpc/build-atlas-strategy-packages.py --studies thread-scaling \
  --output artifacts/atlas-thread-scaling-package
```

Transfer the package to Atlas, extract it, verify `source-manifest.sha256`, then submit from a fresh directory:

```sh
qsub atlas-thread-scaling.pbs
```

## Analyze

```sh
python3 hpc/analyze-atlas-thread-scaling.py /path/to/atlas-thread-scaling.JOBID
```

Outputs are `thread-scaling-summary.csv`, `phase-summary.csv`, `analysis.audit.json` and `analysis.md`. A successful run has `status.txt` containing `exit_status=0` and passing checks in `analysis.audit.json`.

## Phase timing

`--profile` records each rank's kernel and five phase times. Each diagnostic sample uses all phases from the rank with the largest kernel time (smaller rank wins ties); the residual is that rank's kernel minus its phase sum. Legacy `phase_seconds` holds independent per-phase maxima and cannot be summed.

`accumulate` includes buffer clearing, distances, updates and the OpenMP barrier; V3's `thread_merge` is the subsequent merge. `mpi_reduce`, `centroid_update` and `control_bcast` cover the remaining phases. This shows whether accumulation or merge dominates, but does not isolate pure atomic waiting. Keep phase times separate from ordinary kernel times; independent phase medians need not sum to the kernel median.
