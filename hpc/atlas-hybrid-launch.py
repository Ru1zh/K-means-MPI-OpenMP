#!/usr/bin/env python3
"""Explicit Linux rank masks and separate OpenMP placement probes for Atlas."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

PAIRS = [(1, 12), (2, 6), (3, 4), (4, 3), (6, 2), (12, 1)]


def build_plan(allocation):
    topology = allocation['topology']
    cpus = sorted(allocation['allowed_cpus'], key=lambda c: (topology[str(c)]['socket'], topology[str(c)]['core'], c))
    if len(cpus) != 12 or len(set(cpus)) != 12:
        raise ValueError('Exactly 12 distinct allocated CPUs required')
    if len({(topology[str(c)]['socket'], topology[str(c)]['core']) for c in cpus}) != 12:
        raise ValueError('Allocation must contain 12 distinct physical cores')
    configurations = {}
    for p, t in PAIRS:
        ranks = [cpus[r*t:(r+1)*t] for r in range(p)]
        sockets = [sorted({topology[str(c)]['socket'] for c in rank}) for rank in ranks]
        configurations[str(p)] = dict(p=p, t=t, ranks=ranks, rank_sockets=sockets,
                                       cross_socket_ranks=[r for r, ss in enumerate(sockets) if len(ss) > 1])
    return dict(allocation=allocation, configurations=configurations)


def verify_threads(probe, expected):
    threads = probe['threads']
    if len(threads) != len(expected) or {r['tid'] for r in threads} != set(range(len(expected))):
        raise ValueError('Missing/duplicate OpenMP thread IDs')
    seen = []
    for thread in threads:
        cpus = thread['cpus']
        if len(cpus) != 1 or thread['current_cpu'] != cpus[0] or cpus[0] not in expected:
            raise ValueError('OpenMP thread is not bound to one planned CPU')
        seen.extend(cpus)
    if set(seen) != set(expected) or len(set(seen)) != len(expected):
        raise ValueError('OpenMP threads overlap or omit planned CPUs')


def verify_records(plan, p, t, records):
    config = plan['configurations'][str(p)]
    if config['t'] != t:
        raise ValueError('Process/thread configuration mismatch')
    if len(records) != p or {r['rank'] for r in records} != set(range(p)):
        raise ValueError('Missing/duplicate MPI ranks')
    used = []
    for record in records:
        expected = config['ranks'][record['rank']]
        if record['host'] != plan['allocation']['host']:
            raise ValueError('Unexpected compute host')
        if sorted(record['rank_cpus']) != sorted(expected) or record['p'] != p or record['t'] != t:
            raise ValueError('MPI rank CPU mask/configuration mismatch')
        if record['omp_places'] != ','.join('{%d}' % c for c in expected):
            raise ValueError('Explicit OpenMP places mismatch')
        verify_threads(record['thread_probe'], expected)
        used.extend(record['rank_cpus'])
    if len(used) != 12 or len(set(used)) != 12 or set(used) != set(plan['allocation']['allowed_cpus']):
        raise ValueError('Ranks overlap or fail to cover the 12-core allocation')
    return dict(p=p, t=t, placement_check='pass', cross_socket_ranks=config['cross_socket_ranks'])


def rank_launch(args):
    plan = json.loads(args.plan.read_text())
    rank = int(os.environ['OMPI_COMM_WORLD_RANK'])
    p = int(os.environ['OMPI_COMM_WORLD_SIZE'])
    config = plan['configurations'][str(args.p)]
    if p != args.p or config['t'] != args.t or not 0 <= rank < p:
        raise ValueError('MPI world/configuration mismatch')
    if socket.gethostname() != plan['allocation']['host']:
        raise ValueError('Unexpected host before setting CPU affinity')
    if not set(plan['allocation']['allowed_cpus']) <= set(os.sched_getaffinity(0)):
        raise ValueError('Launcher did not inherit the complete PBS CPU set')
    expected = config['ranks'][rank]
    os.sched_setaffinity(0, expected)
    actual = sorted(os.sched_getaffinity(0))
    if actual != sorted(expected):
        raise ValueError('Could not apply planned rank CPU mask')
    env = dict(os.environ, OMP_NUM_THREADS=str(args.t), OMP_DYNAMIC='FALSE',
               OMP_PLACES=','.join('{%d}' % c for c in expected), OMP_PROC_BIND='close')
    env.pop('GOMP_CPU_AFFINITY', None)
    env.pop('KMP_AFFINITY', None)
    probe = subprocess.run([str(args.probe), str(args.t)], env=env, text=True,
                           capture_output=True, timeout=30)
    if probe.stderr:
        print(probe.stderr, file=sys.stderr, end='')
    if probe.returncode:
        raise RuntimeError('OpenMP placement probe failed with status %d' % probe.returncode)
    threads = json.loads(probe.stdout)
    verify_threads(threads, expected)
    record = dict(rank=rank, p=p, t=args.t, host=socket.gethostname(), rank_cpus=actual,
                  omp_places=env['OMP_PLACES'], thread_probe=threads, command=args.command)
    (args.directory / ('rank-%d.json' % rank)).write_text(json.dumps(record) + '\n')
    os.execvpe(args.command[0], args.command, env)


def run(args):
    directory = args.output / ('launch-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    plan = json.loads(args.plan.read_text())
    if args.t != plan['configurations'][str(args.p)]['t']:
        raise ValueError('P*T must match the planned 12 cores')
    command = ['mpirun', '--hostfile', str(args.nodefile), '-n', str(args.p),
               '--bind-to', 'none', '--nooversubscribe', sys.executable, str(Path(__file__).resolve()),
               'rank', '--plan', str(args.plan), '--p', str(args.p), '--t', str(args.t),
               '--probe', str(args.probe), '--directory', str(directory), '--'] + args.command
    (directory / 'launch.json').write_text(json.dumps(dict(p=args.p, t=args.t, command=command,
                                                         algorithm_command=args.command)) + '\n')
    result = subprocess.run(command, text=True, capture_output=True, timeout=240)
    if result.stderr:
        print(result.stderr, file=sys.stderr, end='')
    if result.returncode:
        print(result.stdout, file=sys.stderr, end='')
        raise SystemExit(result.returncode)
    records = [json.loads((directory / ('rank-%d.json' % r)).read_text()) for r in range(args.p)]
    check = verify_records(plan, args.p, args.t, records)
    (directory / 'check.json').write_text(json.dumps(check) + '\n')
    measurement = json.loads(result.stdout)
    measurement.update(placement_id=directory.name, placement_check='pass')
    print(json.dumps(measurement))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    plan = modes.add_parser('plan')
    plan.add_argument('allocation', type=Path)
    plan.add_argument('output', type=Path)
    for mode in ['run', 'rank']:
        sub = modes.add_parser(mode)
        sub.add_argument('--plan', type=Path, required=True)
        sub.add_argument('--p', type=int, required=True)
        sub.add_argument('--t', type=int, required=True)
        sub.add_argument('--probe', type=Path, required=True)
        if mode == 'run':
            sub.add_argument('--output', type=Path, required=True)
            sub.add_argument('--nodefile', type=Path, required=True)
        else:
            sub.add_argument('--directory', type=Path, required=True)
        sub.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.mode == 'plan':
        args.output.write_text(json.dumps(build_plan(json.loads(args.allocation.read_text())), indent=2) + '\n')
    else:
        if args.command and args.command[0] == '--':
            args.command = args.command[1:]
        if not args.command:
            parser.error('An executable after -- is required')
        if args.mode == 'run':
            run(args)
        else:
            rank_launch(args)


if __name__ == '__main__':
    main()
