#!/usr/bin/env python3
"""Run inside a PBS allocation. Save scheduler/topology/toolchain evidence before jobs."""
import argparse
import collections
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def capture(command, output, required=True):
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=120)
    except FileNotFoundError as error:
        if required:
            raise
        output.write_text(str(error) + '\n')
        return ''
    output.write_text('$ ' + ' '.join(command) + '\n' + proc.stdout + '\n' + proc.stderr)
    if required and proc.returncode:
        raise RuntimeError('Resource probe failed: ' + ' '.join(command))
    return proc.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cores-per-node', type=int, choices=(8, 16, 32, 64), required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--gpu', action='store_true')
    a = p.parse_args()
    if not os.environ.get('PBS_JOBID') or not os.environ.get('PBS_NODEFILE'):
        p.error('Probe must run inside a PBS job, not on a login node')
    a.output.mkdir(parents=True, exist_ok=False)
    nodefile = Path(os.environ['PBS_NODEFILE']).read_text()
    (a.output / 'PBS_NODEFILE').write_text(nodefile)
    slots = collections.Counter(line.split('.')[0] for line in nodefile.splitlines() if line.strip())
    if not slots or any(count < a.cores_per_node for count in slots.values()):
        raise ValueError('PBS_NODEFILE has fewer allocated slots than C')
    capture(['qstat', '-f', os.environ['PBS_JOBID']], a.output / 'job.txt')
    capture(['qstat', '-Qf'], a.output / 'queues.txt', required=False)
    capture(['mpiexec', '--version'], a.output / 'mpi-launcher.txt')
    capture(['mpicxx', '--version'], a.output / 'host-compiler.txt')
    capture(['mpicxx', '--showme'], a.output / 'mpi-flags.txt')
    output = capture(['mpiexec', '--host', ','.join('%s:1' % h for h in slots),
                      '--map-by', 'ppr:1:node', '--bind-to', 'none', '-n', str(len(slots)),
                      sys.executable, str(ROOT / 'hpc/rubric_placement.py'), '--inventory'],
                     a.output / 'inventory.txt')
    inventories = [json.loads(line) for line in output.splitlines() if line.strip()]
    if {v['host'] for v in inventories} != set(slots) or len(inventories) != len(slots):
        raise ValueError('Did not observe every allocated node exactly once')
    hosts = {}
    for entry in inventories:
        if len(entry['cpus']) < a.cores_per_node:
            raise ValueError('Not enough distinct allowed physical cores on ' + entry['host'])
        hosts[entry['host']] = dict(cpus=entry['cpus'][:a.cores_per_node],
                                    core_ids=entry['core_ids'][:a.cores_per_node], inventory=entry)
    layout = dict(cores_per_node=a.cores_per_node, hosts=hosts,
                  job_id=os.environ['PBS_JOBID'], scheduler_slots=dict(slots))
    (a.output / 'allocation.json').write_text(json.dumps(layout, indent=2) + '\n')
    if a.gpu:
        capture(['nvidia-smi', '-q'], a.output / 'gpu.txt')
        capture(['nvcc', '--version'], a.output / 'nvcc.txt')
    print('Resource inventory saved; run preflight before formal measurements.')


if __name__ == '__main__':
    main()
