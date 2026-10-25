#!/usr/bin/env python3
"""Run paired thread/communication studies with the Atlas placement launcher."""
from collections import defaultdict
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shlex
import statistics
import subprocess
import sys

DATA_SPEC = json.loads(Path(__file__).with_name('atlas-data-spec.json').read_text())
SEED = DATA_SPEC['seed']
WARMUP = DATA_SPEC['warmup']


def configurations(kind, processes):
    if kind not in ('threads', 'communication'):
        raise ValueError('Unknown study kind')
    if not processes or len(processes) != len(set(processes)):
        raise ValueError('Process counts must be nonempty and unique')
    rows = []
    for p in processes:
        if p not in (1, 2, 3, 4, 6, 12):
            raise ValueError('Process counts must divide the 12-core allocation')
        choices = [('v2', 'allreduce'), ('v3', 'allreduce')] if kind == 'threads' else [
            ('v3', 'allreduce'), ('v3', 'reduce-bcast')]
        rows.extend(dict(p=p, t=12//p, variant=v, communication=c) for v, c in choices)
    return rows


def numerical_errors(reference, row, dump=False):
    for key in ('n', 'd', 'k', 'seed', 'iterations', 'warmup', 'data_fingerprint', 'init_indices'):
        if row[key] != reference[key]:
            raise ValueError('Numerical reference mismatch: ' + key)
    if len(row['counts']) != row['k'] or sum(row['counts']) != row['n'] or any(c < 0 for c in row['counts']):
        raise ValueError('Invalid cluster counts')
    if not math.isfinite(row['sse']) or row['sse'] < 0 or not math.isclose(row['sse'], reference['sse'], rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError('SSE differs from the serial reference')
    result = dict(sse_absolute_error=abs(row['sse']-reference['sse']),
                  sse_scaled_error=abs(row['sse']-reference['sse'])/max(1.0,abs(reference['sse'])),
                  identical_counts=row['counts']==reference['counts'])
    if dump:
        if row['labels'] != reference['labels'] or not result['identical_counts']:
            raise ValueError('Small-data labels/counts differ')
        if len(row['centers']) != len(reference['centers']):
            raise ValueError('Centroid array sizes differ')
        pairs = list(zip(row['centers'], reference['centers']))
        if not all(math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10) for a,b in pairs):
            raise ValueError('Centroids differ from the serial reference')
        result['max_centroid_absolute_error'] = max(abs(a-b) for a,b in pairs)
        result['max_centroid_scaled_error'] = max(abs(a-b)/max(1.0,abs(b)) for a,b in pairs)
    return result


def write_json(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write('\n')


def run_json(command, path):
    proc = subprocess.run(command, text=True, capture_output=True, timeout=300)
    path.with_suffix('.stderr.log').write_text(shlex.join(command)+'\n'+proc.stderr)
    path.write_text(proc.stdout)
    if proc.returncode:
        raise RuntimeError('Command failed; see ' + str(path.with_suffix('.stderr.log')))
    return json.loads(proc.stdout)


def run(args, config):
    work = Path(__file__).resolve().parent
    folder = args.directory.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    plan_path = folder/'layout-plan.json'
    plan = json.loads(plan_path.read_text())
    spec = importlib.util.spec_from_file_location('hybrid',work/'atlas-hybrid-launch.py')
    hybrid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hybrid)
    execution_order = args.processes.copy()
    random.Random(2026).shuffle(execution_order)
    write_json(folder/'study-plan.json', dict(study=args.kind, configurations=config,
               workload=dict(n=args.n,d=args.d,k=args.k,seed=SEED,iterations=args.iterations,warmup=WARMUP),
               repeats=args.repeats, expected_records=len(config)*args.repeats,
               process_block_order=execution_order, order_note='Both strategies interleaved within each P/T block'))
    launcher = [sys.executable,str(work/'atlas-hybrid-launch.py'),'run','--plan',str(plan_path),
                '--p','{p}','--t','{t}','--probe',str(work/'build/atlas-thread-probe'),
                '--output',str(folder/'placements'),'--nodefile',str(args.nodefile),'--']
    small_args = ['--n','37','--d','3','--k','4','--seed',str(SEED),'--iterations','5','--warmup',str(WARMUP),'--dump']
    small = run_json([str(work/'build/kmeans_serial')]+small_args,folder/'reference-small.json')
    errors = []
    for c in config:
        cmd = [part.format(p=c['p'],t=c['t']) for part in launcher]
        # Keep correctness probes distinct from the formal placement records.
        cmd[cmd.index('--output')+1] = str(folder/'preflight-placements')
        cmd += [str(work/'build/kmeans_mpi')]+small_args+['--variant',c['variant'],
                 '--threads',str(c['t']),'--comm',c['communication']]
        name = 'preflight-p%d-%s-%s.json'%(c['p'],c['variant'],c['communication'])
        row = run_json(cmd,folder/name)
        if (row['p'],row['t'],row['variant'],row['communication']) != (c['p'],c['t'],c['variant'],c['communication']):
            raise ValueError('Preflight launched the wrong configuration')
        errors.append(dict(c, **numerical_errors(small,row,dump=True)))
    write_json(folder/'preflight-check.json',dict(numerical_check='pass',configurations=len(config),errors=errors))
    baseline_cpu = plan['configurations']['12']['ranks'][0][0]
    large = run_json(['taskset','--cpu-list',str(baseline_cpu),str(work/'build/kmeans_serial'),
                      '--n',str(args.n),'--d',str(args.d),'--k',str(args.k),'--seed',str(SEED),
                      '--iterations',str(args.iterations),'--warmup',str(WARMUP)],folder/'reference-large.json')
    # This single V0 run is a numerical reference, not a repeated timing baseline.
    raw_files = []
    for p in execution_order:
        raw = folder/('raw-p%d.jsonl'%p)
        cmd = [sys.executable,str(work/'scripts/benchmark.py'),'--suite',args.kind,'--processes',str(p),
               '--threads',str(12//p),'--n',str(args.n),'--d',str(args.d),'--k',str(args.k),
               '--iterations',str(args.iterations),'--warmup',str(WARMUP),'--seed',str(SEED),'--repeats',str(args.repeats),
               '--timeout','300','--launcher',shlex.join(launcher),'--output',str(raw)]
        subprocess.run(cmd,check=True)
        raw_files.append(raw)
    rows = [json.loads(line) for raw in raw_files for line in raw.read_text().splitlines() if line.strip()]
    expected = {(c['p'],c['t'],c['variant'],c['communication']) for c in config}
    groups = defaultdict(list)
    numeric = []
    if len(rows) != len(config)*args.repeats or len({r['placement_id'] for r in rows}) != len(rows):
        raise ValueError('Incomplete/duplicate measurements or placement IDs')
    for row in rows:
        key = (row['p'],row['t'],row['variant'],row['communication'])
        groups[key].append(row)
        if row['nodes'] != 1 or row['mode'] != 'fixed' or row['diagnostic'] or row['p']*row['t'] != 12:
            raise ValueError('Unexpected measurement mode or resources')
        if (row['n'],row['d'],row['k'],row['seed'],row['iterations'],row['warmup']) != (args.n,args.d,args.k,SEED,args.iterations,WARMUP):
            raise ValueError('Unexpected measurement workload')
        error = numerical_errors(large,row)
        numeric.append(dict(placement_id=row['placement_id'],repeat=row['repeat'],p=row['p'],t=row['t'],
                            variant=row['variant'],communication=row['communication'],**error))
        directory = folder/'placements'/row['placement_id']
        records = [json.loads((directory/('rank-%d.json'%r)).read_text()) for r in range(row['p'])]
        hybrid.verify_records(plan,row['p'],row['t'],records)
        if row['placement_check'] != 'pass' or json.loads((directory/'check.json').read_text())['placement_check'] != 'pass':
            raise ValueError('Placement verification missing')
    if set(groups) != expected or any(sorted(r['repeat'] for r in group) != list(range(args.repeats)) for group in groups.values()):
        raise ValueError('Configuration/repetition coverage differs from plan')
    write_json(folder/'numerical-errors.json',numeric)
    with (folder/'raw.jsonl').open('x') as output:
        for raw in raw_files:
            output.write(raw.read_text())
    subprocess.run([sys.executable,str(work/'scripts/summarize.py'),str(folder/'raw.jsonl'),
                    '--output',str(folder/'summary.csv')],check=True)
    comparisons = []
    for p in args.processes:
        choices = [c for c in config if c['p'] == p]
        a,b = [groups[(c['p'],c['t'],c['variant'],c['communication'])] for c in choices]
        def stats(group):
            times = [r['kernel_seconds'] for r in group]
            return dict(median=statistics.median(times),minimum=min(times),maximum=max(times))
        first,second = stats(a),stats(b)
        comparisons.append(dict(p=p,t=12//p,first=choices[0],second=choices[1],
                                first_seconds=first,second_seconds=second,
                                second_speedup_vs_first=first['median']/second['median'],
                                cross_socket_ranks=plan['configurations'][str(p)]['cross_socket_ranks']))
    write_json(folder/'comparisons.json',comparisons)
    check = dict(study=args.kind,records=len(rows),configurations=len(config),repeats=args.repeats,
                 numerical_check='pass',placement_check='pass',identical_counts=all(e['identical_counts'] for e in numeric),
                 job_id=os.environ.get('PBS_JOBID','unset'))
    write_json(folder/'experiment-check.json',check)
    print(json.dumps(check))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=['threads','communication'],required=True)
    parser.add_argument('--processes',default=','.join(map(str,DATA_SPEC['default_processes'])))
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--nodefile',type=Path)
    parser.add_argument('--n',type=int,default=DATA_SPEC['n'])
    parser.add_argument('--d',type=int,default=DATA_SPEC['d'])
    parser.add_argument('--k',type=int,default=DATA_SPEC['k'])
    parser.add_argument('--iterations',type=int,default=DATA_SPEC['iterations'])
    parser.add_argument('--repeats',type=int,default=DATA_SPEC['repeats'])
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    try:
        args.processes = [int(x) for x in args.processes.split(',')]
        config = configurations(args.kind,args.processes)
        if min(args.n,args.d,args.k,args.iterations,args.repeats) < 1 or args.k > args.n:
            raise ValueError('Invalid workload')
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps(dict(study=args.kind,configurations=config,repeats=args.repeats,
                              records=len(config)*args.repeats,n=args.n,d=args.d,k=args.k,
                              seed=SEED,warmup=WARMUP,iterations=args.iterations),indent=2))
    else:
        if args.directory is None or args.nodefile is None:
            parser.error('--directory and --nodefile are required')
        run(args,config)


if __name__ == '__main__':
    main()
