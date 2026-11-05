#!/usr/bin/env python3
"""Generate reviewable PBS jobs; never submits them or guesses site modules."""
import argparse
from pathlib import Path
import re

SUITES = ('serial', 'strong', 'weak', 'hybrid', 'communication', 'gpu')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cores-per-node', type=int, choices=(8, 16, 32, 64), required=True)
    p.add_argument('--cpu-queue', required=True)
    p.add_argument('--gpu-queue', required=True)
    p.add_argument('--walltime', default='08:00:00')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not all(re.fullmatch(r'[A-Za-z0-9_.-]+', q) for q in (a.cpu_queue, a.gpu_queue)):
        p.error('Invalid queue name')
    if not re.fullmatch(r'\d{2,3}:[0-5]\d:[0-5]\d', a.walltime):
        p.error('walltime must be HH:MM:SS (confirm queue limit first)')
    a.output.mkdir(parents=True, exist_ok=False)
    for suite in SUITES:
        gpu = suite == 'gpu'
        c = 8 if gpu else a.cores_per_node
        nodes = 1 if suite in ('serial', 'gpu') else 256 // c
        select = 'select=%d:ncpus=%d:mpiprocs=%d%s:mem=8gb' % (nodes, c, c, ':ngpus=1' if gpu else '')
        body = '''#!/bin/bash
#PBS -N km-{suite}
#PBS -q {queue}
#PBS -l {select}
#PBS -l place=scatter:excl
#PBS -l walltime={walltime}
#PBS -j oe
set -euo pipefail
cd "$PBS_O_WORKDIR"
# Set KMEANS_ENV_FILE in qsub -v. This file must load the verified compiler/MPI/CUDA modules.
: "${{KMEANS_ENV_FILE:?Provide an absolute path to your cluster environment setup file}}"
source "$KMEANS_ENV_FILE"
RUN="$PBS_O_WORKDIR/artifacts/rubric-202611/{suite}.${{PBS_JOBID}}"
mkdir -p "$RUN"
cp "$0" "$RUN/job.pbs"
exec > >(tee "$RUN/job.stdout") 2>&1
# Stage before building: simultaneous jobs must never link into a shared build/.
python3 hpc/rubric_stage.py --output "$RUN/source"
cd "$RUN/source"
python3 hpc/rubric_probe.py --cores-per-node {c} --output "$RUN/probe" {gpu_flag}
make all {build_cuda}
python3 hpc/rubric_preflight.py --allocation "$RUN/probe/allocation.json" {gpu_flag} {full_flag}
python3 scripts/rubric_campaign.py --suite {suite} --cores-per-node {c} --allocation "$RUN/probe/allocation.json" --output "$RUN/measurements"
'''.format(suite=suite, queue=a.gpu_queue if gpu else a.cpu_queue, select=select,
           walltime=a.walltime, c=c, gpu_flag='--gpu' if gpu else '',
           build_cuda='cuda CUDA_HOME="${CUDA_HOME:?Set CUDA_HOME in environment file}" CUDA_ARCH="${CUDA_ARCH:?Set CUDA_ARCH from device probe}"' if gpu else '',
           full_flag='--require-256' if nodes * c >= 256 else '')
        (a.output / (suite + '.pbs')).write_text(body)
    print('Generated six PBS jobs. Review queue limits/modules before qsub; no job submitted.')


if __name__ == '__main__':
    main()
