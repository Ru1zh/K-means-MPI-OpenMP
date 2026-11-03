#!/usr/bin/env python3
"""Linux/PBS/Open MPI placement inventory, rank wrapper and strict verifier."""
import argparse
import json
import os
import socket
import subprocess
from pathlib import Path


def host():
    return socket.gethostname().split('.')[0]


def inventory():
    if not hasattr(os, 'sched_getaffinity'):
        raise RuntimeError('Linux sched_getaffinity is required on the cluster')
    cpus, ids = [], []
    seen = set()
    for cpu in sorted(os.sched_getaffinity(0)):
        topology = Path('/sys/devices/system/cpu/cpu%d/topology' % cpu)
        key = ':'.join((topology / name).read_text().strip()
                       for name in ('physical_package_id', 'core_id'))
        if key not in seen:  # Never count two SMT siblings as two physical cores.
            seen.add(key)
            cpus.append(cpu)
            ids.append(key)
    topology = subprocess.run(["lscpu", "--json"], text=True, capture_output=True, check=True)
    return dict(host=host(), cpus=cpus, core_ids=ids, topology=json.loads(topology.stdout),
                allowed_cpus=sorted(os.sched_getaffinity(0)))


def verify_placement(records, layout, p, t):
    if len(records) != p or sorted(r['rank'] for r in records) != list(range(p)):
        raise ValueError('Missing/duplicate rank placement records')
    occupied = set()
    for record in records:
        machine = record['host'].split('.')[0]
        allowed = layout['hosts'][machine]
        core_ids = dict(zip(allowed['cpus'], allowed['core_ids']))
        if len(core_ids) != len(allowed['cpus']) or len(set(core_ids.values())) != len(core_ids):
            raise ValueError('Allocation contains duplicate CPUs or SMT siblings')
        if len(record['threads']) != t:
            raise ValueError('Wrong actual thread count')
        for thread in record['threads']:
            cpu = thread['cpu']
            if thread['mask'] != [cpu] or cpu not in core_ids:
                raise ValueError('Thread is not pinned to one allocated physical core')
            identity = machine, core_ids[cpu]
            if identity in occupied:
                raise ValueError('Overlapping rank/thread physical cores')
            occupied.add(identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--allocation', type=Path)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    a = parser.parse_args()
    if a.inventory:
        print(json.dumps(inventory()))
        return
    layout = json.loads(a.allocation.read_text())
    cpus = layout['hosts'][host()]['cpus']
    local_rank = int(os.environ.get('OMPI_COMM_WORLD_LOCAL_RANK', '0'))
    chosen = cpus[local_rank * a.threads:(local_rank + 1) * a.threads]
    if a.threads < 1 or len(chosen) != a.threads:
        raise RuntimeError('Insufficient allocated cores for local ranks/threads')
    os.sched_setaffinity(0, chosen)
    for name in ('GOMP_CPU_AFFINITY', 'KMP_AFFINITY'):
        os.environ.pop(name, None)
    os.environ.update(OMP_PLACES=','.join('{%d}' % c for c in chosen),
                      OMP_PROC_BIND='true', OMP_DYNAMIC='FALSE',
                      OMP_NUM_THREADS=str(a.threads),
                      KMEANS_BINDING_NOTE='rubric-explicit-physical-cores')
    command = a.command[1:] if a.command[:1] == ['--'] else a.command
    os.execvp(command[0], command)


if __name__ == '__main__':
    main()
