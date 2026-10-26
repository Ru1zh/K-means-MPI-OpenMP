#!/usr/bin/env python3
"""Fixed P=2 Linux placement with six reserved cores and nested active OpenMP sets."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

THREADS = [1, 2, 3, 4, 6]

# Share the independent thread-level audit with the established hybrid launcher.
_spec = importlib.util.spec_from_file_location('atlas_hybrid_probe_check',
                                             Path(__file__).with_name('atlas-hybrid-launch.py'))
_hybrid = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hybrid)
verify_threads = _hybrid.verify_threads


def build_plan(allocation):
    cpus = allocation['allowed_cpus']
    topology = allocation['topology']
    if (not isinstance(cpus, list) or len(cpus) != 12 or
            any(type(c) is not int or c < 0 for c in cpus) or len(set(cpus)) != 12):
        raise ValueError('Exactly 12 distinct allocated OS CPUs required')
    if not isinstance(allocation['host'], str) or not allocation['host']:
        raise ValueError('Allocation host is required')
    for cpu in cpus:
        entry = topology[str(cpu)]
        if any(type(entry[key]) is not int or entry[key] < 0 for key in ['socket', 'core']):
            raise ValueError('Physical socket/core IDs must be nonnegative integers')
    physical = {(topology[str(c)]['socket'], topology[str(c)]['core']) for c in cpus}
    if len(physical) != 12:
        raise ValueError('Allocation must contain 12 distinct physical cores')
    ordered = sorted(cpus, key=lambda c: (topology[str(c)]['socket'], topology[str(c)]['core'], c))
    reserved = [ordered[:6], ordered[6:]]
    if any(len({topology[str(c)]['socket'] for c in rank}) != 1 for rank in reserved):
        raise ValueError('Cannot reserve two socket-local groups of six cores from this allocation')
    return dict(schema_version=1, p=2, max_threads=6, threads=list(THREADS), allocation=allocation,
                reserved_ranks=reserved,
                configurations={str(t): dict(p=2, t=t, ranks=[rank[:t] for rank in reserved])
                                for t in THREADS})


def configuration(plan, t):
    if type(t) is not int or t not in THREADS:
        raise ValueError('Thread count must be one of 1, 2, 3, 4, 6')
    if plan != build_plan(plan['allocation']):
        raise ValueError('Placement plan does not match the fixed P=2 allocation')
    return plan['configurations'][str(t)]


def places(cpus):
    return ','.join('{%d}' % c for c in cpus)


def verify_records(plan, t, records):
    config = configuration(plan, t)
    if len(records) != 2 or {r['rank'] for r in records} != {0, 1}:
        raise ValueError('Missing/duplicate MPI ranks')
    used = []
    for record in records:
        rank = record['rank']
        if type(rank) is not int:
            raise ValueError('MPI rank ID must be an integer')
        expected = plan['reserved_ranks'][rank]
        active = config['ranks'][rank]
        if record['host'] != plan['allocation']['host']:
            raise ValueError('Unexpected compute host')
        if sorted(record['rank_cpus']) != sorted(expected) or record['p'] != 2 or record['t'] != t:
            raise ValueError('MPI rank CPU mask/configuration mismatch')
        if record['active_cpus'] != active or record['omp_places'] != places(active):
            raise ValueError('Active CPUs/explicit OpenMP places mismatch')
        verify_threads(record['thread_probe'], active)
        used.extend(record['rank_cpus'])
    if len(used) != 12 or len(set(used)) != 12 or set(used) != set(plan['allocation']['allowed_cpus']):
        raise ValueError('Ranks overlap or leave the 12-core allocation')
    return dict(p=2, t=t, placement_check='pass')


def exclusive_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def require_command(command):
    if (not isinstance(command, list) or not command or
            any(not isinstance(arg, str) or '\x00' in arg for arg in command) or not command[0].strip()):
        raise ValueError('A nonempty executable command is required')


def rank_launch(args):
    require_command(args.command)
    plan = json.loads(args.plan.read_text())
    config = configuration(plan, args.t)
    rank = int(os.environ['OMPI_COMM_WORLD_RANK'])
    p = int(os.environ['OMPI_COMM_WORLD_SIZE'])
    if p != 2 or not 0 <= rank < 2:
        raise ValueError('MPI world/configuration mismatch; P must be 2')
    host = socket.gethostname()
    if host != plan['allocation']['host']:
        raise ValueError('Unexpected host before setting CPU affinity')
    if not set(plan['allocation']['allowed_cpus']) <= set(os.sched_getaffinity(0)):
        raise ValueError('Launcher did not inherit the complete PBS CPU set')
    reserved = plan['reserved_ranks'][rank]
    active = config['ranks'][rank]
    os.sched_setaffinity(0, reserved)
    actual = sorted(os.sched_getaffinity(0))
    if actual != sorted(reserved):
        raise ValueError('Could not apply planned rank CPU mask')
    env = dict(os.environ)
    for key in ['GOMP_CPU_AFFINITY', 'KMP_AFFINITY', 'KMP_HW_SUBSET', 'OMP_THREAD_LIMIT']:
        env.pop(key, None)
    env.update(OMP_NUM_THREADS=str(args.t), OMP_DYNAMIC='FALSE', OMP_PROC_BIND='close',
               OMP_PLACES=places(active))
    probe = subprocess.run([str(args.probe), str(args.t)], env=env, text=True,
                           capture_output=True, timeout=30)
    if probe.stderr:
        print(probe.stderr, file=sys.stderr, end='')
    if probe.returncode:
        raise RuntimeError('OpenMP placement probe failed with status %d' % probe.returncode)
    threads = json.loads(probe.stdout)
    verify_threads(threads, active)
    record = dict(rank=rank, p=2, t=args.t, host=host, rank_cpus=actual, active_cpus=active,
                  omp_places=env['OMP_PLACES'], thread_probe=threads, command=args.command)
    exclusive_json(args.directory / ('rank-%d.json' % rank), record)
    os.execvpe(args.command[0], args.command, env)


def save_output(directory, stdout, stderr):
    # TimeoutExpired can carry bytes even with text=True.
    stdout = stdout.decode(errors='replace') if isinstance(stdout, bytes) else (stdout or '')
    stderr = stderr.decode(errors='replace') if isinstance(stderr, bytes) else (stderr or '')
    with (directory / 'stdout.txt').open('x') as stream:
        stream.write(stdout)
    with (directory / 'stderr.txt').open('x') as stream:
        stream.write(stderr)
    if stderr:
        print(stderr, file=sys.stderr, end='')


def run(args):
    require_command(args.command)
    plan = json.loads(args.plan.read_text())
    configuration(plan, args.t)
    directory = args.output / ('launch-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    command = ['mpirun', '--hostfile', str(args.nodefile), '-n', '2', '--bind-to', 'none',
               '--nooversubscribe', sys.executable, str(Path(__file__).resolve()),
               'rank', '--plan', str(args.plan.resolve()), '--t', str(args.t),
               '--probe', str(args.probe.resolve()), '--directory', str(directory.resolve()), '--'] + args.command
    exclusive_json(directory / 'launch.json', dict(p=2, t=args.t, command=command,
                                                  algorithm_command=args.command))
    try:
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=240)
        except subprocess.TimeoutExpired as error:
            save_output(directory, error.stdout, error.stderr)
            raise
        save_output(directory, result.stdout, result.stderr)
        if result.returncode:
            if result.stdout:
                print(result.stdout, file=sys.stderr, end='')
            raise SystemExit(result.returncode)
        records = [json.loads((directory / ('rank-%d.json' % rank)).read_text()) for rank in range(2)]
        check = verify_records(plan, args.t, records)
        measurement = json.loads(result.stdout)
        if not isinstance(measurement, dict):
            raise ValueError('Algorithm measurement must be a JSON object')
    except (Exception, SystemExit) as error:
        exclusive_json(directory / 'check.json', dict(p=2, t=args.t, placement_check='fail', error=str(error)))
        raise
    exclusive_json(directory / 'check.json', check)
    measurement.update(placement_id=directory.name, placement_check='pass')
    print(json.dumps(measurement))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    planner = modes.add_parser('plan')
    planner.add_argument('allocation', type=Path)
    planner.add_argument('output', type=Path)
    for mode in ['run', 'rank']:
        sub = modes.add_parser(mode)
        sub.add_argument('--plan', type=Path, required=True)
        sub.add_argument('--t', type=int, choices=THREADS, required=True)
        sub.add_argument('--probe', type=Path, required=True)
        if mode == 'run':
            sub.add_argument('--output', type=Path, required=True)
            sub.add_argument('--nodefile', type=Path, required=True)
        else:
            sub.add_argument('--directory', type=Path, required=True)
        sub.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.mode == 'plan':
        exclusive_json(args.output, build_plan(json.loads(args.allocation.read_text())))
    else:
        if args.command and args.command[0] == '--':
            args.command = args.command[1:]
        try:
            require_command(args.command)
        except ValueError as error:
            parser.error(str(error))
        if args.mode == 'run':
            run(args)
        else:
            rank_launch(args)


if __name__ == '__main__':
    main()
