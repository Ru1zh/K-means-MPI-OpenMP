#!/usr/bin/env python3
"""Run one new Atlas P=2 study; ordinary and diagnostic launches stay separate."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shlex
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WORK = HERE if (HERE/'src').is_dir() else HERE.parent
THREADS = [1, 2, 3, 4, 6]
WORKLOAD = dict(n=1000000, d=32, k=32, seed=42, iterations=20, warmup=2)


def study_plan():
    order = {}
    rng = random.Random(2026)
    for mode in ['timing', 'profile']:
        order[mode] = []
        for repeat in range(5):
            block = [dict(variant=v, t=t, repeat=repeat) for t in THREADS for v in ['v2', 'v3']]
            rng.shuffle(block)
            order[mode].extend(block)
    return dict(study='thread-scaling', p=2, threads=THREADS, workload=WORKLOAD,
                repeats=5, expected_timing_records=50, expected_profile_records=50,
                execution_order=order,
                order_note='Randomized within repetition; normal launches precede separate profile launches',
                reference_policy='V0 validates numerics only; timing baseline is same-variant P=2,T=1')


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def run_json(command, path):
    """Save exact stdout/stderr before validation; do not overwrite failed attempts."""
    with path.open('x') as stdout, path.with_suffix('.stderr.log').open('x') as stderr:
        stderr.write(shlex.join(command)+'\n')
        stderr.flush()
        result = subprocess.run(command, text=True, stdout=stdout, stderr=stderr, timeout=300)
    if result.returncode:
        raise RuntimeError('Command failed; see '+str(path.with_suffix('.stderr.log')))
    return json.loads(path.read_text())


def check_numerical(reference, row, dump=False):
    for key in ['n','d','k','seed','iterations','warmup','data_fingerprint','init_indices','counts']:
        if row[key] != reference[key]:
            raise ValueError('Numerical reference mismatch: '+key)
    if (len(row['counts']) != row['k'] or sum(row['counts']) != row['n'] or
            any(type(c) is not int or c < 0 for c in row['counts'])):
        raise ValueError('Invalid cluster counts')
    if not math.isfinite(row['sse']) or row['sse'] < 0 or not math.isclose(row['sse'], reference['sse'], rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError('Invalid SSE or different numerical result')
    if dump:
        if row['labels'] != reference['labels'] or len(row['centers']) != len(reference['centers']):
            raise ValueError('Small-data labels/centroid sizes differ')
        if not all(math.isfinite(a) and math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10)
                   for a,b in zip(row['centers'],reference['centers'])):
            raise ValueError('Small-data centroids differ')


def workload_args(workload):
    return [part for key, value in workload.items() for part in ['--'+key, str(value)]]


def run(args):
    folder = args.directory.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    job = os.environ.get('PBS_JOBID')
    if not job:
        raise ValueError('Run this study inside the supplied PBS job; --dry-run needs no Atlas access')
    plan = study_plan()
    # Exclusive creation prevents rerunning into a partial or completed job directory.
    write_json(folder/'study-plan.json', plan)
    layout = json.loads((folder/'layout-plan.json').read_text())
    launcher = [sys.executable, str(HERE/'atlas-thread-scaling-launch.py'), 'run',
                '--plan', str(folder/'layout-plan.json'), '--t', '{t}',
                '--probe', str(WORK/'build/atlas-thread-probe'),
                '--output', '{output}', '--nodefile', str(args.nodefile.resolve()), '--']
    serial, parallel = str(WORK/'build/kmeans_serial'), str(WORK/'build/kmeans_mpi')
    baseline_cpu = layout['reserved_ranks'][0][0]
    small = dict(n=37,d=3,k=4,seed=42,iterations=5,warmup=2)
    reference_small = run_json(['taskset','--cpu-list',str(baseline_cpu),serial]+workload_args(small)+['--dump'],
                               folder/'reference-small.json')
    def command(cell, mode, workload, preflight=False):
        output = folder/('preflight-placements' if preflight else 'placements')
        result = [part.format(t=cell['t'],output=output) for part in launcher]
        result += [parallel]+workload_args(workload)+['--variant',cell['variant'],'--threads',str(cell['t']),
                                                     '--comm','allreduce']
        if mode == 'profile':
            result.append('--profile')
        if preflight:
            result.append('--dump')
        return result
    # Both measurement modes receive small-data checks, outside formal timing streams.
    for mode in ['timing','profile']:
        for t in THREADS:
            for variant in ['v2','v3']:
                cell = dict(t=t,variant=variant)
                row = run_json(command(cell,mode,small,True),folder/('preflight-%s-%s-t%d.json'%(mode,variant,t)))
                if (row['p'],row['t'],row['variant'],row['diagnostic']) != (2,t,variant,mode=='profile'):
                    raise ValueError('Incorrect preflight configuration')
                check_numerical(reference_small,row,dump=True)
    write_json(folder/'preflight-check.json',dict(numerical_check='pass',configurations=20))
    reference = run_json(['taskset','--cpu-list',str(baseline_cpu),serial]+workload_args(WORKLOAD),folder/'reference-large.json')
    # A single serial run is a numerical oracle, never a performance baseline.
    digest = hashlib.sha256(Path(parallel).read_bytes()).hexdigest() if Path(parallel).exists() else None
    for mode in ['timing','profile']:
        with (folder/(mode+'.jsonl')).open('x') as stream:
            for index, cell in enumerate(plan['execution_order'][mode]):
                cmd = command(cell,mode,WORKLOAD)
                raw = folder/'launch-output'
                raw.mkdir(exist_ok=True)
                row = run_json(cmd,raw/('%s-%03d.json'%(mode,index)))
                if (row['p'],row['t'],row['variant'],row['communication'],row['mode'],row['diagnostic']) != (
                        2,cell['t'],cell['variant'],'allreduce','fixed',mode=='profile'):
                    raise ValueError('Incorrect formal configuration')
                check_numerical(reference,row)
                row.update(repeat=cell['repeat'],measurement_mode=mode,job_id=job,host=socket.gethostname(),
                           binary_sha256=digest,command=cmd)
                stream.write(json.dumps(row,allow_nan=False)+'\n')
                stream.flush()
                print('%s %d/50: %s T=%d'%(mode,index+1,cell['variant'],cell['t']),flush=True)
    result = dict(study='thread-scaling',timing_records=50,profile_records=50,job_id=job,
                  note='Run analyzer to validate all matrix, rank-profile and placement evidence')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--nodefile', type=Path)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(study_plan(),indent=2))
    else:
        if args.directory is None or args.nodefile is None:
            parser.error('--directory and --nodefile are required for an Atlas run')
        print(json.dumps(run(args),indent=2))


if __name__ == '__main__':
    main()
