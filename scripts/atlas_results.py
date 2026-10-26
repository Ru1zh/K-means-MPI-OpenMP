"""Validate the recorded workload and derive report statistics without plotting libraries."""
from collections import defaultdict
import csv
import hashlib
import json
import math
import statistics

from reproduce_atlas import verify_bundle


FIGURES = [
    ('01_strong_runtime', 'Strong scaling: kernel runtime'),
    ('02_strong_scaling', 'Strong scaling: speedup and efficiency'),
    ('03_hybrid_layouts', 'Fixed 12-core MPI/OpenMP layouts'),
    ('04_thread_strategies', 'Thread accumulation: V2 versus V3'),
    ('05_communication', 'Global update: Allreduce versus Reduce+Bcast'),
]


def describe_times(times):
    if not times or any(not math.isfinite(t) or t <= 0 for t in times):
        raise ValueError('Kernel times must be finite and positive')
    return dict(repeats=len(times), median_seconds=statistics.median(times),
                min_seconds=min(times), max_seconds=max(times), times=list(times))


def compare(reference_median, candidate, cores=None):
    """Ratios use a fixed reference median; ranges are descriptive, not confidence intervals."""
    speedup = reference_median/candidate['median_seconds']
    return dict(reference_seconds=reference_median, speedup=speedup,
                efficiency=speedup/cores if cores else None,
                speedup_min=reference_median/candidate['max_seconds'],
                speedup_max=reference_median/candidate['min_seconds'],
                time_change_pct=100*(candidate['median_seconds']/reference_median-1),
                time_change_min_pct=100*(candidate['min_seconds']/reference_median-1),
                time_change_max_pct=100*(candidate['max_seconds']/reference_median-1))


def key(row):
    return row['variant'], row['p'], row['t'], row['communication']


def expected_configurations(kind):
    if kind == 'strong':
        return {('v0', 1, 1, 'allreduce')} | {('v3', p, 1, 'allreduce') for p in (1,2,3,4,6,12)}
    if kind == 'hybrid':
        return {('v3', p, 12//p, 'allreduce') for p in (1,2,3,4,6,12)}
    if kind == 'threads':
        return {(v, p, 12//p, 'allreduce') for p in (2,4,6) for v in ('v2','v3')}
    if kind == 'thread-scaling':
        return {(v, 2, t, 'allreduce') for t in (1,2,3,4,6) for v in ('v2','v3')}
    if kind == 'communication':
        return {('v3', p, 12//p, comm) for p in (2,4,6) for comm in ('allreduce','reduce-bcast')}
    raise ValueError('Unknown study: '+kind)


def summarize_study(kind, rows, workload):
    if not rows:
        raise ValueError('Empty study: '+kind)
    reference = rows[0]
    # V0 is compiled without MPI and records "none"; compare MPI versions among parallel rows.
    if len({r['mpi_version'] for r in rows if r['variant'] != 'v0'}) != 1:
        raise ValueError('Mixed MPI versions within job: '+kind)
    groups = defaultdict(list)
    for row in rows:
        for field in ('job_id','host','compiler'):
            if row[field] != reference[field]:
                raise ValueError('Mixed job/environment in %s: %s'%(kind, field))
        for field in ('n','d','k','seed','iterations','warmup'):
            if row[field] != workload[field]:
                raise ValueError('Workload mismatch: '+field)
        if row['requested_iterations'] != workload['iterations'] or row['stop_reason'] != 'fixed_iterations':
            raise ValueError('Unexpected iteration count or stop reason')
        if row['mode'] != 'fixed' or row['diagnostic'] or row['skew'] or row['nodes'] != 1 or row['input']:
            raise ValueError('Unmatched measurement mode')
        for field in ('data_fingerprint','init_indices','counts'):
            if row[field] != reference[field]:
                raise ValueError('Numerical/input mismatch: '+field)
        if sum(row['counts']) != row['n'] or len(row['counts']) != row['k']:
            raise ValueError('Invalid cluster counts')
        if not math.isfinite(row['sse']) or not math.isclose(row['sse'], reference['sse'], rel_tol=1e-10):
            raise ValueError('SSE mismatch')
        groups[key(row)].append(row)
    if set(groups) != expected_configurations(kind):
        raise ValueError('Unexpected configuration matrix: '+kind)
    result = []
    for config, group in sorted(groups.items()):
        group.sort(key=lambda r:r['repeat'])
        if [r['repeat'] for r in group] != list(range(workload['repeats'])):
            raise ValueError('Missing or duplicate repeat: '+str(config))
        variant,p,t,comm = config
        item = dict(study=kind, job_id=reference['job_id'], host=reference['host'],
                    variant=variant, p=p, t=t, communication=comm)
        item.update({f:reference[f] for f in ('n','d','k','seed','iterations','warmup','data_fingerprint')})
        item.update(describe_times([r['kernel_seconds'] for r in group]))
        result.append(item)
    return result


def build_results(bundle):
    manifest, file_count = verify_bundle(bundle)
    groups = []
    for kind, study in manifest['studies'].items():
        raw = bundle/study['directory']/study['raw_file']
        rows = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        groups.extend(summarize_study(kind, rows, manifest['workload']))
    comparisons = []
    for kind in manifest['studies']:
        selected = [r for r in groups if r['study']==kind]
        lookup = {key(r):r for r in selected}
        for row in selected:
            if kind == 'strong':
                if row['variant'] == 'v0':
                    continue
                reference = lookup[('v0',1,1,'allreduce')]
                reference_name = 'V0 serial'
            elif kind == 'hybrid':
                reference = lookup[('v3',12,1,'allreduce')]
                reference_name = 'V3 12x1'
            elif kind == 'threads':
                if row['variant'] != 'v3':
                    continue
                reference = lookup[('v2',row['p'],row['t'],'allreduce')]
                reference_name = 'V2 same layout'
            elif kind == 'thread-scaling':
                reference = lookup[(row['variant'],2,1,'allreduce')]
                reference_name = 'Same variant P=2 T=1'
            else:
                if row['communication'] != 'reduce-bcast':
                    continue
                reference = lookup[('v3',row['p'],row['t'],'allreduce')]
                reference_name = 'Allreduce same layout'
            comparison = {f:row[f] for f in ('study','job_id','variant','p','t','communication')}
            comparison['reference'] = reference_name
            cores = row['t'] if kind == 'thread-scaling' else row['p']*row['t'] if kind=='strong' else None
            comparison.update(compare(reference['median_seconds'], row, cores))
            comparison['ranges_overlap'] = max(reference['min_seconds'],row['min_seconds']) <= min(reference['max_seconds'],row['max_seconds'])
            comparison['speedup_vs_v3_p1'] = None
            comparison['efficiency_vs_v3_p1'] = None
            if kind == 'strong':
                speedup = lookup[('v3',1,1,'allreduce')]['median_seconds']/row['median_seconds']
                comparison.update(speedup_vs_v3_p1=speedup, efficiency_vs_v3_p1=speedup/row['p'])
            comparisons.append(comparison)
    return dict(workload=manifest['workload'], formal_records=manifest['formal_records'],
                diagnostic_records=manifest.get('diagnostic_records', 0),
                verified_files=file_count, groups=groups, comparisons=comparisons,
                input_manifest_sha256=hashlib.sha256((bundle/'checksums.sha256').read_bytes()).hexdigest())


def write_csv(path, rows):
    with path.open('w', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def write_tables(output, results):
    configurations = []
    for row in results['groups']:
        item = {k:v for k,v in row.items() if k != 'times'}
        item.update({'repeat_%d_seconds'%i:value for i,value in enumerate(row['times'])})
        configurations.append(item)
    write_csv(output/'configuration_summary.csv', configurations)
    write_csv(output/'comparison_summary.csv', results['comparisons'])
    (output/'statistics.json').write_text(json.dumps(results, indent=2, allow_nan=False)+'\n')
