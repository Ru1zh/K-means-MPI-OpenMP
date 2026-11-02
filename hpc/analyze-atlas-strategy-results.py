#!/usr/bin/env python3
"""Audit downloaded paired strategy studies; preserve raw records and regenerate analysis."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import sys
import tarfile


def load(path):
    return json.loads(path.read_text())


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def assert_errors(actual,saved):
    for key,value in actual.items():
        if isinstance(value,float):
            assert math.isclose(value,saved[key],rel_tol=1e-13,abs_tol=1e-25),(key,value,saved[key])
        else:
            assert value==saved[key],(key,value,saved[key])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    folder=args.directory.resolve()
    hpc=Path(__file__).resolve().parent
    check=load(folder/'experiment-check.json');kind=check['study']
    assert kind in ['threads','communication']
    with tarfile.open(hpc/('project3-atlas-%s.tar.gz'%kind)) as tar:
        prefix='project3-atlas-%s/'%kind
        for name in ['atlas-hybrid-launch.py','atlas-strategy-study.py','atlas-data-spec.json']:
            assert tar.extractfile(prefix+name).read()==(hpc/name).read_bytes(),name
        manifest=tar.extractfile(prefix+'source-manifest.sha256').read().decode()
        expected_sources={line.split('  ',1)[1] for line in manifest.splitlines()}
    verified_sources={}
    for line in (folder/'source-check.txt').read_text().splitlines():
        name,status=line.rsplit(': ',1)
        assert status=='OK' and name not in verified_sources
        verified_sources[name]=status
    assert set(verified_sources)==expected_sources
    hybrid=module('hybrid',hpc/'atlas-hybrid-launch.py')
    study=module('study',hpc/'atlas-strategy-study.py')
    plan=load(folder/'study-plan.json');layout=load(folder/'layout-plan.json');allocation=load(folder/'allocation.json')
    assert layout==hybrid.build_plan(allocation)
    selected_processes=list(dict.fromkeys(c['p'] for c in plan['configurations']))
    assert plan['configurations']==study.configurations(kind,selected_processes)
    expected={(c['p'],c['t'],c['variant'],c['communication']) for c in plan['configurations']}
    assert (folder/'status.txt').read_text().strip()=='exit_status=0'
    pbs=(folder/'pbs-job.txt').read_text()
    assert re.search(r'^\s*Exit_status = 0$',pbs,re.M)
    assert re.search(r'^\s*job_state = F$',pbs,re.M)
    rows=[json.loads(line) for line in (folder/'raw.jsonl').read_text().splitlines() if line.strip()]
    assert len(rows)==plan['expected_records']==check['records']
    assert len({r['placement_id'] for r in rows})==len(rows)
    assert len(list((folder/'placements').iterdir()))==len(rows)
    reference=load(folder/'reference-large.json')
    small=load(folder/'reference-small.json')
    manifest={line.split()[1]:line.split()[0] for line in (folder/'binaries.sha256').read_text().splitlines()}
    error_map={r['placement_id']:r for r in load(folder/'numerical-errors.json')}
    assert len(error_map)==len(rows)
    groups=defaultdict(list);placements={};error_rows=[]
    rank_count=thread_count=0
    for row in rows:
        p,t=row['p'],row['t'];key=(p,t,row['variant'],row['communication'])
        assert key in expected and p*t==12
        assert row['nodes']==1 and row['mode']=='fixed' and not row['diagnostic'] and not row['skew']
        assert row['input']=='' and row['generator']==reference['generator']
        assert row['stop_reason']=='fixed_iterations' and row['requested_iterations']==row['iterations']
        assert row['host']==allocation['host'] and row['job_id']==allocation['job_id']==check['job_id']
        assert row['binary_sha256']==manifest['build/kmeans_mpi']
        for field in ['n','d','k','seed','iterations','warmup']:
            assert row[field]==plan['workload'][field]
        assert math.isfinite(row['kernel_seconds']) and row['kernel_seconds']>0
        errors=study.numerical_errors(reference,row)
        assert errors['identical_counts']
        assert_errors(errors,error_map[row['placement_id']])
        error_rows.append(errors)
        directory=folder/'placements'/row['placement_id']
        launch=load(directory/'launch.json')
        command=row['command'][row['command'].index('--')+1:]
        assert launch['algorithm_command']==command and (launch['p'],launch['t'])==(p,t)
        records=[load(directory/('rank-%d.json'%r)) for r in range(p)]
        assert hybrid.verify_records(layout,p,t,records)==load(directory/'check.json')
        assert row['placement_check']=='pass'
        signature=[]
        for record in records:
            assert record['command']==command
            assert record['thread_probe']['openmp']==201511
            signature.append((record['rank'],record['rank_cpus'],record['thread_probe']['threads']))
        # Both strategies and every repeat must use the same per-rank and per-thread layout.
        assert placements.setdefault(p,signature)==signature
        rank_count+=len(records)
        thread_count+=sum(len(r['thread_probe']['threads']) for r in records)
        groups[key].append(row)
    assert set(groups)==expected
    for group in groups.values():
        assert sorted(r['repeat'] for r in group)==list(range(plan['repeats']))
    for p in plan['process_block_order']:
        subset=[r for r in rows if r['p']==p]
        assert len({r['run_id'] for r in subset})==1
        for repeat in range(plan['repeats']):
            assert len([r for r in subset if r['repeat']==repeat])==2
    expected_raw=''.join((folder/('raw-p%d.jsonl'%p)).read_text() for p in plan['process_block_order'])
    assert (folder/'raw.jsonl').read_text()==expected_raw
    with (folder/'summary.csv').open() as source:
        summaries={(int(r['p']),int(r['t']),r['variant'],r['communication']):r for r in csv.DictReader(source)}
    assert set(summaries)==expected
    for key,group in groups.items():
        times=[r['kernel_seconds'] for r in group];saved=summaries[key]
        assert int(saved['repeats'])==plan['repeats']
        for field,value in [('median_seconds',statistics.median(times)),('min_seconds',min(times)),('max_seconds',max(times))]:
            assert math.isclose(float(saved[field]),value,rel_tol=1e-14)
    small_errors=[]
    saved_small=load(folder/'preflight-check.json')
    for c in plan['configurations']:
        name='preflight-p%d-%s-%s.json'%(c['p'],c['variant'],c['communication'])
        row=load(folder/name)
        assert (row['p'],row['t'],row['variant'],row['communication'])==(c['p'],c['t'],c['variant'],c['communication'])
        errors=study.numerical_errors(small,row,dump=True)
        matching=next(r for r in saved_small['errors'] if all(r[k]==c[k] for k in ['p','t','variant','communication']))
        assert_errors(errors,matching)
        directory=folder/'preflight-placements'/row['placement_id']
        records=[load(directory/('rank-%d.json'%r)) for r in range(c['p'])]
        hybrid.verify_records(layout,c['p'],c['t'],records)
        small_errors.append(dict(c,**errors))
    comparisons=[];table=[]
    saved_comparisons={c['p']:c for c in load(folder/'comparisons.json')}
    for p in sorted(placements):
        configs=[c for c in plan['configurations'] if c['p']==p]
        a,b=[groups[(c['p'],c['t'],c['variant'],c['communication'])] for c in configs]
        def stats(group):
            ts=[r['kernel_seconds'] for r in group]
            return dict(median=statistics.median(ts),minimum=min(ts),maximum=max(ts),times=ts)
        first,second=stats(a),stats(b)
        ratio=first['median']/second['median'];reduction=100*(1-second['median']/first['median'])
        pairs={r['repeat']:r['kernel_seconds'] for r in a}
        paired_ratios=[pairs[r['repeat']]/r['kernel_seconds'] for r in sorted(b,key=lambda r:r['repeat'])]
        saved=saved_comparisons[p]
        for key,actual in [('first_seconds',first),('second_seconds',second)]:
            for field in ['median','minimum','maximum']:
                assert math.isclose(saved[key][field],actual[field],rel_tol=1e-14)
        assert math.isclose(saved['second_speedup_vs_first'],ratio,rel_tol=1e-14)
        comparisons.append(dict(p=p,t=12//p,first=first,second=second,speedup=ratio,time_reduction_pct=reduction,
                                paired_speedups=paired_ratios,second_always_faster=all(r>1 for r in paired_ratios),
                                ranges_separated=second['maximum']<first['minimum'],
                                cross_socket_ranks=layout['configurations'][str(p)]['cross_socket_ranks']))
        table.append('| %d×%d | %.6f | %.6f–%.6f | %.6f | %.6f–%.6f | %.3f× | %.2f%% |'%
                     (p,12//p,first['median'],first['minimum'],first['maximum'],second['median'],second['minimum'],second['maximum'],ratio,reduction))
    original_files=[p for p in folder.rglob('*') if p.is_file() and p.name not in ['analysis.audit.json','analysis.md']]
    sse_min=min(r['sse'] for r in rows);sse_max=max(r['sse'] for r in rows)
    audit=dict(job_id=allocation['job_id'],study=kind,records=len(rows),configurations=len(expected),
               repeats=plan['repeats'],source_check='pass',checked_source_files=len(expected_sources),
               completeness='pass',csv_recalculation='pass',comparisons_recalculation='pass',
               numerical_check='pass',placement_check='pass',formal_rank_records=rank_count,
               formal_thread_probe_records=thread_count,allowed_os_cpus=allocation['allowed_cpus'],
               identical_counts=True,sse_min=sse_min,sse_max=sse_max,
               max_sse_absolute_error_vs_v0=max(r['sse_absolute_error'] for r in error_rows),
               max_sse_scaled_error_vs_v0=max(r['sse_scaled_error'] for r in error_rows),
               small_case_errors=small_errors,comparisons=comparisons,
               source_sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(original_files)})
    (folder/'analysis.audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    title='V2/V3 thread accumulation strategy' if kind=='threads' else 'V3 communication strategy'
    first_name='V2 atomic updates' if kind=='threads' else 'Allreduce'
    second_name='V3 private buffers' if kind=='threads' else 'Reduce+Bcast'
    job_date=datetime.fromisoformat(rows[0]['timestamp_utc']).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    favorable=all(c['ranges_separated'] for c in comparisons)
    intro=('In all %d configurations, every V3 run was faster than the corresponding V2 run, '
           'and the time ranges did not overlap.'%len(comparisons) if favorable and kind=='threads'
           else 'Differences for each configuration are shown below; min–max ranges are not confidence intervals.')
    trend=sorted(comparisons,key=lambda c:c['t'])
    increasing=all(b['speedup']>=a['speedup'] for a,b in zip(trend,trend[1:])) and len(trend)>1
    thread_ratios='; '.join('P=%d, T=%d: %.3f×'%(c['p'],c['t'],c['speedup']) for c in comparisons)
    interpretation=(('Median V2/V3 time ratios: '+thread_ratios+'. ')+
                    ('The benefit grows with thread count in this run, consistent with the design motivation of private buffers reducing shared atomic updates.' if increasing else 'The size of the strategy difference must be discussed for each P/T.')+
                    '\n\nProcess count also changes, so partitioning, communication and cache conditions change with it; this run did not record atomic wait time or hardware counters, so the full time difference cannot be attributed quantitatively to atomic contention. Decomposing the cause further requires separate profiling; diagnostic samples must not be mixed into formal timings.'
                    if kind=='threads' else 'Only the communication strategy changes at the same P/T; interpret differences together with the repeat ranges. The current results do not directly measure communication-phase overhead, so separate profiling is needed to analyse the bottleneck.')
    if kind=='communication':
        changes='; '.join('%d×%d: %+.2f%%'%(c['p'],c['t'],-c['time_reduction_pct']) for c in comparisons)
        overlap=all(max(c['first']['minimum'],c['second']['minimum'])<=min(c['first']['maximum'],c['second']['maximum']) for c in comparisons)
        interpretation+='\n\nMedian time change of Reduce+Bcast relative to Allreduce: '+changes+'.'
        if overlap:
            interpretation+=' The time ranges of both groups overlap in every configuration; this run does not provide enough evidence for a stable advantage of either communication strategy. The default Allreduce can be retained, but this choice should not be described as proof of superior performance.'
        interpretation+=' This run did not measure the reduction/broadcast phases separately, so similar kernel totals do not imply equal communication-phase times.'
    next_step=('Next, run the prepared communication comparison while keeping the same representative P/T.' if kind=='threads'
               else 'The main experimental data is complete; proceed to figures and report preparation. Add weak-scaling, profiling or multi-node experiments as the report requires.')
    env_line='%s, %s, Python %s.'%(
        rows[0].get('compiler','unknown'),
        str(rows[0].get('mpi_version','unknown')).split(',')[0],
        sys.version.split()[0])
    report='''# Atlas %s comparison

Job `%s`, %s (Singapore time), node `%s`. Strategy comparisons use only matched configurations within this job.

## Verification

- PBS and script exit status are 0; checksums for all %d uploaded source files passed.
- %d formal records in %d configurations, %d repeats each; raw shard files match the merged file, and the CSV and comparisons.json statistics were recomputed independently.
- Data fingerprint and initial centers match the V0 reference in this job; every formal run has identical cluster counts summing to 1000000.
- SSE ranges from %.12f to %.12f; maximum absolute error versus V0 is %.6g and scaled error %.3g, where scaled error is absolute error / max(1, abs(V0 SSE)).
- The selected small-data configuration matches on centers, labels, counts and SSE; details are in preflight-check.json and analysis.audit.json.
- %d rank records and %d OpenMP thread-probe records before formal launches were checked. Both strategies at the same P/T and all repeats use the same rank/thread CPU layout, with no overlap or out-of-range placement.

## Environment and scope

%s Fixed N=1000000, D=32, K=32, seed=42; 2 warmup iterations restore the initial centers before 20 measured iterations. All configurations use P×T=12 on a single node.

%s

## Performance

Times are median kernel_seconds; data generation, initialization, warmup, final evaluation and launch probes are excluded. The two strategies are interleaved within each P/T, with the order shuffled per repeat; P/T blocks run sequentially, so configurations are not globally interleaved.

| P×T | %s median (s) | min–max (s) | %s median (s) | min–max (s) | first / second time | second time reduction |
|---|---:|---:|---:|---:|---:|---:|
%s

A negative "second time reduction" means the second strategy had a longer median time in this run.

%s

%s

These ratios compare strategies under fixed resources; they are not strong-scaling speedups relative to serial. The large V0 run in this job is a single numerical check, not a repeated performance baseline.

## Limitations and next steps

Thread affinity comes from an independent OpenMP probe run before the algorithm; the wrapper then runs the algorithm with the same CPU mask and environment, and the algorithm separately checks the actual team size. These records are not live thread samples inside the timing loop.

Nodes, socket/NUMA placement and system state can differ between jobs; small differences between this V3 time and earlier mixed-workload jobs are not interpreted as optimization gains. No V0 time from another job is used to compute speedups.

Conclusions cover only the current synthetic data scale, node allocation and tested strategies. All raw records, build logs and placement records are retained; rerun HPC/analyze-atlas-strategy-results.py to recompute the analysis. %s
'''%(title,allocation['job_id'],job_date,allocation['host'],len(expected_sources),len(rows),len(expected),plan['repeats'],
       sse_min,sse_max,audit['max_sse_absolute_error_vs_v0'],audit['max_sse_scaled_error_vs_v0'],rank_count,thread_count,
       env_line,intro,first_name,second_name,'\n'.join(table),interpretation,layout_description(allocation,layout,selected_processes),next_step)
    (folder/'analysis.md').write_text(report)
    print(json.dumps(dict(job_id=allocation['job_id'],records=len(rows),numerical='pass',placement='pass',
                          rank_records=rank_count,thread_probe_records=thread_count,
                          speedups=[c['speedup'] for c in comparisons]),indent=2))


def layout_description(allocation,layout,selected_processes):
    cpus=allocation['allowed_cpus']
    sockets=sorted({r['socket'] for r in allocation['topology'].values()})
    cross={p:c['cross_socket_ranks'] for p,c in layout['configurations'].items() if int(p) in selected_processes}
    return ('This job was allocated OS CPUs `%s` and uses sockets %s overall. '
            'Cross-socket ranks for the tested configurations are `%s`. '
            'Distinguish "the whole job spans sockets" from "one rank\'s threads span sockets"; '
            'matched strategies keep the same layout.')%(
                ','.join(map(str,cpus)),','.join(map(str,sockets)),json.dumps(cross))


if __name__=='__main__':
    main()
