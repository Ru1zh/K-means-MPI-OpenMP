#!/usr/bin/env python3
"""Strict audit and statistics for the independent November rubric campaign."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rubric_campaign import SUITES, matrix, validate_result, source_manifest
FIELDS = ('suite', 'n', 'd', 'k', 'p', 't', 'variant', 'communication', 'profile')


def key(row):
    return tuple(row[k] if k != 'profile' else row.get('profile', row.get('diagnostic')) for k in FIELDS)


def scaling_metrics(suite, p, seconds, serial=None, mpi_one=None):
    if seconds <= 0:
        raise ValueError('Nonpositive measurement')
    if suite == 'strong':
        return dict(speedup_serial=serial / seconds, efficiency_serial=serial / seconds / p,
                    speedup_mpi=mpi_one / seconds, efficiency_mpi=mpi_one / seconds / p)
    if suite == 'weak':
        return dict(weak_efficiency=mpi_one / seconds,
                    throughput_speedup=p * mpi_one / seconds)
    return {}


def read_runs(folder):
    rows, layouts = [], {}
    for path in sorted(folder.rglob('raw.jsonl')):
        allocation = path.parent / 'allocation.json'
        if not allocation.exists():
            raise ValueError('Missing actual allocation next to ' + str(path))
        layout = json.loads(allocation.read_text())
        probe = path.parent.parent / 'probe'
        preflight = json.loads((probe / 'preflight.json').read_text())
        job = path.parent.parent
        for name in ('job.pbs', 'job.stdout'):
            if not (job / name).is_file() or not (job / name).stat().st_size:
                raise ValueError('Missing PBS script/output: ' + name)
        expected_sources = preflight['source_manifest']
        if source_manifest(job / 'source') != expected_sources:
            raise ValueError('Preserved source differs from measurement source')
        # Post-experiment test cleanup and reporting edits must not rewrite the
        # measured snapshots. Still require the delivered computational sources
        # and build recipe to match the actual measured implementation exactly.
        current_sources = source_manifest()
        computational = {'Makefile'} | {name for name in expected_sources if name.startswith('src/')}
        if computational != ({'Makefile'} | {name for name in current_sources if name.startswith('src/')}) or any(
                current_sources.get(name) != expected_sources[name] for name in computational):
            raise ValueError('Delivered computational source differs from measurement source')
        required = {'PBS_NODEFILE', 'job.txt', 'queues.txt', 'mpi-launcher.txt',
                    'host-compiler.txt', 'mpi-flags.txt', 'inventory.txt', 'allocation.json', 'ties.txt'}
        if preflight['gpu_verified']:
            required.update(('gpu.txt', 'nvcc.txt', 'cuda-tests.txt'))
        required.update('check-%02d.%s' % (i, ext) for i in range(preflight['checks'])
                        for ext in ('stdout', 'stderr'))
        actual_probe = {str(f.relative_to(probe)): hashlib.sha256(f.read_bytes()).hexdigest()
                        for f in probe.rglob('*') if f.is_file() and f.name != 'preflight.json'}
        if not required.issubset(actual_probe) or preflight['evidence_manifest'] != actual_probe:
            raise ValueError('Incomplete or altered numerical/resource preflight evidence')
        completion = json.loads((path.parent / 'completion.json').read_text())
        actual_measurements = {str(f.relative_to(path.parent)): hashlib.sha256(f.read_bytes()).hexdigest()
                               for f in path.parent.rglob('*') if f.is_file() and f.name != 'completion.json'}
        if completion['files'] != actual_measurements or completion['source_manifest'] != expected_sources:
            raise ValueError('Incomplete or altered measurement evidence')
        total = completion['records']
        required = {'raw.jsonl', 'profiles.jsonl', 'allocation.json', 'source-manifest.json'}
        required.update('%03d.%s' % (i, ext) for i in range(total) for ext in ('stdout', 'stderr'))
        if not required.issubset(actual_measurements):
            raise ValueError('Missing invocation stdout/stderr evidence')
        invocation_ids = []
        if preflight['allocation_sha256'] != hashlib.sha256(allocation.read_bytes()).hexdigest():
            raise ValueError('Allocation does not match preflight')
        for filename, diagnostic in (('raw.jsonl', False), ('profiles.jsonl', True)):
            for line in (path.parent / filename).read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                invocation_ids.append(row['invocation_id'])
                original = json.loads((path.parent / ('%03d.stdout' % row['invocation_id'])).read_text())
                if any(row.get(k) != v for k, v in original.items()):
                    raise ValueError('Recorded sample differs from executable stdout')
                if row['diagnostic'] != diagnostic:
                    raise ValueError('Ordinary and diagnostic files mixed')
                if (row['source_manifest'] != preflight['source_manifest'] or
                        row['job_id'] != preflight['job_id']):
                    raise ValueError('Preflight context mismatch')
                binary = {'v0': 'kmeans_serial', 'v4': 'kmeans_cuda'}.get(row['variant'], 'kmeans_mpi')
                if row['binary_sha256'] != preflight['binary_manifest'][binary]:
                    raise ValueError('Binary differs from validated preflight')
                if row['suite'] not in ('serial', 'gpu') and not preflight['verified_256']:
                    raise ValueError('Missing 256-core preflight')
                if row['suite'] == 'gpu' and not preflight['gpu_verified']:
                    raise ValueError('Missing GPU numerical preflight')
                if row['run_id'] in layouts and layouts[row['run_id']] != layout:
                    raise ValueError('A run_id spans different allocations')
                layouts[row['run_id']] = layout
                rows.append(row)
        if sorted(invocation_ids) != list(range(total)):
            raise ValueError('Missing/duplicate invocation evidence')
    return rows, layouts


def audit_records(rows, layouts):
    if not rows:
        raise ValueError('No Vanda measurements yet. Run all six experiment suites before auditing the campaign.')
    groups, seen, suite_runs, contexts, numerical, binaries = {}, set(), {}, set(), {}, {}
    gpu_identities = set()
    for row in rows:
        if row.get('development') is not False or row.get('campaign') != 'rubric-202611':
            raise ValueError('Development/historical samples cannot be formal evidence')
        suite = row['suite']
        if suite not in SUITES:
            raise ValueError('Unknown suite')
        suite_runs.setdefault(suite, set()).add(row['run_id'])
        layout = layouts[row['run_id']]
        if row['cores_per_node'] != layout['cores_per_node']:
            raise ValueError('Incorrect C')
        spec = next((r for r in matrix(suite, row['cores_per_node'], row['diagnostic']) if key(r) == key(row)), None)
        if spec is None:
            raise ValueError('Configuration is outside the approved matrix')
        validate_result(row, spec, layout)
        for field in ('kernel_seconds', 'total_seconds', 'sse'):
            if not math.isfinite(row[field]) or row[field] <= 0:
                raise ValueError('Invalid time/objective: ' + field)
        if row['total_seconds'] < row['kernel_seconds']:
            raise ValueError('End-to-end time excludes kernel work')
        identity = key(row), row['repeat']
        if row['repeat'] not in range(5) or identity in seen:
            raise ValueError('Duplicate or out-of-range repeat')
        seen.add(identity)
        groups.setdefault(key(row), []).append(row)
        contexts.add(json.dumps(row['source_manifest'], sort_keys=True))
        bkey = suite, row['variant']
        if bkey in binaries and binaries[bkey] != row['binary_sha256']:
            raise ValueError('Binary changed inside a comparison')
        binaries[bkey] = row['binary_sha256']
        nkey = suite, row['n'], row['d'], row['k']
        if nkey in numerical:
            ref = numerical[nkey]
            if row['data_fingerprint'] != ref['data_fingerprint'] or row['init_indices'] != ref['init_indices']:
                raise ValueError('Input/initialization differs inside a controlled comparison')
            if not math.isclose(row['sse'], ref['sse'], rel_tol=1e-8 if suite == 'gpu' else 1e-10, abs_tol=1e-10):
                raise ValueError('Final SSE differs across matched workloads')
        else:
            numerical[nkey] = row
        if row['variant'] == 'v4':
            gpu_identities.add(row['gpu']['uuid'])
        if row['diagnostic']:
            critical_profile(row)
    if len(gpu_identities) != 1:
        raise ValueError('GPU device changed inside the same-job comparison')
    if len(contexts) != 1 or set(suite_runs) != set(SUITES) or any(len(ids) != 1 for ids in suite_runs.values()):
        raise ValueError('Require one complete job per suite, all from the same source snapshot')
    for suite in SUITES:
        c = next(r['cores_per_node'] for r in rows if r['suite'] == suite)
        expected = {key(r) for prof in (False, True) for r in matrix(suite, c, prof)}
        actual = {k for k in groups if k[0] == suite}
        if actual != expected or any(len(groups[k]) != 5 for k in actual):
            raise ValueError('Incomplete configurations/repeats: ' + suite)
    if sum(not r['diagnostic'] for r in rows) != 275 or sum(r['diagnostic'] for r in rows) != 75:
        raise ValueError('Expected exactly 275 ordinary and 75 diagnostic records')
    return groups


def critical_profile(row):
    profiles = row['profile_ranks']
    if sorted(p['rank'] for p in profiles) != list(range(row['p'])):
        raise ValueError('Missing per-rank profiles')
    winner = max(profiles, key=lambda r: (r['kernel_seconds'], -r['rank']))
    if winner['rank'] != row['profile_critical_rank'] or winner['kernel_seconds'] != row['kernel_seconds']:
        raise ValueError('Wrong critical rank')
    for sample in profiles:
        values = list(sample['phase_seconds'].values())
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('Invalid phase time')
        if sum(values) > sample['kernel_seconds'] + 1e-6:
            raise ValueError('Overlapping/inconsistent local phase timings')
    return winner


def summarize(groups):
    tables, profiles = [], []
    for config, rows in groups.items():
        head = dict(zip(FIELDS, config))
        if head.pop('profile'):
            # One real median-kernel sample, retaining ALL phases of its critical rank.
            # This allows a stacked chart without adding unrelated phase medians/maxima.
            representative = sorted(rows, key=lambda r: r['kernel_seconds'])[2]
            selected = critical_profile(representative)
            entry = dict(head, repeat=representative['repeat'], critical_rank=selected['rank'],
                         kernel_seconds=selected['kernel_seconds'], **selected['phase_seconds'])
            if representative['variant'] == 'v4':
                entry.update({'gpu_' + k: v for k, v in representative['gpu']['phase_seconds'].items()})
            profiles.append(entry)
            continue
        times = [r['kernel_seconds'] for r in rows]
        totals = [r['total_seconds'] for r in rows]
        tables.append(dict(head, run_id=rows[0]['run_id'], job_id=rows[0]['job_id'],
                           nodes=rows[0]['nodes'], cores_per_node=rows[0]['cores_per_node'], repeats=5,
                           median_seconds=statistics.median(times), min_seconds=min(times), max_seconds=max(times),
                           median_total_seconds=statistics.median(totals), min_total_seconds=min(totals), max_total_seconds=max(totals),
                           seconds_per_inkd=statistics.median(times) / (20 * head['n'] * head['k'] * head['d'])))
    def baseline(suite, predicate):
        matches = [r for r in tables if r['suite'] == suite and predicate(r)]
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous same-job baseline for ' + suite)
        return matches[0]['median_seconds']
    serial = baseline('strong', lambda r: r['variant'] == 'v0')
    mpi_one = baseline('strong', lambda r: r['variant'] == 'v1' and r['p'] == 1)
    weak_one = baseline('weak', lambda r: r['p'] == 1)
    hybrid = baseline('hybrid', lambda r: r['variant'] == 'v1')
    for row in tables:
        suite, time = row['suite'], row['median_seconds']
        if suite == 'strong':
            row.update(scaling_metrics(suite, row['p'], time, serial, mpi_one))
        elif suite == 'weak':
            row.update(scaling_metrics(suite, row['p'], time, mpi_one=weak_one))
        elif suite == 'hybrid':
            row.update(speedup_vs_mpi256=hybrid / time, time_change_percent=100 * (time / hybrid - 1))
        elif suite == 'gpu':
            cpu = baseline('gpu', lambda r: r['n'] == row['n'] and r['variant'] == 'v0')
            cpu8 = baseline('gpu', lambda r: r['n'] == row['n'] and r['variant'] == 'v3')
            row.update(speedup_vs_cpu1=cpu / time, speedup_vs_cpu8=cpu8 / time)
        elif suite == 'communication':
            allreduce = baseline(suite, lambda r: r['p'] == row['p'] and r['communication'] == 'allreduce')
            row.update(time_ratio_vs_allreduce=time / allreduce)
    return tables, profiles


def write_csv(path, rows):
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def tables(folder, groups):
    folder.mkdir(parents=True, exist_ok=False)
    ordinary, profiles = summarize(groups)
    write_csv(folder / 'statistics.csv', ordinary)
    write_csv(folder / 'profiles.csv', profiles)
    for suite in SUITES:
        write_csv(folder / (suite + '.csv'), [r for r in ordinary if r['suite'] == suite])
    return ordinary, profiles
