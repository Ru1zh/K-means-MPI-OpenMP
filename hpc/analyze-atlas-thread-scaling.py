#!/usr/bin/env python3
"""Validate and regenerate a complete independent Atlas P=2 thread-scaling study."""
import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import statistics
import sys

THREADS = [1, 2, 3, 4, 6]
VARIANTS = ('v2', 'v3')
PHASES = ('accumulate', 'thread_merge', 'mpi_reduce', 'centroid_update', 'control_bcast')
WORKLOAD = ('n', 'd', 'k', 'seed', 'iterations', 'warmup')
FORMAL_WORKLOAD = dict(n=1000000, d=32, k=32, seed=42, iterations=20, warmup=2)
SMALL_WORKLOAD = dict(n=37, d=3, k=4, seed=42, iterations=5, warmup=2)
OUTPUTS = ('thread-scaling-summary.csv', 'phase-summary.csv', 'analysis.audit.json',
           'analysis.md')
PHASE_NOTE = ('Each profile sample uses all five phases from its maximum-kernel rank; '
              'ties select the smaller rank. Independent phase maxima across ranks are never summed. '
              'This decomposition does not directly measure pure atomic waiting time.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reject_constant(value):
    raise ValueError('Nonfinite JSON number: ' + value)


def decode(text):
    return json.loads(text, parse_constant=reject_constant)


def load(path):
    return decode(path.read_text())


def finite(value, name, positive=False):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0),
            'Invalid ' + name)
    return value


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, 'Invalid ' + name)
    return value


def tolerance(seconds):
    return max(1e-6, abs(seconds) * 1e-6)


def launcher_module():
    path = Path(__file__).with_name('atlas-thread-scaling-launch.py')
    spec = importlib.util.spec_from_file_location('atlas_thread_scaling_launch_analysis', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def validate_plan(plan, layout, reference):
    require(plan['study'] == 'thread-scaling' and plan['p'] == 2, 'Wrong study or fixed process count')
    require(plan['threads'] == THREADS and plan['repeats'] == 5, 'Incomplete thread/repeat study plan')
    require(plan['expected_timing_records'] == plan['expected_profile_records'] == 50,
            'Incorrect expected record counts')
    require(plan['workload'] == FORMAL_WORKLOAD, 'Formal workload differs from fixed study specification')
    for key in WORKLOAD:
        integer(plan['workload'][key], key, minimum=0 if key in ('seed', 'warmup') else 1)
        require(reference[key] == plan['workload'][key], 'Reference workload mismatch: ' + key)
    validate_reference(reference, FORMAL_WORKLOAD)
    require(isinstance(reference['data_fingerprint'], str) and reference['data_fingerprint'],
            'Missing reference data fingerprint')
    require(len(reference['init_indices']) == reference['k'], 'Invalid reference initialization')
    for value in reference['init_indices']:
        integer(value, 'initial center index')
        require(value < reference['n'], 'Initial center index outside workload')
    require(len(set(reference['init_indices'])) == reference['k'], 'Duplicate initial centers')
    validate_counts(reference)
    finite(reference['sse'], 'reference SSE')
    require(layout['schema_version'] == 1 and layout['p'] == 2 and layout['max_threads'] == 6
            and layout['threads'] == THREADS, 'Layout plan mismatch')
    require(set(layout['configurations']) == set(map(str, THREADS)), 'Incomplete layout plan')


def validate_reference(reference, workload):
    require(reference['variant'] == 'v0' and reference['p'] == reference['t'] == 1
            and reference['diagnostic'] is False, 'Reference must be serial nondiagnostic V0')
    require(reference['mode'] == 'fixed' and reference['stop_reason'] == 'fixed_iterations'
            and reference['requested_iterations'] == workload['iterations'], 'Invalid reference iteration mode')
    for key, value in workload.items():
        integer(reference[key], 'reference ' + key)
        require(reference[key] == value, 'Reference workload mismatch: ' + key)
    require(isinstance(reference['data_fingerprint'], str) and reference['data_fingerprint'],
            'Missing reference fingerprint')
    indices = reference['init_indices']
    require(isinstance(indices, list) and len(indices) == reference['k'], 'Invalid reference initialization')
    for value in indices:
        integer(value, 'reference initial index')
        require(value < reference['n'], 'Reference initial index outside workload')
    require(len(set(indices)) == len(indices), 'Duplicate reference initial indices')
    validate_counts(reference)
    finite(reference['sse'], 'reference SSE')


def validate_dump(row):
    labels = row['labels']
    require(isinstance(labels, list) and len(labels) == row['n'], 'Incomplete small-data labels')
    counts = [0] * row['k']
    for label in labels:
        integer(label, 'small-data label')
        require(label < row['k'], 'Small-data label outside cluster range')
        counts[label] += 1
    require(counts == row['counts'], 'Small-data labels disagree with counts')
    centers = row['centers']
    require(isinstance(centers, list) and len(centers) == row['d'] * row['k'], 'Incomplete small-data centers')
    require(all(isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c) for c in centers),
            'Nonfinite small-data center')


def validate_counts(row):
    counts = row['counts']
    require(isinstance(counts, list) and len(counts) == row['k'], 'Invalid cluster counts')
    for count in counts:
        integer(count, 'cluster count')
    require(sum(counts) == row['n'], 'Cluster counts do not sum to N')


def validate_profile(row):
    ranks = row['profile_ranks']
    require(isinstance(ranks, list) and len(ranks) == 2, 'Incomplete profile ranks')
    for rank in ranks:
        integer(rank['rank'], 'profile rank')
    require({rank['rank'] for rank in ranks} == {0, 1}, 'Missing/duplicate profile ranks')
    for rank in ranks:
        seconds = finite(rank['kernel_seconds'], 'rank kernel_seconds', positive=True)
        phases = rank['phase_seconds']
        require(set(phases) == set(PHASES), 'Incomplete phase measurements')
        values = [finite(phases[phase], 'phase ' + phase) for phase in PHASES]
        require(sum(values) <= seconds + tolerance(seconds), 'Phase sum exceeds rank kernel_seconds')
    critical = min(ranks, key=lambda rank: (-rank['kernel_seconds'], rank['rank']))
    integer(row['profile_critical_rank'], 'critical rank')
    require(row['profile_critical_rank'] == critical['rank'], 'Incorrect critical rank')
    require(abs(row['kernel_seconds'] - critical['kernel_seconds']) <= tolerance(critical['kernel_seconds']),
            'Row kernel_seconds differs from maximum rank kernel_seconds')
    return critical


def validate_placement(folder, row, layout, launcher, root='placements'):
    identifier = row['placement_id']
    require(isinstance(identifier, str) and identifier.startswith('launch-')
            and Path(identifier).name == identifier, 'Invalid placement identifier')
    directory = folder / root / identifier
    launch = load(directory / 'launch.json')
    require((launch['p'], launch['t']) == (2, row['t']), 'Launch configuration mismatch')
    command = launch['algorithm_command']
    require(isinstance(command, list) and command and all(isinstance(a, str) for a in command),
            'Missing algorithm command in launch evidence')
    require(isinstance(launch['command'], list) and launch['command'], 'Missing launch command')
    if 'command' in row:
        saved_command = row['command']
        if '--' in saved_command:
            saved_command = saved_command[saved_command.index('--') + 1:]
        require(saved_command == command, 'Measurement command differs from launch evidence')
    records = [load(directory / ('rank-%d.json' % rank)) for rank in range(2)]
    for rank in records:
        require(rank['command'] == command, 'Rank command differs from launch evidence')
    checked = launcher.verify_records(layout, row['t'], records)
    require(checked == load(directory / 'check.json') and checked['placement_check'] == 'pass',
            'Saved placement check disagrees with evidence')
    require(row['placement_check'] == 'pass', 'Failed measurement placement check')
    return records


def validate_preflight(folder, layout, launcher, environment, formal_ids):
    reference = load(folder / 'reference-small.json')
    validate_reference(reference, SMALL_WORKLOAD)
    validate_dump(reference)
    saved = load(folder / 'preflight-check.json')
    require(saved['numerical_check'] == 'pass' and saved['configurations'] == 20,
            'Missing/failed preflight summary')
    seen = set()
    results = []
    expected_files = set()
    for mode in ('timing', 'profile'):
        for variant in VARIANTS:
            for t in THREADS:
                filename = 'preflight-%s-%s-t%d.json' % (mode, variant, t)
                expected_files.add(filename)
                row = load(folder / filename)
                require(type(row['p']) is int and type(row['t']) is int
                        and (row['p'], row['t'], row['variant']) == (2, t, variant),
                        'Preflight configuration mismatch')
                require(row['diagnostic'] is (mode == 'profile') and row['mode'] == 'fixed'
                        and row['communication'] == 'allreduce' and row['stop_reason'] == 'fixed_iterations'
                        and row['requested_iterations'] == SMALL_WORKLOAD['iterations'], 'Preflight mode mismatch')
                require(not row.get('skew', False) and row.get('input', '') == '', 'Unexpected preflight input/skew')
                require((row['compiler'], row['mpi_version']) == environment[2:], 'Preflight compiler/MPI mismatch')
                if 'host' in row:
                    require(row['host'] == environment[1], 'Preflight host mismatch')
                if 'job_id' in row:
                    require(row['job_id'] == environment[0], 'Preflight job mismatch')
                for key in WORKLOAD + ('data_fingerprint', 'init_indices', 'counts'):
                    require(row[key] == reference[key], 'Preflight numerical mismatch: ' + key)
                validate_counts(row)
                finite(row['sse'], 'preflight SSE')
                require(math.isclose(row['sse'], reference['sse'], rel_tol=1e-10, abs_tol=1e-10),
                        'Preflight SSE mismatch')
                validate_dump(row)
                require(row['labels'] == reference['labels'], 'Preflight labels differ from V0')
                require(all(math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10)
                            for a, b in zip(row['centers'], reference['centers'])), 'Preflight centers differ from V0')
                finite(row['kernel_seconds'], 'preflight kernel_seconds', positive=True)
                if mode == 'profile':
                    validate_profile(row)
                else:
                    require('profile_ranks' not in row and 'profile_critical_rank' not in row,
                            'Rank profile injected into preflight timing')
                identifier = row['placement_id']
                require(identifier not in seen and identifier not in formal_ids, 'Duplicate preflight placement')
                validate_placement(folder, row, layout, launcher, root='preflight-placements')
                seen.add(identifier)
                results.append(dict(measurement_mode=mode, variant=variant, p=2, t=t, numerical_check='pass',
                                    placement_check='pass', sse_absolute_error=abs(row['sse'] - reference['sse']),
                                    max_centroid_absolute_error=max(abs(a-b) for a, b in zip(row['centers'], reference['centers']))))
    require({p.name for p in folder.glob('preflight-*-v*-t*.json')} == expected_files,
            'Unexpected preflight configuration files')
    require({p.name for p in (folder / 'preflight-placements').iterdir() if p.is_dir()} == seen,
            'Preflight placement matrix mismatch')
    return results


def csv_text(rows):
    result = io.StringIO(newline='')
    writer = csv.DictWriter(result, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return result.getvalue()


def make_reports(audit, plan, summaries, phases):
    timing_table = '| Variant | T | Median / s | Min / s | Max / s | Speedup T=1 | Efficiency |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for row in summaries:
        timing_table += '| %s | %d | %.6f | %.6f | %.6f | %.3f | %.2f%% |\n' % (
            row['variant'].upper(), row['t'], row['median_seconds'], row['min_seconds'], row['max_seconds'],
            row['speedup_vs_same_variant_t1'], 100 * row['thread_efficiency'])
    phase_table = '| Variant | T | Kernel / s | accumulate | thread_merge | mpi_reduce | centroid_update | control_bcast | residual |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    for row in phases:
        values = ['%.6f (%.2f%%)' % (row[p + '_median_seconds'], row[p + '_median_pct']) for p in PHASES]
        values.append('%.6f (%.2f%%)' % (row['critical_rank_residual_median_seconds'], row['critical_rank_residual_median_pct']))
        phase_table += '| %s | %d | %.6f | %s |\n' % (row['variant'].upper(), row['t'], row['profile_kernel_median_seconds'], ' | '.join(values))
    w = plan['workload']
    context = ('Job `%s`; host `%s`; compiler `%s`; MPI `%s`.\n\n'
               'P=2; T=1,2,3,4,6; N=%d; D=%d; K=%d; seed=%d; iterations=%d; warmup=%d.\n\n') % (
                   audit['job_id'], audit['host'], audit['compiler'], audit['mpi_version'],
                   w['n'], w['d'], w['k'], w['seed'], w['iterations'], w['warmup'])
    numeric = ('SSE: %.12g–%.12g; max |SSE−V0|: %.6g; %d timing + %d profile records; %d repeats/configuration.\n\n') % (
        audit['sse_min'], audit['sse_max'], audit['max_sse_absolute_error_vs_v0'],
        audit['timing_records'], audit['profile_records'], plan['repeats'])
    introductions = {
        'analysis.md': ('# Atlas fixed-P thread scaling\n\n',
            'All workload, numerical, matrix and placement checks passed, including 20 small-data preflight '
            'runs with labels, centroids and both measurement modes. This is a new independent job; '
            'timings must not be compared directly with older jobs. V0 is a numerical reference only.\n\n'
            'Formal timings use only diagnostic=false timing records. Speedup is the same variant’s T=1 median '
            'divided by its T median; thread efficiency is speedup/T. Min–max ranges are not confidence intervals.\n\n',
            'Separate diagnostic profile samples are excluded from formal timing. Every sample attributes all phases '
            'to the rank with maximum kernel time (ties: smaller rank); percentages use that rank’s kernel time. '
            'Independent phase maxima across ranks cannot be summed. This is not a direct measurement of pure atomic '
            'waiting time. Cells below show median seconds and median percentages; their independent medians need not '
            'sum to the median kernel or 100%. Residual is kernel minus that rank’s phase sum.\n\n',
            'Raw inputs are read-only; rerun `python3 hpc/analyze-atlas-thread-scaling.py RESULT_DIRECTORY` to regenerate.\n'),
    }
    return {name: title + context + intro + numeric + timing_table + '\n' + explanation + phase_table + '\n' + ending
            for name, (title, intro, explanation, ending) in introductions.items()}


def analyze(directory):
    folder = Path(directory).resolve()
    plan = load(folder / 'study-plan.json')
    layout = load(folder / 'layout-plan.json')
    reference = load(folder / 'reference-large.json')
    validate_plan(plan, layout, reference)
    launcher = launcher_module()
    expected = {(v, t) for v in VARIANTS for t in THREADS}
    groups = {}
    seen_placements = set()
    environment = None
    all_rows = []
    for measurement in ('timing', 'profile'):
        rows = [decode(line) for line in (folder / (measurement + '.jsonl')).read_text().splitlines() if line.strip()]
        require(len(rows) == plan['expected_' + measurement + '_records'], 'Incomplete ' + measurement + ' records')
        grouped = defaultdict(list)
        for row in rows:
            require(type(row['p']) is int and type(row['t']) is int and row['p'] == 2
                    and (row['variant'], row['t']) in expected, 'Unexpected configuration')
            require(row['communication'] == 'allreduce' and row['mode'] == 'fixed'
                    and row['stop_reason'] == 'fixed_iterations', 'Nonfixed/allreduce measurement')
            require(row['measurement_mode'] == measurement and row['diagnostic'] is (measurement == 'profile'),
                    'Timing/profile measurement isolation failed')
            if measurement == 'timing':
                require('profile_ranks' not in row and 'profile_critical_rank' not in row,
                        'Rank profile injected into formal timing')
            require(not row.get('skew', False) and row.get('input', '') == '', 'Unexpected skew or external input')
            current_environment = tuple(row[key] for key in ('job_id', 'host', 'compiler', 'mpi_version'))
            require(all(isinstance(value, str) and value for value in current_environment), 'Missing job/environment')
            if environment is None:
                environment = current_environment
            require(current_environment == environment, 'Mixed job/compiler/MPI/host environment')
            require(row['host'] == layout['allocation']['host'], 'Host differs from layout allocation')
            if 'job_id' in layout['allocation']:
                require(row['job_id'] == layout['allocation']['job_id'], 'Job differs from layout allocation')
            for key in WORKLOAD:
                integer(row[key], key)
                require(row[key] == plan['workload'][key], 'Workload mismatch: ' + key)
            integer(row['requested_iterations'], 'requested_iterations', minimum=1)
            require(row['requested_iterations'] == row['iterations'], 'Fixed iteration count mismatch')
            for key in ('data_fingerprint', 'init_indices', 'counts'):
                require(row[key] == reference[key], 'Numerical reference mismatch: ' + key)
            validate_counts(row)
            finite(row['sse'], 'SSE')
            require(math.isclose(row['sse'], reference['sse'], rel_tol=1e-10, abs_tol=1e-10), 'SSE reference mismatch')
            finite(row['kernel_seconds'], 'kernel_seconds', positive=True)
            integer(row['repeat'], 'repeat')
            require(row['repeat'] < plan['repeats'], 'Repeat outside study plan')
            if measurement == 'profile':
                validate_profile(row)
            require(row['placement_id'] not in seen_placements, 'Duplicate placement identifier')
            validate_placement(folder, row, layout, launcher)
            seen_placements.add(row['placement_id'])
            grouped[row['variant'], row['t']].append(row)
        require(set(grouped) == expected, 'Incomplete configuration matrix')
        for key, values in grouped.items():
            require(sorted(row['repeat'] for row in values) == list(range(plan['repeats'])),
                    'Missing/duplicate repeat: ' + str(key))
        groups[measurement] = grouped
        all_rows.extend(rows)
    actual_directories = {path.name for path in (folder / 'placements').iterdir() if path.is_dir()}
    require(actual_directories == seen_placements, 'Placement directories do not match measurement matrix')
    preflight = validate_preflight(folder, layout, launcher, environment, seen_placements)
    summaries, phases = [], []
    for variant, t in sorted(expected):
        values = [row['kernel_seconds'] for row in groups['timing'][variant, t]]
        median = statistics.median(values)
        baseline = statistics.median(row['kernel_seconds'] for row in groups['timing'][variant, 1])
        summaries.append(dict(p=2, t=t, variant=variant, repeats=plan['repeats'], median_seconds=median,
                              min_seconds=min(values), max_seconds=max(values),
                              speedup_vs_same_variant_t1=baseline / median, thread_efficiency=baseline / median / t))
        critical = [validate_profile(row) for row in groups['profile'][variant, t]]
        phase = dict(p=2, t=t, variant=variant, repeats=plan['repeats'],
                     profile_kernel_median_seconds=statistics.median(rank['kernel_seconds'] for rank in critical))
        for name in PHASES:
            phase[name + '_median_seconds'] = statistics.median(rank['phase_seconds'][name] for rank in critical)
            phase[name + '_median_pct'] = statistics.median(100 * rank['phase_seconds'][name] / rank['kernel_seconds'] for rank in critical)
        residuals = [max(0.0, rank['kernel_seconds'] - sum(rank['phase_seconds'][p] for p in PHASES)) for rank in critical]
        phase['critical_rank_residual_median_seconds'] = statistics.median(residuals)
        phase['critical_rank_residual_median_pct'] = statistics.median(100 * residual / rank['kernel_seconds']
                                                                     for rank, residual in zip(critical, residuals))
        phases.append(phase)
    audit = dict(study='thread-scaling', p=2, job_id=environment[0], host=environment[1], compiler=environment[2],
                 mpi_version=environment[3], records=len(all_rows), timing_records=50, profile_records=50,
                 configurations=10, repeats=5, completeness='pass', numerical_check='pass', placement_check='pass',
                 phase_attribution_note=PHASE_NOTE, identical_counts=True,
                 sse_min=min(row['sse'] for row in all_rows), sse_max=max(row['sse'] for row in all_rows),
                 max_sse_absolute_error_vs_v0=max(abs(row['sse'] - reference['sse']) for row in all_rows),
                 formal_rank_records=100, profile_rank_records=100, preflight_records=len(preflight),
                 preflight_rank_records=2 * len(preflight), preflight_check='pass', small_case_errors=preflight,
                 source_sha256={str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in sorted(folder.rglob('*')) if path.is_file() and path.name not in OUTPUTS})
    contents = {'thread-scaling-summary.csv': csv_text(summaries), 'phase-summary.csv': csv_text(phases),
                'analysis.audit.json': json.dumps(audit, indent=2, allow_nan=False) + '\n'}
    reports = make_reports(audit, plan, summaries, phases)
    contents.update({name: text for name, text in reports.items() if name == 'analysis.md'})
    # All validation and serialization finish before touching any generated output.
    for name, content in contents.items():
        (folder / name).write_text(content)
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, metavar='RESULT_DIRECTORY')
    args = parser.parse_args()
    try:
        audit = analyze(args.directory)
    except (ValueError, KeyError, TypeError, OSError, ImportError) as error:
        print('Analysis rejected: %s' % error, file=sys.stderr)
        return 1
    print(json.dumps({key: audit[key] for key in ('records', 'timing_records', 'profile_records',
                                               'completeness', 'numerical_check', 'placement_check')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
