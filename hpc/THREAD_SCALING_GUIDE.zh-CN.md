# 固定 P=2 的线程扩展与独立阶段计时

[English](THREAD_SCALING_GUIDE.md) | [简体中文](THREAD_SCALING_GUIDE.zh-CN.md) | [한국어](THREAD_SCALING_GUIDE.ko.md)

这是**一个新增 CPU 作业**。原来四组实验的 125 条记录仍然有效，无需为本次扩展重跑。无需 GPU，也无需下载数据。作业 `1028185.venus01` 已完成，50 条普通计时、50 条独立诊断及 20 次小数据预检已归档并通过本地复核，无需重新提交。见[结果说明](../analysis/atlas/THREAD_SCALING.zh-CN.md)及[独立归档](../benchmarks/atlas/EXPERIMENT_INDEX.zh-CN.md)。以下提交步骤供未来复现实验使用；复核已下载结果请运行 `python3 -B scripts/reproduce_atlas_thread_scaling.py`。

## 实验设计

- 固定 P=2，T=1、2、3、4、6，对比 V2/V3，通信固定为 Allreduce。N=1,000,000、D=32、K=32、seed=42、20 轮计时、2 轮预热。
- 整个作业申请 12 核。每个 rank 始终保留同一 socket 内的相同 6 核，只随 T 改变嵌套的 OpenMP 活动核心集合。实际启用核心数为 2T，并非始终为 12。无法分成两组各 6 核且组内不跨 socket 的分配会在测量前报错。
- 每配置重复 5 次，得到 **50 条普通计时**（`timing.jsonl`）及 **50 条独立诊断计时**（`profile.jsonl`）。每次重复内部随机排列配置，顺序存入 `study-plan.json`。先完成普通计时，再单独运行诊断计时。
- 当次生成完整数据量的 V0 数值参考，并对两种模式、两种实现和全部线程数执行 20 次小数据检查。V0 不是重复测量的性能基线。核查数据指纹、初始样本、簇计数和 SSE；小数据还核查标签和质心。

线程扩展基线为同一实现 P=2、T=1 的中位时间：加速比 = median(T=1)/median(T)，线程效率 = 加速比/T。在新作业内比较 V2/V3。旧 T=6 结果仅供背景参考，不属于这次分配下的配对测量。

## 只准备并提交新增作业

在本机仓库根目录执行：

```sh
python3 hpc/atlas-thread-scaling.py --dry-run
python3 hpc/build-atlas-strategy-packages.py --studies thread-scaling \
  --output artifacts/atlas-thread-scaling-package
```

将 `artifacts/atlas-thread-scaling-package/project3-atlas-thread-scaling.tar.gz` 传至 Atlas。在 Atlas 的新工作目录中执行：

```sh
tar -xzf project3-atlas-thread-scaling.tar.gz
cd project3-atlas-thread-scaling
sha256sum -c source-manifest.sha256
qsub atlas-thread-scaling.pbs
```

PBS 脚本加载已有实验使用的模块，编译当前源码，保存环境与 CPU 拓扑，逐次核查绑核，运行实验并生成统计及中英韩分析。资源为 `parallel` 队列、单节点、12 核、8 GB、30 分钟。务必使用独立解压目录，不直接从仓库的 `hpc/` 提交，也不与其他运行中的作业共用构建目录。失败后请使用新提交及新结果目录。

## 取回与分析

取回**整个** `results/atlas-thread-scaling.<PBS_JOBID>/`、PBS 标准输出/错误文件（`p3_tscale.o*`）和本次确切源码包。调度器记录仍可查询时保存：

```sh
qstat -xf JOBID > results/atlas-thread-scaling.JOBID/pbs-job.txt
```

两处 `JOBID` 均替换为完整作业号。成功作业的 `status.txt` 应为 `exit_status=0`，且 `analysis.audit.json` 的数值、矩阵及绑核检查均通过。失败日志也应保留用于排查，不要把未完成的结果混入原来的 125 条归档记录。

下载后可在本地用 Python 3.8+ 标准库重新分析：

```sh
python3 hpc/analyze-atlas-thread-scaling.py /path/to/atlas-thread-scaling.JOBID
```

输出为 `thread-scaling-summary.csv`、`phase-summary.csv`、`analysis.audit.json` 和 `analysis.md` / `analysis.zh-CN.md` / `analysis.ko.md`。原始输入不变，派生文件可重新生成。

## 阶段贡献的解释

`--profile` 新增 `profile_ranks`（逐 rank 的内核及五阶段时间）和 `profile_critical_rank`。每条诊断样本使用**内核耗时最大 rank 的全部阶段**，平局取较小 rank。residual 为该 rank 内核减去其阶段之和。兼容保留的顶层 `phase_seconds` 仍为各阶段独立最大值，不能相加。

`accumulate` 包含缓冲清零、距离计算、更新及 OpenMP 屏障；V3 的 `thread_merge` 对随后合并单独计时。`mpi_reduce`、`centroid_update` 和 `control_bcast` 对应其他阶段（Allreduce 通常无需控制广播）。这能判断累加或合并是否占主要时间，但**不能**单独测出纯 atomic 等待，也不能仅靠相减证明因果。不要把诊断阶段时间与普通内核时间拼接。各阶段独立中位数的和不必等于内核中位数；最小–最大范围不是置信区间。现有报告和图表不会自动修改。
