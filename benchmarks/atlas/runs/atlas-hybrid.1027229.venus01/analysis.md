# Atlas MPI+OpenMP layout results with 12 fixed cores

[English](analysis.md) | [简体中文](analysis.zh-CN.md) | [한국어](analysis.ko.md)

Job `1027229.venus01`, 2026-10-24, node `cnode-33-43-45`. This analysis compares only the six V3 layouts using 12 fixed cores within the same job.

## Verification findings

- Both PBS and script exit statuses are 0. All 30 formal records are present, with 5 repeats per configuration and all six layouts included in every batch.
- The median, minimum and maximum in CSV match the raw JSONL for every group.
- Every run has data fingerprint `7fcf2e8b0cc1a222`, identical initial centroid IDs and identical final cluster counts, summing to 1000000.
- All formal runs have SSE 73440053.24011984. Large-input V0 was not remeasured in this round; small-data results for the six layouts were separately compared with the serial reference, with identical labels/counts and centroids and SSE within the specified tolerances. Specific errors are saved in analysis.audit.json.
- Checked 140 rank CPU masks and 360 OpenMP thread-probe records for the 30 formal runs; all match the placement plan, without overlap, and cover all 12 allocated cores. Raw records are individually linked to actual launch directories through placement_id.
- The MPI executable SHA-256 for each formal run matches binaries.sha256. The probe's `_OPENMP` macro is 201511; this field identifies the compile-time OpenMP standard version, not the runtime library release version.

## Hardware, placement and workload

AMD EPYC 7R13, KVM virtual machine; 96 CPUs, 2 sockets, 4 NUMA nodes and 1 hardware thread per core are visible. The job requested 12 cores and 8GB, with a walltime of 5 minutes 43 seconds.

The actual allocation is OS CPUs `36–47`, all on socket 0, NUMA node 1. Every layout uses the same set of 12 distinct physical cores, with T cores per rank and all cross_socket_ranks empty. Thus the previously anticipated case of “1×12 and 3×4 spanning sockets” did not occur in this allocation.

GCC 9.2.0, Open MPI 4.1.2, Python 3.8.5; the algorithm is compiled with `-O3 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp -DKM_MPI`. V3, Allreduce, N=1000000, D=32, K=32 and seed=42 are fixed; initial centroids are restored after 2 warmup iterations, followed by 20 timed iterations. Each configuration has 5 repeats, with randomized ordering in each batch.

At each launch, the Python wrapper sets the rank's OS CPU mask, explicit per-core OMP_PLACES and OMP_PROC_BIND=close. An independent OpenMP probe first checks that each thread uses one specified core, then K-means runs. MPI's `--bind-to none` means only that the MPI launcher adds no further binding; it does not mean the wrapper leaves the process unbound. Thread records come from the independent probe, while the algorithm separately checks team size; these are not real-time affinity samples inside the algorithm's timing loop.

## Layout comparison within the same job

P is the number of MPI processes and T the threads per process; every configuration has P×T=12. Times are medians of kernel_seconds, excluding compilation, data preparation, initialization, warmup, final evaluation and external launch overhead. Minimum–maximum ranges come from 5 measured runs, not confidence intervals.

| P×T | Median kernel time/s | Minimum–maximum/s | 12×1 time/this layout's time | Time change relative to 12×1 |
|---|---:|---:|---:|---:|
| 1×12 | 0.954366 | 0.921613–1.019229 | 1.0023× | -0.23% |
| 2×6 | 0.979631 | 0.970431–0.997293 | 0.9764× | +2.42% |
| 3×4 | 0.952300 | 0.916632–0.974131 | 1.0044× | -0.44% |
| 4×3 | 0.980928 | 0.916852–0.994980 | 0.9751× | +2.55% |
| 6×2 | 0.984793 | 0.900327–0.988295 | 0.9713× | +2.96% |
| 12×1 | 0.956526 | 0.946156–1.003424 | 1.0000× | +0.00% |

The lowest observed median is 3×4, about 0.44% below 12×1; 1×12 is about 0.23% below 12×1. All medians lie between 0.952300 and 0.984793 seconds, with a maximum/minimum median ratio of about 1.0341.

The measured minimum–maximum ranges of all six groups share a common intersection, approximately 0.970431–0.974131 seconds. This is not a formal significance test, but with only 5 repeats and very small median differences, the evidence is insufficient to identify 3×4 as a consistently optimal layout. A more appropriate conclusion is that V3's six process/thread layouts perform similarly for this input on 12 cores allocated within the same NUMA node.

These ratios describe placement differences at fixed resources, not strong-scaling speedups as core counts increase; they should not be divided by 12 to obtain parallel efficiency.

## Relationship to the preceding strong-scaling job

The preceding job 1027222 ran on cnode-33-43-39 and used two sockets for 12 processes; the current node is cnode-33-43-45, with all 12 cores on one socket/NUMA node. Binding and launch methods also differ between the jobs. The earlier V0=11.232365 seconds cannot be directly reused to calculate a “serial speedup for this job,” and small timing differences between the jobs cannot be attributed to hybrid parallelism or NUMA optimization.

## Suggested wording for the report

On one AMD EPYC 7R13 node of Atlas, total cores were fixed at 12 while comparing six V3 MPI/OpenMP layouts: 1×12, 2×6, 3×4, 4×3, 6×2 and 12×1. All configurations used the same 12 cores on socket 0, NUMA node 1. With N=1000000, D=32 and K=32 fixed, 2 warmup iterations and 20 timed iterations were used, with 5 repeats per configuration. Median kernel times across the six layouts were 0.952–0.985 seconds; 3×4 had the lowest observed median, reducing time by about 0.44% relative to 12×1. Because repeated-run ranges overlap, a stable advantage for this layout has not been established. All runs had identical data and initial centroids, identical final cluster counts and SSE, and small-data comparisons for all six layouts also passed validation against the serial reference.

## Choice of subsequent comparisons

The prepared thread-strategy and communication-strategy packages default to 2×6, 4×3 and 6×2, which remain suitable: they cover different thread and MPI process counts, and showed no clear performance disadvantage in this V3 experiment. Retaining multiple representative layouts is more suitable for strategy comparisons than selecting a single “best” layout based only on the observed 0.44% difference.

Run V2/V3 next to examine atomic updates versus private buffers, then run V3 Allreduce/Reduce+Bcast. Each new job should still record placement according to its actual allocation; any change in cross-socket conditions must be stated in the corresponding results. These conclusions apply only to the measured single node, one input size, Allreduce and V3; they do not establish similar performance for other strategies or multiple nodes.

Original files remain unchanged. Analysis can be recalculated with analyze.py in the same directory; per-file hashes and complete derived statistics are in analysis.audit.json.
