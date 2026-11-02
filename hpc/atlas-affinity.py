#!/usr/bin/env python3
"""Record Linux OS CPU IDs and check single-node, one-thread MPI placement."""
import argparse
import json
import os
from pathlib import Path
import socket


def snapshot(expected_cores):
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) != expected_cores:
        raise ValueError("Expected a PBS-restricted %d-CPU affinity mask; got %r" %
                         (expected_cores, cpus))
    topology = {}
    for cpu in cpus:
        root = Path('/sys/devices/system/cpu/cpu%d/topology' % cpu)
        topology[str(cpu)] = {
            'socket': int((root / 'physical_package_id').read_text()),
            'core': int((root / 'core_id').read_text()),
        }
    if len({(v['socket'], v['core']) for v in topology.values()}) != expected_cores:
        raise ValueError('Allocation includes sibling hardware threads; review physical core accounting')
    return dict(host=socket.gethostname(), allowed_cpus=cpus, topology=topology,
                job_id=os.environ.get('PBS_JOBID', 'unset'))


def rank_record():
    return dict(rank=int(os.environ['OMPI_COMM_WORLD_RANK']),
                host=socket.gethostname(), cpus=sorted(os.sched_getaffinity(0)))


def verify(allocation, audits):
    allowed = set(allocation['allowed_cpus'])
    if not audits or 1 not in audits:
        raise ValueError('The single-rank baseline audit is required')
    baseline = None
    verified = {}
    for p, records in sorted(audits.items()):
        if len(records) != p or {r['rank'] for r in records} != set(range(p)):
            raise ValueError('Incomplete/duplicate rank records for P=%d' % p)
        used = []
        for record in records:
            if record['host'] != allocation['host']:
                raise ValueError('Expected a single-node run')
            cpus = record['cpus']
            if len(cpus) != 1 or not set(cpus) <= allowed:
                raise ValueError('Rank must use exactly one allocated OS CPU: %r' % record)
            used.extend(cpus)
            if record['rank'] == 0:
                if baseline is None:
                    baseline = cpus[0]
                elif baseline != cpus[0]:
                    raise ValueError('Rank 0 changed CPU across process counts')
        if len(set(used)) != p:
            raise ValueError('Ranks overlap on an OS CPU for P=%d' % p)
        verified[str(p)] = sorted(records, key=lambda r: r['rank'])
    return dict(baseline_cpu=baseline, allowed_cpus=sorted(allowed), audits=verified,
                note='Preflight OS CPU affinity; repeated launches also retain MPI binding reports')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['snapshot', 'rank', 'verify'])
    parser.add_argument('--expected-cores', type=int, default=12)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--processes', default='1,2,3,4,6,12')
    args = parser.parse_args()
    if args.mode == 'snapshot':
        result = snapshot(args.expected_cores)
    elif args.mode == 'rank':
        result = rank_record()
    else:
        if args.directory is None:
            parser.error('--directory is required for verify')
        allocation = json.loads((args.directory / 'allocation.json').read_text())
        audits = {}
        for p in map(int, args.processes.split(',')):
            path = args.directory / ('affinity-p%d.jsonl' % p)
            audits[p] = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        result = verify(allocation, audits)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
