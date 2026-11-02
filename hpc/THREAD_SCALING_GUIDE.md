# Fixed P=2 thread scaling and separate phase timing

This is **one new CPU job**. The four archived studies and their 125 measurements remain valid; do not rerun them for this extension. No GPU or data download is required. Job `1028185.venus01` has completed and passed local revalidation: 50 ordinary measurements, 50 separate profiles and 20 small-data preflights. No resubmission is needed. See the [results](../analysis/atlas/THREAD_SCALING.md) and [evidence manifest](../benchmarks/atlas/manifest.json). Submission steps below are for future replication; recheck downloaded evidence with `python3 -B scripts/reproduce_atlas_thread_scaling.py`.

## Design

- Fix P=2 and compare V2/V3 at T=1,2,3,4,6 with Allreduce. Keep N=1,000,000, D=32, K=32, seed=42, 20 measured iterations and 2 warmup iterations.
- Request 12 cores for the whole job. Reserve the same six socket-local cores per rank throughout; only the nested active OpenMP places change with T. The used core count is 2T, not always 12. Allocations that cannot form two socket-local six-core groups fail before measuring.
- Five repetitions per configuration produce **50 ordinary timing records** (`timing.jsonl`) and **50 separate diagnostic records** (`profile.jsonl`). Configuration order is randomized within each repetition and saved in `study-plan.json`. All ordinary launches precede the separate profile block.
- Generate a fresh full-size V0 numerical reference, plus 20 small-data preflights covering both modes, variants and thread counts. V0 is not a repeated performance baseline. Check fingerprints, initial samples, counts and SSE; small cases also check labels and centroids.

The same-variant P=2,T=1 median is the thread-scaling baseline: speedup = median(T=1)/median(T), efficiency = speedup/T. Compare V2 and V3 within this new job. The old T=6 result provides context but is not a paired measurement from this allocation.

## Prepare and submit only the new job

From the repository root on your computer:

```sh
python3 hpc/atlas-thread-scaling.py --dry-run
python3 hpc/build-atlas-strategy-packages.py --studies thread-scaling \
  --output artifacts/atlas-thread-scaling-package
```

Transfer `artifacts/atlas-thread-scaling-package/project3-atlas-thread-scaling.tar.gz` to Atlas. In a new working directory on Atlas:

```sh
tar -xzf project3-atlas-thread-scaling.tar.gz
cd project3-atlas-thread-scaling
sha256sum -c source-manifest.sha256
qsub atlas-thread-scaling.pbs
```

The PBS script loads the recorded modules, builds current source, records environment and CPU topology, verifies placement for every launch, runs the study, and generates statistics plus English/Chinese/Korean analyses. It requests queue `parallel`, one node, 12 cores, 8 GB and 30 minutes. Use a separate extracted directory; do not submit from the repository's `hpc/` directory or share a build directory with another running job. A failed run must use a fresh submission/result directory.

## Retrieve and analyze

Download the **entire** `results/atlas-thread-scaling.<PBS_JOBID>/` directory, the PBS stdout/stderr file (`p3_tscale.o*`) and the exact source archive. Save scheduler metadata while available:

```sh
qstat -xf JOBID > results/atlas-thread-scaling.JOBID/pbs-job.txt
```

Replace both `JOBID` occurrences with the full job ID. A successful job has `status.txt` containing `exit_status=0` and `analysis.audit.json` with passing numerical, matrix and placement checks. Preserve failed logs for diagnosis. Do not add incomplete results to the archived 125 records.

After downloading, regenerate analysis locally with Python 3.8+ (standard library only):

```sh
python3 hpc/analyze-atlas-thread-scaling.py /path/to/atlas-thread-scaling.JOBID
```

Outputs are `thread-scaling-summary.csv`, `phase-summary.csv`, `analysis.audit.json` and `analysis.md` / `analysis.zh-CN.md` / `analysis.ko.md`. Raw inputs are unchanged; derived outputs can be regenerated.

## Interpret phase contributions

`--profile` adds `profile_ranks` (each rank's kernel and five phase times) and `profile_critical_rank`. Each diagnostic sample uses **all phases from the rank with the largest kernel time**, with the smaller rank winning ties. Residual is that rank's kernel minus its phase sum. Legacy top-level `phase_seconds` still contains independent per-phase maxima and cannot be summed.

`accumulate` includes clearing buffers, distance calculation, updates and the OpenMP barrier; V3's `thread_merge` measures the subsequent merge. `mpi_reduce`, `centroid_update` and `control_bcast` cover the other phases (Allreduce normally needs no control broadcast). This decomposition can show whether accumulation or merge dominates; it does **not** isolate pure atomic waiting or prove causality by subtraction. Do not combine profile phase times with ordinary kernel times. Independent medians of phases need not sum to the median kernel; min–max ranges are not confidence intervals. No existing report or figure is automatically changed.
