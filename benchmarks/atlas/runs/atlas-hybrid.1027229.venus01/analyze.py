"""Recompute statistics and audit downloaded job 1027229 without changing raw data."""
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import tarfile

ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def main():
    helper = ROOT.parent/'atlas-hybrid-launch.py'
    with tarfile.open(ROOT.parent/'project3-atlas-hybrid.tar.gz') as tar:
        assert tar.extractfile('project3-atlas-hybrid/atlas-hybrid-launch.py').read() == helper.read_bytes()
    spec = importlib.util.spec_from_file_location('hybrid', helper)
    hybrid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hybrid)
    plan = load(ROOT/'layout-plan.json')
    allocation = load(ROOT/'allocation.json')
    assert plan['allocation'] == allocation
    assert hybrid.build_plan(allocation) == plan
    assert allocation['job_id'] == '1027229.venus01'
    assert (ROOT/'status.txt').read_text().strip() == 'exit_status=0'
    pbs = (ROOT/'pbs-job.txt').read_text()
    assert re.search(r'^\s*Exit_status = 0$', pbs, re.M)
    assert re.search(r'^\s*job_state = F$', pbs, re.M)
    rows = [json.loads(line) for line in (ROOT/'hybrid.jsonl').read_text().splitlines() if line.strip()]
    assert len(rows) == 30 and len({r['placement_id'] for r in rows}) == 30
    assert len(list((ROOT/'placements').iterdir())) == 30
    reference = rows[0]
    binary_manifest = {line.split()[1]:line.split()[0] for line in (ROOT/'binaries.sha256').read_text().splitlines()}
    groups = defaultdict(list)
    rank_records = thread_records = 0
    for row in rows:
        p,t = row['p'],row['t']
        assert (p,t) in hybrid.PAIRS
        assert (row['n'],row['d'],row['k'],row['seed'],row['iterations'],row['warmup']) == (1000000,32,32,42,20,2)
        assert (row['variant'],row['communication'],row['nodes'],row['mode'],row['diagnostic'],row['skew']) == ('v3','allreduce',1,'fixed',False,False)
        assert row['input'] == '' and row['stop_reason'] == 'fixed_iterations'
        assert row['binary_sha256'] == binary_manifest['build/kmeans_mpi']
        for field in ['data_fingerprint','init_indices','counts','sse','host','run_id','job_id','compiler']:
            assert row[field] == reference[field],field
        assert sum(row['counts']) == row['n'] and len(row['counts']) == row['k']
        assert row['host'] == allocation['host'] and row['job_id'] == allocation['job_id']
        assert math.isfinite(row['kernel_seconds']) and row['kernel_seconds'] > 0
        directory = ROOT/'placements'/row['placement_id']
        launch = load(directory/'launch.json')
        actual_command = row['command'][row['command'].index('--')+1:]
        assert launch['algorithm_command'] == actual_command
        assert (launch['p'],launch['t']) == (p,t)
        records = [load(directory/('rank-%d.json'%rank)) for rank in range(p)]
        check = hybrid.verify_records(plan,p,t,records)
        assert check == load(directory/'check.json')
        assert row['placement_check'] == 'pass'
        assert row['omp_places'] == next(r for r in records if r['rank']==0)['omp_places']
        for record in records:
            assert record['command'] == actual_command
            assert record['thread_probe']['openmp'] == 201511
        rank_records += len(records)
        thread_records += sum(len(r['thread_probe']['threads']) for r in records)
        groups[(p,t)].append(row)
    assert set(groups) == set(hybrid.PAIRS)
    assert (rank_records,thread_records) == (140,360)
    for group in groups.values():
        assert sorted(r['repeat'] for r in group) == list(range(5))
    for repeat in range(5):
        assert {(r['p'],r['t']) for r in rows if r['repeat']==repeat} == set(hybrid.PAIRS)
    with (ROOT/'hybrid.csv').open() as source:
        summaries = {(int(r['p']),int(r['t'])):r for r in csv.DictReader(source)}
    assert set(summaries) == set(groups)
    for key,group in groups.items():
        saved = summaries[key]
        times = [r['kernel_seconds'] for r in group]
        assert int(saved['repeats']) == 5
        for field,actual in [('median_seconds',statistics.median(times)),('min_seconds',min(times)),('max_seconds',max(times))]:
            assert math.isclose(float(saved[field]),actual,rel_tol=1e-14)

    small = load(ROOT/'preflight-serial.json')
    small_errors = []
    for p,t in hybrid.PAIRS:
        row = load(ROOT/('preflight-p%d.json'%p))
        assert (row['p'],row['t']) == (p,t)
        for field in ['data_fingerprint','init_indices','counts','labels']:
            assert row[field] == small[field]
        assert len(row['centers']) == len(small['centers'])
        pairs = list(zip(row['centers'],small['centers']))
        assert all(math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-10) for a,b in pairs)
        assert math.isclose(row['sse'],small['sse'],rel_tol=1e-8,abs_tol=1e-10)
        directory = ROOT/'preflight-placements'/row['placement_id']
        records = [load(directory/('rank-%d.json'%rank)) for rank in range(p)]
        hybrid.verify_records(plan,p,t,records)
        small_errors.append(dict(p=p,t=t,max_centroid_absolute_error=max(abs(a-b) for a,b in pairs),
                                 sse_absolute_error=abs(row['sse']-small['sse'])))

    baseline = statistics.median(r['kernel_seconds'] for r in groups[(12,1)])
    stats = []
    table = []
    for (p,t),group in sorted(groups.items()):
        times = [r['kernel_seconds'] for r in group]
        median = statistics.median(times)
        item = dict(p=p,t=t,repeats=5,times=times,median_seconds=median,
                    min_seconds=min(times),max_seconds=max(times),relative_to_12x1=baseline/median,
                    time_change_vs_12x1_pct=100*(median/baseline-1),
                    median_total_seconds=statistics.median(r['total_seconds'] for r in group),
                    median_launch_seconds=statistics.median(r['launch_seconds'] for r in group))
        stats.append(item)
        table.append('| %d×%d | %.6f | %.6f–%.6f | %.4f× | %+.2f%% |' %
                     (p,t,median,min(times),max(times),baseline/median,item['time_change_vs_12x1_pct']))
    best = min(stats,key=lambda r:r['median_seconds'])
    interval_intersection = (max(s['min_seconds'] for s in stats),min(s['max_seconds'] for s in stats))
    assert interval_intersection[0] <= interval_intersection[1]
    allowed = allocation['allowed_cpus']
    sockets = sorted({v['socket'] for v in allocation['topology'].values()})
    assert sockets == [0] and allowed == list(range(36,48))
    assert all(not c['cross_socket_ranks'] for c in plan['configurations'].values())
    original_files = [p for p in ROOT.rglob('*') if p.is_file() and p.name not in ['analyze.py','analysis.audit.json','analysis.zh-CN.md']]
    audit = dict(job_id=allocation['job_id'],records=30,configurations=6,repeats=5,
                 completeness='pass',csv_recalculation='pass',numerical_check='pass',placement_check='pass',
                 formal_rank_records=rank_records,formal_thread_probe_records=thread_records,
                 allowed_os_cpus=allowed,sockets=sockets,numa_nodes=[1],
                 sse=reference['sse'],identical_counts=True,data_fingerprint=reference['data_fingerprint'],
                 openmp_standard_macro=201511,small_case_errors=small_errors,statistics=stats,
                 observed_best=dict(p=best['p'],t=best['t'],median_seconds=best['median_seconds']),
                 all_observed_ranges_intersection=list(interval_intersection),
                 relative_metric='12x1 median / layout median; fixed total cores, not strong-scaling efficiency',
                 source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(original_files)})
    (ROOT/'analysis.audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    report = '''# Atlas 固定 12 核的 MPI+OpenMP 配比结果

作业 `1027229.venus01`，2026-10-24，节点 `cnode-33-43-45`。本分析仅比较同一作业内固定 12 核的六种 V3 配比。

## 核查结论

- PBS 和脚本退出状态均为 0。30 条正式记录完整，每配置 5 次，每批均覆盖全部六种配比。
- CSV 的中位数、最小值和最大值与原始 JSONL 逐组一致。
- 所有运行的数据指纹为 `7fcf2e8b0cc1a222`，初始中心编号、最终簇计数完全相同，计数和为 1000000。
- 全部正式运行的 SSE 均为 73440053.24011984。本轮没有重新测量大输入 V0；六种配比的小数据结果另与串行参考比较，标签/计数相同、质心和 SSE 在规定容差内。具体误差保存在 analysis.audit.json。
- 核对 30 次正式运行的 140 份 rank CPU mask、360 份 OpenMP 线程探测记录，均与布局计划一致、无重叠、覆盖分配的全部 12 核。原始记录通过 placement_id 与实际启动目录逐一关联。
- 每个正式运行的 MPI 可执行文件 SHA-256 均匹配 binaries.sha256。探测器的 `_OPENMP` 宏为 201511，该字段表示编译时 OpenMP 标准版本，不是运行库发行版本。

## 硬件、布局与工作量

AMD EPYC 7R13，KVM 虚拟机；可见 96 个 CPU、2 个 socket、4 个 NUMA 节点、每核 1 个硬件线程。作业申请 12 核、8GB，walltime 为 5 分 43 秒。

本次实际分配 OS CPU `36–47`，全部属于 socket 0、NUMA node 1。所有配比均使用同一组 12 个不同物理核心，每 rank 取得 T 个核心，全部 cross_socket_ranks 为空。因此此前预期的“1×12、3×4 跨 socket”情况没有在本次分配中出现。

GCC 9.2.0、Open MPI 4.1.2、Python 3.8.5；算法使用 `-O3 -std=c++17 -Wall -Wextra -Wpedantic -fopenmp -DKM_MPI` 编译。固定 V3、Allreduce、N=1000000、D=32、K=32、seed=42，预热 2 轮后恢复初始中心，计时 20 轮；每配置重复 5 次，每批随机排序。

每次启动时，Python 包装器设置 rank 的 OS CPU mask 及显式逐核 OMP_PLACES、OMP_PROC_BIND=close，独立 OpenMP 探测程序先检查每线程一个指定核心，再执行 K-means。MPI 的 `--bind-to none` 只表示 MPI 启动器不做额外绑定，不代表包装器没有绑定。线程记录来自独立探测程序，算法自身另检查线程组大小；并非算法计时循环内的实时 affinity 采样。

## 同作业内的配比比较

P 是 MPI 进程数，T 是每进程线程数，所有配置 P×T=12。耗时为 kernel_seconds 中位数，不含编译、数据准备、初始化、预热、最终评价或外部启动开销。最小–最大范围来自 5 次实测，不是置信区间。

| P×T | 中位内核耗时/秒 | 最小–最大/秒 | 12×1 时间/本配比时间 | 相对 12×1 耗时变化 |
|---|---:|---:|---:|---:|
%s

3×4 在本次观测中位数最低，比 12×1 低约 0.44%%；1×12 比 12×1 低约 0.23%%。所有中位数位于 0.952300–0.984793 秒，最大/最小中位数之比约为 1.0341。

六组的实测最小–最大范围全部存在共同交集（约 0.970431–0.974131 秒）。这并非正式显著性检验，但结合只有 5 次重复和很小的中位数差异，本次资料不足以认定 3×4 是稳定最优配比。更合适的结论是：在该输入和同一 NUMA 节点的 12 核分配下，V3 的六种进程/线程配比表现接近。

这些比值描述固定资源下的布局差异，不是随核心数增加的强扩展加速比，也不应再除以 12 作为并行效率。

## 与前一强扩展作业的关系

前次 1027222 在 cnode-33-43-39 上运行，12 进程使用两个 socket；本次节点为 cnode-33-43-45，12 核全部在同一个 socket/NUMA 节点。两次的绑核启动方式也不同。本次不能直接套用前次 V0=11.232365 秒计算“本次串行加速比”，也不能用两作业间的小幅时间差归因于混合并行或 NUMA 优化。

## 报告可用表述

在 Atlas 的一个 AMD EPYC 7R13 节点上，固定总核数为 12，比较 V3 的 1×12、2×6、3×4、4×3、6×2、12×1 六种 MPI/OpenMP 配比。所有配置使用 socket 0、NUMA node 1 中相同的 12 个核心。固定 N=1000000、D=32、K=32，预热 2 轮、计时 20 轮，每配置重复 5 次。六种配比的内核时间中位数为 0.952–0.985 秒，3×4 本次中位数最低，相对 12×1 的耗时下降约 0.44%%。由于重复运行范围重叠，尚不能认定该配比具有稳定优势。全部运行的数据与初始中心一致，最终簇计数和 SSE 相同，六种配比的小数据对照也通过串行参考验证。

## 后续对照选择

已准备的线程策略包和通信策略包默认使用 2×6、4×3、6×2，可以继续采用：它们覆盖不同线程数量与 MPI 进程数量，并且在本次 V3 试验中没有明显性能劣势。保持多个代表性配比，比仅依据本次 0.44%% 的差异挑选单个“最佳”配比更适合比较策略。

下一轮先跑 V2/V3，观察原子更新与私有缓冲的差异，再跑 V3 Allreduce/Reduce+Bcast。每个新作业仍按其实际分配记录布局；如果跨 socket 情况改变，需在对应结果中说明。本次结论只适用于所测单节点、单输入规模、Allreduce 和 V3，不能证明其他策略或多节点下也相近。

原始文件保持原样，分析可用同目录 analyze.py 重算，逐文件哈希和完整派生统计量在 analysis.audit.json 中。
''' % '\n'.join(table)
    (ROOT/'analysis.zh-CN.md').write_text(report)
    print(json.dumps(dict(records=30,csv='pass',placement='pass',formal_rank_records=rank_records,
                          formal_thread_probe_records=thread_records,observed_best=[best['p'],best['t']],
                          observed_best_relative_to_12x1=best['relative_to_12x1']),indent=2))


if __name__ == '__main__':
    main()
