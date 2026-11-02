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
    original_files=[p for p in folder.rglob('*') if p.is_file() and p.name not in ['analysis.audit.json','analysis.zh-CN.md']]
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
    title='V2/V3 线程累加策略' if kind=='threads' else 'V3 通信策略'
    first_name='V2 原子更新' if kind=='threads' else 'Allreduce'
    second_name='V3 私有缓冲' if kind=='threads' else 'Reduce+Bcast'
    job_date=datetime.fromisoformat(rows[0]['timestamp_utc']).astimezone(timezone(timedelta(hours=8))).date().isoformat()
    favorable=all(c['ranges_separated'] for c in comparisons)
    intro=('%d 种配比中，V3 的全部运行都快于对应 V2 的全部运行，耗时范围不重叠。'%len(comparisons) if favorable and kind=='threads'
           else '各配比的具体性能差异见下表；最小–最大范围不是置信区间。')
    trend=sorted(comparisons,key=lambda c:c['t'])
    increasing=all(b['speedup']>=a['speedup'] for a,b in zip(trend,trend[1:])) and len(trend)>1
    thread_ratios='；'.join('P=%d、T=%d：%.3f 倍'%(c['p'],c['t'],c['speedup']) for c in comparisons)
    interpretation=(('V2/V3 的耗时中位数比为：'+thread_ratios+'。')+
                    ('收益随本次线程数增大而增大的趋势，与私有缓冲减少共享原子更新的设计动机一致。' if increasing else '策略差异的大小需结合各 P/T 分别讨论。')+
                    '\n\n进程数也同时变化，数据分区、通信和缓存条件随之改变；本轮没有直接记录原子等待时间或硬件计数器，不能把全部时间差定量归因于原子竞争。若要进一步分解成因，应单独 profile，避免将诊断样本混入正式时间。'
                    if kind=='threads' else '相同 P/T 下只改变通信策略；应结合重复范围判断差异。当前结果不直接测量通信阶段的独立开销，需单独 profile 才能分析瓶颈。')
    if kind=='communication':
        changes='；'.join('%d×%d：%+.2f%%'%(c['p'],c['t'],-c['time_reduction_pct']) for c in comparisons)
        overlap=all(max(c['first']['minimum'],c['second']['minimum'])<=min(c['first']['maximum'],c['second']['maximum']) for c in comparisons)
        interpretation+='\n\nReduce+Bcast 相对 Allreduce 的中位耗时变化为：'+changes+'。'
        if overlap:
            interpretation+='各配比的两组耗时范围均重叠；本次没有足够依据认定一种通信策略存在稳定性能优势。可以保留默认 Allreduce，但不把这一选择描述为性能优越性的证明。'
        interpretation+='本轮没有单独测量归约/广播阶段，不能由内核总时间接近推出通信阶段本身耗时相同。'
    next_step=('下一步可以执行已准备的通信方式对照，继续保留相同的代表性 P/T。' if kind=='threads'
               else '主要实验数据已收齐，可以进入图表与报告整理；弱扩展、profile 和多节点实验按报告需要补充。')
    report='''# Atlas %s对照结果

作业 `%s`，%s（新加坡时间），节点 `%s`。仅使用本作业内匹配配置的时间进行策略对照。

## 核查结论

- PBS 和脚本退出状态均为 0；%d 个上传源文件的校验全部通过。
- %d 条正式记录，%d 组配置，每组 %d 次；原始分块文件与合并文件一致，CSV 和 comparisons.json 的统计均已独立重算。
- 数据指纹、初始中心与本作业内的 V0 数值参考匹配，所有正式运行的最终簇计数相同、总数为 1000000。
- SSE 范围为 %.12f 至 %.12f；相对 V0 的最大绝对误差 %.6g，缩放误差 %.3g。这里缩放误差为绝对误差/max(1,abs(V0 SSE))。
- 所选小数据配置的质心、标签、计数和 SSE 对照通过，具体误差在 preflight-check.json 与 analysis.audit.json 中。
- 核对 %d 份 rank 记录、%d 份正式启动前的 OpenMP 线程探测记录。相同 P/T 的两种策略和所有重复使用相同 rank/thread 核心布局，无重叠、无越界。

## 环境与比较范围

GCC 9.2.0、Open MPI 4.1.2、Python 3.8.5，AMD EPYC 7R13 KVM 节点。固定 N=1000000、D=32、K=32、seed=42，预热 2 轮后恢复初始中心，计时 20 轮。所有配置 P×T=12、单节点。

%s

## 性能结果

时间采用 kernel_seconds 中位数；数据生成、初始化、预热、最终评价和启动探测不在内核时间中。每个 P/T 内两种策略交错执行，每轮随机排序；各 P/T 按分块顺序执行，不是所有配置全局交错。

| P×T | %s中位/秒 | 最小–最大/秒 | %s中位/秒 | 最小–最大/秒 | 第一方案时间/第二方案时间 | 第二方案耗时下降 |
|---|---:|---:|---:|---:|---:|---:|
%s

表中“第二方案耗时下降”为负值时，表示第二方案本次中位耗时更长。

%s

%s

这里的比值是固定资源下的策略对照，不是相对串行的强扩展加速比。本作业内 V0 大输入只运行一次，供数值核查，不把它作为重复计时的性能基线。

## 限制与后续

线程 affinity 来自执行算法前的独立 OpenMP 探测器；包装器随后使用同一 CPU mask 和环境执行算法，算法另检查实际线程组大小。记录不是算法计时循环内的线程实时采样。

不同作业之间的节点、socket/NUMA 分配及系统状态可能不同，不把本次 V3 时间与此前混合作业的小幅差异解释为优化收益。没有用其他作业的 V0 时间计算本次加速比。

结论只覆盖当前合成数据规模、节点分配和所测策略。保留全部原始记录、编译日志和布局记录；分析可使用 HPC/analyze-atlas-strategy-results.py 重算。%s
'''%(title,allocation['job_id'],job_date,allocation['host'],len(expected_sources),len(rows),len(expected),plan['repeats'],
       sse_min,sse_max,audit['max_sse_absolute_error_vs_v0'],audit['max_sse_scaled_error_vs_v0'],rank_count,thread_count,
       intro,first_name,second_name,'\n'.join(table),interpretation,layout_description(allocation,layout,selected_processes),next_step)
    (folder/'analysis.zh-CN.md').write_text(report)
    print(json.dumps(dict(job_id=allocation['job_id'],records=len(rows),numerical='pass',placement='pass',
                          rank_records=rank_count,thread_probe_records=thread_count,
                          speedups=[c['speedup'] for c in comparisons]),indent=2))


def layout_description(allocation,layout,selected_processes):
    cpus=allocation['allowed_cpus']
    sockets=sorted({r['socket'] for r in allocation['topology'].values()})
    cross={p:c['cross_socket_ranks'] for p,c in layout['configurations'].items() if int(p) in selected_processes}
    return ('本次 OS CPU 分配为 `%s`，整体使用 socket %s。所测配比的跨 socket rank 为 `%s`。'
            '因此需区分“整个作业跨 socket”与“单个 rank 的线程跨 socket”；匹配策略的布局保持一致。')%(
                ','.join(map(str,cpus)),','.join(map(str,sockets)),json.dumps(cross))


if __name__=='__main__':
    main()
