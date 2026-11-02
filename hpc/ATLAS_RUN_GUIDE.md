# Atlas experiments

This directory contains PBS entry points, CPU affinity tools and package preparation.
Archived measurements and original source snapshots are not included in this code-only
snapshot; they are available in the full repository.

## Recheck the recorded experiments locally

From the repository root, using Python 3.8+ and its standard library:

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
```

The second command audits all 125 formal measurements, recalculates statistics and
checks numerical results and recorded placement evidence. It writes copies and
regenerated reports to `artifacts/atlas-audit/`; archived inputs are never changed.
Choose `--output artifacts/atlas-audit-2` for another run. The validation/pilot job
is included in integrity checks but is not counted in the 125 formal records or
rerun by the four formal audit scripts. No MPI installation or cluster login is
needed for this offline analysis.

## Prepare a new HPC run from the current checkout

```sh
python3 hpc/build-atlas-strategy-packages.py
```

This builds seven standalone archives under `artifacts/atlas-packages/`, with a
SHA-256 manifest for every included source file. Existing output directories are
rejected. To prepare only selected studies or use another output directory:

```sh
python3 hpc/build-atlas-strategy-packages.py --studies threads communication \
  --output artifacts/atlas-packages-new
```

These new packages contain the **current checkout**. For the exact source used
in the recorded jobs, use the archived source packages in the full repository. Do not
replace the archived packages with newly generated ones.

Transfer the desired archive to Atlas using your normal file transfer method.
On Atlas, extract it, enter its directory, and submit from that directory:

```sh
tar -xzf project3-atlas-strong.tar.gz
cd project3-atlas-strong
sha256sum -c source-manifest.sha256
qsub atlas-strong.pbs
```

The seven entry points are `atlas-smoke.pbs`, `atlas-validation.pbs`,
`atlas-strong.pbs`, `atlas-hybrid.pbs`, `atlas-threads.pbs` and
`atlas-communication.pbs`, plus `atlas-thread-scaling.pbs`. Historical snapshots do not all contain source
manifests; skip the checksum command if using an old package without one.

**Do not submit `qsub hpc/atlas-strong.pbs` directly from a checkout.** The PBS
scripts expect sources and helpers together in `PBS_O_WORKDIR`. The package
builder creates that flat working layout. Each study must have its own extracted
directory because jobs share build outputs within their working directory.
Do not run multiple study jobs from one checkout or extracted working directory.

## Recorded environment and workload

- CPU implementation: C++17, MPI + OpenMP; no GPU is used.
- Recorded modules: `miniconda/4.12`, `openmpi/4.1.2`, `gcc/9.2.0`.
- PBS settings: queue `parallel`, one node, 12 CPUs, 8 GB memory, 30-minute walltime.
  Confirm these modules/resources are available for a new run.
- Formal workload: N=1,000,000, D=32, K=32, seed=42, fixed 20 measured iterations,
  2 warmup iterations, 5 repeats per configuration. Input is generated in memory.
- Strong scaling: V0 baseline and V3 at P=1,2,3,4,6,12 with T=1 (35 records).
- Hybrid: V3 at P/T=1/12,2/6,3/4,4/3,6/2,12/1 (30 records).
- Thread strategy: V2/V3 at P/T=2/6,4/3,6/2 (30 records).
- Communication: V3 Allreduce/Reduce+Bcast at the same layouts (30 records).

New jobs write to `results/atlas-<study>.<PBS_JOBID>/`, except the simple smoke
job, which writes to PBS output. Download the result directory and PBS output;
save finished scheduler metadata with `qstat -xf JOBID` when available. Full
historical audits use `pbs-job.txt` as well as program output. Timings vary with
allocated CPUs, topology and load; compare matched configurations within a job.
Matching the procedure does not guarantee identical wall times.

## Tests

```sh
python3 -m unittest discover -s hpc -v
make test
```

HPC unit tests use recorded/constructed layouts and do not submit real PBS jobs.
For actual MPI integration tests, use `make test-mpi` on a suitable system or
submit the validation package. Historical run instructions remain in the original source snapshots
in the full repository; current commands are consolidated here. New packages flatten the helpers and include only the run
dependencies; run the repository's offline audits from the full checkout.

## Additional fixed-P experiment

See the [P=2 thread-scaling and separate phase-timing guide](THREAD_SCALING_GUIDE.md). Job `1028185.venus01` is complete and revalidated; no resubmission is needed. Its 50 ordinary measurements and 50 separate profiles are stored by job alongside the earlier 125 in the unified archive. The results and figures are available in the full repository.
