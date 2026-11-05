#!/usr/bin/env python3
"""Independent November rubric campaign: 275 ordinary + 75 diagnostic records."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shlex
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

from benchmark import command
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'hpc'))
from rubric_placement import verify_placement
SUITES = ('serial', 'strong', 'weak', 'hybrid', 'communication', 'gpu')
PROCESSES = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def matrix(suite, c=64, profile=False):
    if c not in (8, 16, 32, 64):
        raise ValueError('C must be 8, 16, 32 or 64')
    rows = []
    def add(**changes):
        rows.append(dict(dict(suite=suite, n=4000000, d=32, k=32, p=1, t=1,
                              variant='v1', communication='allreduce', profile=profile), **changes))
    if suite == 'serial' and not profile:
        for n in (100000, 200000, 500000, 1000000, 2000000, 4000000):
            add(n=n, variant='v0')
        for d in (8, 16, 32, 64, 128):
            add(n=1000000, d=d, variant='v0')
        for k in (8, 16, 32, 64, 128):
            add(n=1000000, k=k, variant='v0')
    elif suite in ('strong', 'weak'):
        if suite == 'strong' and not profile:
            add(variant='v0')
        for p in ((1, c, 256) if profile else PROCESSES):
            add(p=p, n=100000 * p if suite == 'weak' else 4000000)
    elif suite == 'hybrid':
        if not profile:
            add(p=256)
        for p, t in (((32, 8),) if profile else ((256, 1), (128, 2), (64, 4), (32, 8))):
            for variant in ('v2', 'v3'):
                add(p=p, t=t, variant=variant)
    elif suite == 'communication':
        for p in (c, 256):
            for comm in ('allreduce', 'reduce-bcast'):
                add(p=p, communication=comm)
    elif suite == 'gpu':
        for n in (100000, 1000000, 4000000):
            for variant, t in ((('v4', 1),) if profile else (('v0', 1), ('v3', 8), ('v4', 1))):
                add(n=n, variant=variant, t=t)
    return list({json.dumps(row, sort_keys=True): row for row in rows}.values())


def source_manifest(root=ROOT):
    files = [root / 'Makefile']
    # Plot dependencies belong to the full local analysis repository, not the
    # source-only submission. Preserve them in historical snapshots when present.
    if (root / 'requirements.txt').is_file():
        files.append(root / 'requirements.txt')
    for directory, patterns in [('src', ('*.hpp', '*.cpp', '*.cu')), ('scripts', ('*.py',)),
                                ('hpc', ('rubric*',)), ('tests', ('*.py',))]:
        for pattern in patterns:
            files += [f for f in (root / directory).glob(pattern) if f.is_file()]
    return {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(set(files))}


def validate_result(result, row, layout, iterations=20, warmup=2):
    for key in ('n', 'd', 'k', 'p', 't', 'variant', 'communication'):
        if result[key] != row[key]:
            raise ValueError('Actual workload mismatch: ' + key)
    if (result['iterations'] != iterations or result['warmup'] != warmup or
            result['mode'] != 'fixed' or result['seed'] != 42 or
            result['diagnostic'] != row['profile'] or result['skew'] or result['input']):
        raise ValueError('Unexpected mode, timing workload or diagnostic status')
    if (len(result['counts']) != row['k'] or any(v < 0 for v in result['counts']) or
            sum(result['counts']) != row['n'] or not result['data_fingerprint'] or
            len(result['init_indices']) != row['k'] or len(set(result['init_indices'])) != row['k'] or
            any(v < 0 or v >= row['n'] for v in result['init_indices'])):
        raise ValueError('Invalid final counts/input identity')
    if layout:
        verify_placement(result['placement'], layout, row['p'], row['t'])
        expected_nodes = min(len(layout['hosts']), max(1, row['p'] * row['t'] // layout['cores_per_node']))
        if result['nodes'] != expected_nodes:
            raise ValueError('Actual number of nodes differs from planned packing')
    if result['backend'] != ('cuda' if row['variant'] == 'v4' else 'cpu'):
        raise ValueError('Backend differs from requested implementation')
    if row['variant'] == 'v4':
        gpu = result['gpu']
        if result['backend'] != 'cuda' or gpu['kernel_launches'] < iterations * 2 or not gpu['uuid']:
            raise ValueError('No evidence of real CUDA execution')
        if row['profile']:
            events = gpu['phase_seconds']
            if set(events) != {'h2d', 'assignment', 'merge', 'd2h'} or any(not math.isfinite(v) or v < 0 for v in events.values()):
                raise ValueError('Invalid independent CUDA event timings')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite', choices=SUITES + ('all',), required=True)
    p.add_argument('--cores-per-node', type=int, choices=(8, 16, 32, 64), default=64)
    p.add_argument('--kind', choices=('both', 'ordinary', 'profile'), default='both')
    p.add_argument('--allocation', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--development', action='store_true', help='tiny local smoke; never accepted as formal evidence')
    p.add_argument('--timeout', type=int, default=7200)
    p.add_argument('--launcher', default='mpiexec -n {p}')
    a = p.parse_args()
    suites = SUITES if a.suite == 'all' else (a.suite,)
    rows = [row for suite in suites for prof in (False, True)
            if a.kind == 'both' or (a.kind == 'profile') == prof
            for row in matrix(suite, a.cores_per_node, prof)]
    layout = json.loads(a.allocation.read_text()) if a.allocation else None
    launcher = a.launcher
    if layout:
        if layout['cores_per_node'] != a.cores_per_node:
            p.error('C differs from verified allocation')
        launcher = shlex.join([sys.executable, str(ROOT / 'hpc/rubric_launch.py'),
                              '--allocation', str(a.allocation.resolve()), '--p', '{p}', '--t', '{t}', '--'])
    if a.development:
        # Small correctness/runner test only, deliberately outside the formal matrix.
        rows = [dict(r, n=37, d=3, k=4, p=min(r['p'], 2), t=min(r['t'], 2))
                for r in rows[:2]]
    args = SimpleNamespace(launcher=launcher, serial_launcher=launcher, iterations=2 if a.development else 20,
                           warmup=2, seed=42, skew=False)
    def cmd(row):
        return command(args, row) + (['--profile'] if row['profile'] else [])
    if a.dry_run:
        for row in rows:
            print(json.dumps(dict(row, command=cmd(row))))
        return
    if a.suite == 'all' or not a.output or (not layout and not a.development):
        p.error('Execution requires one suite, --output and verified --allocation (or --development)')
    if not a.development:
        preflight = a.allocation.parent / 'preflight.json'
        if not preflight.exists():
            p.error('Run rubric_preflight.py before formal timing')
        ready = json.loads(preflight.read_text())
        if ready['source_manifest'] != source_manifest() or ready['allocation_sha256'] != hashlib.sha256(a.allocation.read_bytes()).hexdigest():
            p.error('Sources/allocation changed after preflight; repeat preflight')
        if ready['job_id'] != os.environ.get('PBS_JOBID'):
            p.error('Preflight belongs to a different PBS allocation')
        if a.suite not in ('serial', 'gpu') and not ready['verified_256']:
            p.error('256-core placement preflight is required')
        for name, digest in ready['binary_manifest'].items():
            binary = ROOT / 'build' / name
            if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != digest:
                p.error('Binary changed after preflight: ' + name)
        if a.suite == 'gpu' and not ready['gpu_verified']:
            p.error('GPU preflight was not completed')
    a.output.mkdir(parents=True, exist_ok=False)
    source = source_manifest()
    (a.output / 'source-manifest.json').write_text(json.dumps(source, indent=2) + '\n')
    if layout:
        (a.output / 'allocation.json').write_text(json.dumps(layout, indent=2) + '\n')
    run_id = str(uuid.uuid4())
    schedule = [(repeat, row) for repeat in range(5) for row in rows]
    random.Random(202611).shuffle(schedule)
    with (a.output / 'raw.jsonl').open('x') as ordinary, (a.output / 'profiles.jsonl').open('x') as profiles:
        for index, (repeat, row) in enumerate(schedule):
            argv = cmd(row)
            binary = Path(argv[argv.index('--n') - 1])
            binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
            if source_manifest() != source:
                raise RuntimeError('Source changed before measurement')
            if not a.development and binary_hash != ready['binary_manifest'][binary.name]:
                raise RuntimeError('Binary changed before measurement')
            print('[%d/%d] %s' % (index + 1, len(schedule), shlex.join(argv)), file=sys.stderr, flush=True)
            launch_start = time.perf_counter()
            proc = subprocess.run(argv, text=True, capture_output=True, timeout=a.timeout)
            launch_seconds = time.perf_counter() - launch_start
            prefix = a.output / ('%03d' % index)
            prefix.with_suffix('.stdout').write_text(proc.stdout)
            prefix.with_suffix('.stderr').write_text(proc.stderr)
            if proc.returncode:
                raise RuntimeError('Measurement failed; raw stdout/stderr retained')
            if source_manifest() != source or hashlib.sha256(binary.read_bytes()).hexdigest() != binary_hash:
                raise RuntimeError('Source/binary changed during measurement; sample rejected')
            result = json.loads(proc.stdout)
            validate_result(result, row, layout, args.iterations, args.warmup)
            result.update(suite=row['suite'], repeat=repeat, run_id=run_id,
                          campaign='rubric-202611', development=a.development,
                          cores_per_node=a.cores_per_node, command=argv, launch_seconds=launch_seconds,
                          timestamp_utc=datetime.now(timezone.utc).isoformat(),
                          job_id=os.environ.get('PBS_JOBID', 'unset'),
                          binary_sha256=binary_hash, invocation_id=index,
                          source_manifest=source)
            out = profiles if row['profile'] else ordinary
            out.write(json.dumps(result, allow_nan=False) + '\n')
            out.flush()
    if source_manifest() != source:
        raise RuntimeError('Source changed after schedule')
    files = {str(f.relative_to(a.output)): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in a.output.rglob('*') if f.is_file()}
    with (a.output / 'completion.json').open('x') as f:
        json.dump(dict(records=len(schedule), files=files, source_manifest=source), f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
