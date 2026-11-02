# Atlas 实验

本目录包含 PBS 作业入口、CPU 亲和性工具和运行包准备工具。
归档测量数据和原始源代码快照位于
[benchmarks/atlas](../benchmarks/atlas/EXPERIMENT_INDEX.zh-CN.md)。

## 在本地复核已记录的实验

在仓库根目录下运行，使用 Python 3.8+ 及其标准库：

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
```

第二条命令会审计全部 125 条正式测量记录，重新计算统计量，并检查数值结果和已记录的进程放置证据。
它将副本和重新生成的报告写入 `artifacts/atlas-audit/`；归档输入始终保持不变。
再次运行时，可使用 `--output artifacts/atlas-audit-2` 选择另一个输出目录。
验证/试运行作业包含在完整性检查中，但不计入这 125 条正式记录，也不会由四个正式审计脚本重新运行。
此离线分析不需要安装 MPI，也不需要登录集群。

## 基于当前检出版本准备新的 HPC 运行

```sh
python3 hpc/build-atlas-strategy-packages.py
```

该命令会在 `artifacts/atlas-packages/` 下构建七个独立归档包，并为每个包内的全部源文件生成 SHA-256 清单。
如果输出目录已经存在，命令会拒绝执行。若只准备部分研究或使用其他输出目录：

```sh
python3 hpc/build-atlas-strategy-packages.py --studies threads communication \
  --output artifacts/atlas-packages-new
```

这些新包包含的是**当前检出版本**。若需要已记录作业使用的确切源代码，请改用
`benchmarks/atlas/source-packages/`。不要用新生成的包替换归档包。

使用你通常采用的文件传输方式，将所需归档包传到 Atlas。
在 Atlas 上解压，进入解压后的目录，并从该目录提交作业：

```sh
tar -xzf project3-atlas-strong.tar.gz
cd project3-atlas-strong
sha256sum -c source-manifest.sha256
qsub atlas-strong.pbs
```

七个入口分别是 `atlas-smoke.pbs`、`atlas-validation.pbs`、
`atlas-strong.pbs`、`atlas-hybrid.pbs`、`atlas-threads.pbs` 和
`atlas-communication.pbs`，以及 `atlas-thread-scaling.pbs`。历史快照并非都包含源文件校验清单；
使用不含清单的旧包时，跳过校验和命令。

**不要直接从检出目录提交 `qsub hpc/atlas-strong.pbs`。** PBS 脚本要求源文件和辅助工具共同位于
`PBS_O_WORKDIR`。打包工具会创建这种扁平工作目录布局。
各项研究必须使用各自独立的解压目录，因为同一工作目录内的作业会共用构建输出。
不要从同一个检出目录或解压工作目录运行多个研究作业。

## 已记录的环境和工作负载

- CPU 实现：C++17、MPI + OpenMP；不使用 GPU。
- 已记录的模块：`miniconda/4.12`、`openmpi/4.1.2`、`gcc/9.2.0`。
- PBS 设置：`parallel` 队列、一个节点、12 个 CPU、8 GB 内存、30 分钟墙钟时间上限。
  新运行前，请确认这些模块和资源可用。
- 正式工作负载：N=1,000,000、D=32、K=32、seed=42，固定 20 次计时迭代，
  2 次预热迭代，每种配置重复 5 次。输入在内存中生成。
- 强扩展：V0 基线以及 P=1,2,3,4,6,12、T=1 的 V3（35 条记录）。
- 混合并行：P/T=1/12,2/6,3/4,4/3,6/2,12/1 的 V3（30 条记录）。
- 线程策略：P/T=2/6,4/3,6/2 的 V2/V3（30 条记录）。
- 通信：相同布局下的 V3 Allreduce/Reduce+Bcast（30 条记录）。

新作业会将输出写入 `results/atlas-<study>.<PBS_JOBID>/`；简单的 smoke 作业例外，它直接写入 PBS 输出。
请下载结果目录和 PBS 输出；在可用时，通过 `qstat -xf JOBID` 保存已完成作业的调度器元数据。
完整历史审计既使用程序输出，也使用 `pbs-job.txt`。
耗时会随分配的 CPU、拓扑和负载变化；请在同一作业内比较相匹配的配置。
采用相同流程并不保证获得完全相同的墙钟时间。

## 测试

```sh
python3 -m unittest discover -s hpc -v
make test
```

HPC 单元测试使用已记录或构造的布局，不会提交真实 PBS 作业。
如需实际的 MPI 集成测试，请在适当系统上使用 `make test-mpi`，或提交验证包。
历史运行说明保存在 `benchmarks/atlas/source-packages/` 的原始源码快照内；当前命令统一使用本指南。
新包将辅助工具平铺放置，且只包含运行依赖；仓库的离线审计应从完整检出目录运行。

## 新增固定 P 实验

详见[固定 P=2 线程扩展与独立阶段计时说明](THREAD_SCALING_GUIDE.zh-CN.md)。作业 `1028185.venus01` 已完成并复核通过，无需重新提交。新增 50 条普通计时、50 条独立诊断与原四组 125 条在统一目录中按作业保存；[结果与图表](../analysis/atlas/THREAD_SCALING.zh-CN.md)已整理。
