"""Audit downloaded Atlas job 1027222; regenerate derived JSON and Chinese report."""
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shlex
import statistics

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text())


def binding_records(text):
    records = {}
    for match in re.finditer(r'MCW rank (\d+) bound to ([^\n]+)', text):
        rank = int(match.group(1))
        assert rank not in records, ('duplicate binding report', rank)
        cores = re.findall(r'socket (\d+)\[core (\d+)\[hwt (\d+)\]\]', match.group(2))
        assert len(cores) == 1, match.group(0)
        records[rank] = tuple(map(int, cores[0]))
    return records


def main():
    rows = [json.loads(line) for line in (ROOT / 'strong.jsonl').read_text().splitlines() if line.strip()]
    groups = defaultdict(list)
    expected = {('v0', 1)} | {('v3', p) for p in (1, 2, 3, 4, 6, 12)}
    assert len(rows) == 35
    reference = next(r for r in rows if r['variant'] == 'v0')
    for r in rows:
        groups[(r['variant'], r['p'])].append(r)
        assert (r['n'], r['d'], r['k'], r['seed'], r['iterations'], r['warmup']) == (1000000, 32, 32, 42, 20, 2)
        assert (r['t'], r['nodes'], r['mode'], r['diagnostic'], r['skew']) == (1, 1, 'fixed', False, False)
        assert r['communication'] == 'allreduce'
        assert r['stop_reason'] == 'fixed_iterations' and r['requested_iterations'] == 20
        assert r['input'] == '' and r['generator'] == reference['generator']
        for field in ('job_id', 'run_id', 'host', 'compiler', 'data_fingerprint', 'init_indices', 'counts'):
            assert r[field] == reference[field], field
        assert sum(r['counts']) == r['n']
        assert math.isclose(r['sse'], reference['sse'], rel_tol=1e-12)
        assert math.isfinite(r['kernel_seconds']) and r['kernel_seconds'] > 0
    assert set(groups) == expected
    for group in groups.values():
        assert sorted(r['repeat'] for r in group) == list(range(5))
        assert len({r['binary_sha256'] for r in group}) == 1
    for repeat in range(5):
        assert {(r['variant'], r['p']) for r in rows if r['repeat'] == repeat} == expected
    assert len({r['binary_sha256'] for r in rows if r['variant'] == 'v3'}) == 1
    assert (ROOT / 'status.txt').read_text().strip() == 'exit_status=0'
    pbs = (ROOT / 'pbs-job.txt').read_text()
    assert re.search(r'^\s*job_state = F$', pbs, re.M)
    assert re.search(r'^\s*Exit_status = 0$', pbs, re.M)
    with (ROOT / 'strong.csv').open() as source:
        summaries = {(r['variant'], int(r['p'])): r for r in csv.DictReader(source)}
    assert set(summaries) == expected
    for key, group in groups.items():
        times = [r['kernel_seconds'] for r in group]
        saved = summaries[key]
        assert int(saved['repeats']) == 5
        for field, actual in [('median_seconds', statistics.median(times)), ('min_seconds', min(times)), ('max_seconds', max(times))]:
            assert math.isclose(float(saved[field]), actual, rel_tol=1e-14)

    allocation = load('allocation.json')
    assert allocation['job_id'] == '1027222.venus01'
    allowed = set(allocation['allowed_cpus'])
    assert len(allowed) == 12
    physical = {(v['socket'], v['core']) for v in allocation['topology'].values()}
    assert len(physical) == 12
    audits = {}
    preflight = {}
    logical_to_os = {}
    for p in (1, 2, 3, 4, 6, 12):
        audits[p] = [json.loads(line) for line in (ROOT / ('affinity-p%d.jsonl' % p)).read_text().splitlines()]
        assert len(audits[p]) == p and {r['rank'] for r in audits[p]} == set(range(p))
        assert all(r['host'] == allocation['host'] and len(r['cpus']) == 1 and set(r['cpus']) <= allowed for r in audits[p])
        assert len({r['cpus'][0] for r in audits[p]}) == p
        assert next(r for r in audits[p] if r['rank'] == 0)['cpus'] == [40]
        preflight[p] = binding_records((ROOT / ('affinity-p%d.stderr.log' % p)).read_text())
        assert set(preflight[p]) == set(range(p))
        for r in audits[p]:
            logical = preflight[p][r['rank']]
            os_cpu = r['cpus'][0]
            assert logical_to_os.setdefault(logical, os_cpu) == os_cpu
    assert load('serial-affinity.json')['cpus'] == [40]
    assert load('affinity-verified.json')['baseline_cpu'] == 40
    log = (ROOT / 'strong.stderr.log').read_text()
    blocks = []
    for line in log.splitlines():
        if line.startswith('mpirun ') or line.startswith('taskset '):
            blocks.append([line, []])
        elif blocks:
            blocks[-1][1].append(line)
    assert len(blocks) == len(rows)
    mpi_launches = 0
    rank_reports = 0
    for row, (command, lines) in zip(rows, blocks):
        assert shlex.split(command) == row['command']
        reports = binding_records('\n'.join(lines))
        if row['variant'] == 'v0':
            assert not reports
            assert row['command'][:3] == ['taskset', '--cpu-list', '40']
        else:
            mpi_launches += 1
            p = row['p']
            assert reports == preflight[p], (p, reports)
            mapped = [logical_to_os[reports[r]] for r in range(p)]
            assert len(set(mapped)) == p and set(mapped) <= allowed
            rank_reports += len(reports)
    assert (mpi_launches, rank_reports) == (30, 140)

    serial = statistics.median(r['kernel_seconds'] for r in groups[('v0', 1)])
    v3one = statistics.median(r['kernel_seconds'] for r in groups[('v3', 1)])
    statistics_rows = []
    table = []
    for (variant, p), group in sorted(groups.items()):
        times = [r['kernel_seconds'] for r in group]
        median = statistics.median(times)
        stats = dict(variant=variant, p=p, t=1, repeats=5, times=times,
                     median_seconds=median, min_seconds=min(times), max_seconds=max(times),
                     speedup_vs_v0=serial / median, efficiency_vs_v0=serial / median / p,
                     speedup_vs_v3_p1=v3one / median if variant == 'v3' else None,
                     efficiency_vs_v3_p1=v3one / median / p if variant == 'v3' else None,
                     median_total_seconds=statistics.median(r['total_seconds'] for r in group),
                     median_launch_seconds=statistics.median(r['launch_seconds'] for r in group))
        statistics_rows.append(stats)
        table.append('| %s | %d | %.6f | %.6f–%.6f | %.3f× | %.2f%% | %s | %s |' %
                     (variant.upper(), p, median, min(times), max(times), stats['speedup_vs_v0'], 100 * stats['efficiency_vs_v0'],
                      '%.3f×' % stats['speedup_vs_v3_p1'] if variant == 'v3' else '—',
                      '%.2f%%' % (100 * stats['efficiency_vs_v3_p1']) if variant == 'v3' else '—'))
    sse_min, sse_max = min(r['sse'] for r in rows), max(r['sse'] for r in rows)
    warnings = sorted(set(re.findall(r'unable to open ([^:]+): ([^:]+):', log)))
    sources = ['strong.jsonl', 'strong.csv', 'strong.stderr.log', 'environment.txt', 'allocation.json',
               'affinity-verified.json', 'serial-affinity.json', 'pbs-job.txt', 'p3_strong.o1027222', 'status.txt']
    sources += ['affinity-p%d.%s' % (p, suffix) for p in (1, 2, 3, 4, 6, 12) for suffix in ('jsonl', 'stderr.log')]
    audit = dict(job_id='1027222.venus01', records=35, configurations=7, repeats=5,
                 completeness='pass', csv_recalculation='pass', numerical_check='pass',
                 sse_min=sse_min, sse_max=sse_max, sse_absolute_spread=sse_max-sse_min,
                 sse_relative_spread=(sse_max-sse_min)/sse_min,
                 identical_counts=True, data_fingerprint=reference['data_fingerprint'],
                 baseline_os_cpu=40, allowed_os_cpus=sorted(allowed),
                 affinity_preflight='pass', repeated_mpi_binding_reports='pass', mpi_launches=30, rank_reports=140,
                 binding_limit='OS affinity sampled in preflight; timed launches checked via matching MPI logical binding reports',
                 sockets_by_p={str(p): sorted({allocation['topology'][str(r['cpus'][0])]['socket'] for r in records}) for p, records in audits.items()},
                 warnings=warnings, statistics=statistics_rows,
                 source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources})
    (ROOT / 'analysis.audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    report = '''# Atlas V3 单节点进程强扩展结果

作业 `1027222.venus01`，2026-10-24，计算节点 `cnode-33-43-39`。分析仅使用本作业数据，不与 N=100000 的前次 pilot 合并。

## 核查结果

- PBS Exit_status=0、脚本 exit_status=0；35 条记录完整，7 组配置各 5 次，无缺失或重复编号。
- 原始 JSONL 与 CSV 的中位数、最小值、最大值逐组一致。
- 全部记录的数据指纹、初始中心样本编号、最终簇计数相同，计数和均为 1000000。
- SSE 范围为 %.12f 至 %.12f，绝对跨度 %.6g，相对跨度 %.3g；独立复核通过相对容差 1e-12。
- 本作业未重新运行全套数值单元测试。此前 validation 作业 1027219 的 12 项测试已通过；本轮增加了大输入结果一致性核查。
- 30 次正式 MPI 启动的 140 条 rank 绑核报告完整，与各 P 的预检查一致。

## 环境与计时定义

AMD EPYC 7R13，KVM 虚拟机；节点可见 96 个 CPU、2 个 socket、4 个 NUMA 节点、每核 1 个硬件线程。作业分配 12 核、8 GB，walltime 为 5 分 11 秒。

GCC 9.2.0、Open MPI 4.1.2、Python 3.8.5。构建选项为 `-O3 -std=c++17 -Wall -Wextra -Wpedantic`；MPI 程序另用 `-fopenmp -DKM_MPI`。完整编译命令在 PBS 主日志中。Python 自身报告的构建编译器 GCC 7.3.0 不代表本次 C++ 算法使用该版本。

固定 N=1000000、D=32、K=32、seed=42，预热 2 轮后恢复初始中心，正式测量 20 轮。每组重复 5 次，每批打乱配置顺序。V3 固定每进程 1 线程，通信方式为 Allreduce；没有测量 V1、V2 或多线程 V3。

下表采用 `kernel_seconds` 的中位数，即各 rank 的 Lloyd 迭代耗时最大值。数据生成、初始化、预热、最终评价、MPI 启动与编译均不计入该数值；不能把它称为整个作业或端到端时间。每组总耗时及外部启动耗时的中位数另保存在 analysis.audit.json 中。

## 性能结果

| 版本 | P（T=1） | 中位内核时间/秒 | 最小–最大/秒 | 相对 V0 加速比 | 相对 V0 效率 | 相对 V3(P=1) 加速比 | 相对 V3(P=1) 效率 |
|---|---:|---:|---:|---:|---:|---:|---:|
%s

相对 V0：S=T_V0/T_P，E=S/P。相对 V3(P=1)：S_MPI=T_V3,1/T_V3,P，E_MPI=S_MPI/P。效率按每次实际使用的 P 个核心计算；PBS 整个作业保留了 12 核，两者不可混同。范围为 5 次实测的最小–最大值，不是置信区间。

V3 的 12 进程中位时间为 0.949930 秒，相对 V0 为 11.824 倍、效率 98.54%%；相对同一 V3 实现的单进程版本为 11.545 倍、效率 96.20%%。该输入在本次单节点 1–12 进程范围内呈现接近线性的扩展。

V3 单进程比 V0 的中位时间低约 2.37%%。两者为分别编译的串行和 MPI/OpenMP 可执行文件；相对 V0 的速度比包含这部分差异。P=2、4、6 相对 V0 的效率略超 100%%；同实现基准下 P=2、4 也略超 100%%。这些是原始测量的比值，应如实保留。缓存工作集变化、编译路径和系统波动都是可能因素，本次未测硬件计数器，不能确定因果，也不应宣称超线性收益稳定成立。

## CPU 布局与限制

PBS 可用 OS CPU 为 `40-45,86-91`。V0 通过 taskset 固定到 CPU 40；所有 P 的 MPI rank 0 预检查也在 CPU 40。每 rank 仅使用一个核心，不重叠、不超额订阅。

- P=1、2、3、4、6：CPU 从 40 开始依次使用，均在 socket 0、NUMA node 1。
- P=12：rank 0–5 在 CPU 40–45，rank 6–11 在 CPU 86–91；使用 socket 0/1、NUMA node 1/3。

本次没有单个多线程 rank 跨 socket 的情况，但 P=12 的整体布局跨两个 socket。因此 6 到 12 进程的比较同时涉及更多核心、更多缓存/内存资源和跨 socket 通信，不能解释为严格保持 NUMA 条件不变的实验，也不能外推到跨节点。

实际 OS affinity 在正式计时前通过独立 Python rank 探测；正式 30 次 MPI 启动另检查逻辑绑核报告与探测报告一致。计时程序没有在每轮采样 sched_getaffinity。证据支持本次映射一致，不等于逐时刻监控或物理硬件独占保证。

缺少 libbat.so、libosmcomp.so.3、libpsm_infinipath.so.1 的 MPI 可选组件警告被标记为 ignored，未阻止本次运行。尚无多节点网络性能验证。

## 报告可用表述

在 Atlas 的一个 AMD EPYC 7R13 计算节点上，固定 N=1000000、D=32、K=32，使用 2 轮预热、20 轮计时迭代，每种配置重复 5 次。每进程固定 1 个线程，V3 使用 Allreduce。V0 的内核时间中位数为 11.232365 秒，V3 的 12 进程结果为 0.949930 秒，对应相对串行的加速比 11.824 和效率 98.54%%；以 V3 单进程为基准，加速比为 11.545、效率为 96.20%%。所有运行使用相同数据与初始中心，最终簇计数相同，SSE 的相对跨度低于 1e-12。12 进程配置使用两个 socket，其他配置使用一个 socket，因此该结果描述此节点分配和布局下的单节点进程强扩展。

## 后续实验

下一轮优先开展固定总核数的 MPI+OpenMP 配比实验，明确记录每个 rank 的核心集合与 socket；这能补足作业的混合并行部分。再按需要分别比较 V2/V3、通信方式和弱扩展。小幅优势需结合波动范围与额外重复判断。

当前报告没有提供混合线程扩展、跨节点扩展或通信瓶颈的结论。保留源码上传包、原始结果、编译日志和本目录 analyze.py，以便复核。
''' % (sse_min, sse_max, sse_max-sse_min, (sse_max-sse_min)/sse_min, '\n'.join(table))
    (ROOT / 'analysis.zh-CN.md').write_text(report)
    print(json.dumps(dict(records=35, csv='pass', numerical='pass', mpi_launches=mpi_launches,
                          rank_bindings=rank_reports, speedup_12_vs_v0=serial/statistics.median(r['kernel_seconds'] for r in groups[('v3', 12)])), indent=2))


if __name__ == '__main__':
    main()
