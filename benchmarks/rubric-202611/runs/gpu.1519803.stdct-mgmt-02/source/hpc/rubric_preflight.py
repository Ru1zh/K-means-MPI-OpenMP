#!/usr/bin/env python3
"""Fail-closed numerical and actual-placement acceptance, outside formal timing."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rubric_campaign import source_manifest
from rubric_launch import launch_command
from rubric_placement import verify_placement


def compare(reference, observed, small=True, gpu=False):
    for key in ('data_fingerprint', 'init_indices', 'counts'):
        if reference[key] != observed[key]:
            raise ValueError('Numerical preflight mismatch: ' + key)
    if small:
        if reference['labels'] != observed['labels']:
            raise ValueError('Incorrect labels')
        if len(reference['centers']) != len(observed['centers']):
            raise ValueError('Wrong centroid dimensions')
        if not all(math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10)
                   for a, b in zip(reference['centers'], observed['centers'])):
            raise ValueError('Incorrect centroids')
    if not math.isclose(reference['sse'], observed['sse'], rel_tol=1e-8 if gpu else 1e-10, abs_tol=1e-10):
        raise ValueError('SSE failed the declared tolerance')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allocation', type=Path, required=True)
    p.add_argument('--gpu', action='store_true')
    p.add_argument('--require-256', action='store_true')
    a = p.parse_args()
    layout = json.loads(a.allocation.read_text())
    if layout['job_id'] != os.environ.get('PBS_JOBID'):
        p.error('Stale allocation: job identity differs')
    out = a.allocation.parent
    if (out / 'preflight.json').exists():
        p.error('Preflight already exists; use a fresh probe directory')
    records = []
    def run(variant, ranks, threads, args, spread=False, comm='allreduce'):
        binary = {'v0': 'kmeans_serial', 'v4': 'kmeans_cuda'}.get(variant, 'kmeans_mpi')
        command = [str(ROOT / 'build' / binary), '--variant', variant, '--threads', str(threads),
                   '--comm', comm] + args
        command = launch_command(a.allocation, ranks, threads, command, spread)
        proc = subprocess.run(command, text=True, capture_output=True, timeout=600)
        index = len(records)
        (out / ('check-%02d.stdout' % index)).write_text(proc.stdout)
        (out / ('check-%02d.stderr' % index)).write_text(proc.stderr)
        if proc.returncode:
            raise RuntimeError('Preflight executable failed; inspect check-%02d.stderr' % index)
        row = json.loads(proc.stdout)
        if (row['p'], row['t'], row['variant']) != (ranks, threads, variant):
            raise ValueError('Wrong actual preflight configuration')
        verify_placement(row['placement'], layout, ranks, threads)
        if spread and row['nodes'] != ranks:
            raise ValueError('Cross-node correctness test did not use distinct nodes')
        records.append(row)
        return row
    small = ['--n', '37', '--d', '3', '--k', '4', '--iterations', '5', '--warmup', '2', '--dump']
    reference = run('v0', 1, 1, small)
    for variant, t in (('v1', 1), ('v2', 2), ('v3', 2)):
        for comm in ('allreduce', 'reduce-bcast'):
            compare(reference, run(variant, 3, t, small, comm=comm))
    # Explicit input exercises tie breaking, empty clusters and ranks with no points.
    fixture = out / 'ties.txt'
    fixture.write_text('3 1\n0\n2\n1\n')
    edge = ['--input', str(fixture.resolve()), '--k', '3', '--init-indices', '0,1,2',
            '--iterations', '3', '--dump']
    edge_ref = run('v0', 1, 1, edge)
    # Identical initial centers force an empty cluster; the midpoint is an exact tie.
    fixture.write_text('3 1\n0\n2\n0\n')
    edge_ref = run('v0', 1, 1, edge)
    for variant, t in (('v1', 1), ('v2', 2), ('v3', 2)):
        for comm in ('allreduce', 'reduce-bcast'):
            compare(edge_ref, run(variant, 4, t, edge, comm=comm))
    if len(layout['hosts']) > 1:
        compare(reference, run('v1', 2, 1, small, spread=True))
    if a.require_256:
        if len(layout['hosts']) * layout['cores_per_node'] < 256:
            raise ValueError('256 distinct physical cores were not allocated')
        compare(reference, run('v1', 256, 1, small))  # also tests 219 empty ranks
        for variant in ('v2', 'v3'):
            for ranks, threads in ((256, 1), (128, 2), (64, 4), (32, 8)):
                compare(reference, run(variant, ranks, threads, small))
    if a.gpu:
        compare(reference, run('v4', 1, 1, small), gpu=True)
        compare(edge_ref, run('v4', 1, 1, edge), gpu=True)
        # Full-scale numerical validation is intentionally separate from 20-iteration timing.
        for n in (100000, 1000000, 4000000):
            args = ['--n', str(n), '--d', '32', '--k', '32', '--iterations', '20', '--warmup', '2']
            ref = run('v0', 1, 1, args)
            compare(ref, run('v3', 1, 8, args), small=False)
            compare(ref, run('v4', 1, 1, args), small=False, gpu=True)
        env = dict(os.environ, TEST_CUDA='1')
        proc = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_cuda.py', '-v'],
                              cwd=ROOT, env=env, text=True, capture_output=True, timeout=600)
        (out / 'cuda-tests.txt').write_text(proc.stdout + proc.stderr)
        if proc.returncode:
            raise ValueError('CUDA integration suite failed')
    binaries = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                for f in (ROOT / 'build').glob('kmeans_*') if f.is_file()}
    evidence = {str(f.relative_to(out)): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in out.rglob('*') if f.is_file()}
    result = dict(evidence_manifest=evidence, source_manifest=source_manifest(), binary_manifest=binaries,
                  allocation_sha256=hashlib.sha256(a.allocation.read_bytes()).hexdigest(),
                  gpu_verified=a.gpu, verified_256=a.require_256, checks=len(records),
                  job_id=os.environ.get('PBS_JOBID'))
    (out / 'preflight.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Preflight passed: %d independent checks' % len(records))


if __name__ == '__main__':
    main()
