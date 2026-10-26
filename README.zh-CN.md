# Lloyd K-means：MPI + OpenMP

[English](README.md) | [简体中文](README.zh-CN.md) | [한국어](README.ko.md)

使用 C++17 实现 Lloyd K-means，比较进程与线程并行策略。项目包含串行参考、MPI/OpenMP 版本、数值测试和实验脚本。聚类算法自行实现，不依赖聚类库。

| 版本 | 本地累加方式 | 用途 |
| --- | --- | --- |
| V0 | 串行 | 数值参考与单核基线 |
| V1 | 各 MPI 进程内串行 | 纯 MPI 基线 |
| V2 | OpenMP 共享数组原子更新 | 观察线程竞争 |
| V3 | OpenMP 线程私有缓冲，结束后合并 | 减少样本循环中的同步 |

并行程序支持 Allreduce 和 Reduce + Bcast 两种全局质心更新方式。

## 编译

需要 C++17 编译器和 Make；并行程序需要 MPI-3+ 与 OpenMP；测试、实验和离线核查需要 Python 3.8+，仅使用标准库；可选的报告绘图需要 Python 3.9+ 和 Matplotlib，依赖见 `requirements.txt`。

Linux/HPC 环境先加载相互匹配的编译器与 MPI 模块，再执行：

```sh
make all CXX=g++ MPICXX=mpicxx
```

仅编译串行程序可使用 `make serial`。macOS 使用 Apple Clang、Homebrew Open MPI 和 libomp：

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

默认选项为 `-O3 -std=c++17 -Wall -Wextra -Wpedantic`。串行和并行程序应使用相同的底层编译器与浮点选项。更换编译器或选项时加 `-B` 强制重编译。

## 快速运行

运行附带的手算示例：

```sh
./build/kmeans_serial --input examples/tiny.txt --k 2 \
  --init-indices 0,2 --iterations 1 --dump --trace
```

预期最终质心按行展开为 `[0, 1, 10, 11]`，计数为 `[2, 2]`，标签为 `[0, 0, 1, 1]`，SSE 为 `4`。

使用两个 MPI 进程、每进程两个线程运行合成数据：

```sh
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 50
```

纯 MPI 使用 `--variant v1 --threads 1`，原子累加使用 `--variant v2`，另一种通信方式使用 `--comm reduce-bcast`。每次成功运行向 stdout 输出一条 JSON，错误写入 stderr。

## 数据与参数

合成数据由种子和全局样本编号决定，在相同构建环境下改变进程数不会改变数据，无需下载。生成器包含 16 个高斯生成簇，与算法聚类数 `K` 独立；`--skew` 使 90% 的样本来自同一个生成簇。

外部数据使用空白分隔的文本格式：首行为 `N D`，之后恰好包含 `N * D` 个有限坐标值。运行前删除 ID 和标签，并统一完成需要的缩放。文件尺寸覆盖 `--n` 和 `--d`。文件由 rank 0 读取后通过 Scatterv 分发，总坐标数必须不超过 `INT_MAX`。

| 参数 | 默认值／含义 |
| --- | --- |
| `--n`、`--d`、`--k` | `10000`、`8`、`16`；要求 `N,D > 0`、`1 <= K <= N` |
| `--seed` | `42`；数据生成与初始样本选择 |
| `--input FILE` | 准备好的文本数据 |
| `--init-indices 0,2,...` | `K` 个不同的全局样本编号 |
| `--variant` | 串行为 `v0`；并行为 `v1`、`v2` 或默认的 `v3` |
| `--comm` | 默认 `allreduce`，或 `reduce-bcast` |
| `--threads` | `1`；V0、V1 只能使用一个线程 |
| `--mode` | 默认 `fixed`，或 `converge` |
| `--iterations` | 固定模式默认 `50` 轮；收敛模式默认上限 `300` 轮 |
| `--tol` | `1e-6`；相对最大质心位移 |
| `--warmup` | `0`；预热指定轮数后恢复初始状态 |
| `--skew` | 启用偏斜合成分布 |
| `--dump` | 输出初始／最终质心和最终标签 |
| `--trace` | 每轮 SSE、计数与更新后的质心 |
| `--profile` | 累加、合并、归约、更新和广播的阶段耗时 |

运行任一程序的 `--help` 可查看参数摘要。`--dump` 和 `--trace` 要求 `N` 与 `K * D` 均不超过 `100000`。

距离和坐标和使用 `double`，计数使用 64 位整数。完全等距时选择最小簇编号，空簇保留旧质心。最终标签、计数和 SSE 使用最终质心重新计算。浮点结果应按容差比较。不同数学库之间的高斯生成可能存在差异，可通过 `data_fingerprint` 核对输入。

## 测试

```sh
make test
make test-mpi
```

`make test` 运行串行和实验工具测试，跳过 MPI 集成测试。`make test-mpi` 还会执行真实 MPI/OpenMP 对照，包括不均匀分区、无样本进程、两种通信策略和分布式错误处理。

自定义启动器：

```sh
TEST_MPI=1 MPIEXEC=mpiexec MPIEXEC_FLAGS='--bind-to none' \
  python3 -m unittest discover -s tests -v
```

HPC 上的并行测试和实验应在调度器分配的足够计算资源内运行。`--threads` 设置线程数；程序关闭动态线程组并检查实际线程数。

## 实验

先预览工作量，再运行强扩展实验并汇总：

```sh
python3 scripts/benchmark.py --suite smoke --processes 1,2 --threads 2 \
  --n 10000 --d 8 --k 16 --iterations 5 --dry-run

python3 scripts/benchmark.py --suite strong --processes 1,2,4 --threads 1 \
  --n 100000 --d 32 --k 32 --repeats 5 --output results/strong.jsonl
python3 scripts/summarize.py results/strong.jsonl --output results/strong.csv
```

| 实验集 | 对比内容 |
| --- | --- |
| `serial` | 仅 V0 |
| `smoke` | V0–V3，以及 V3 的两种通信策略 |
| `strong` | 固定问题规模、改变进程数，包含 V0 基线 |
| `weak` | 固定每进程样本数，总样本数为 `N = --n * P` |
| `hybrid` | 固定 `--total-cores`，对有效进程数设置 `T = total_cores / P` |
| `threads` | 相同进程／线程配置下比较 V2 与 V3 |
| `communication` | V3 的 Allreduce 与 Reduce + Bcast |
| `sensitivity` | 每次只改变 N、D、K 中的一个参数 |

脚本默认测量 50 轮、预热 2 轮，每配置重复 5 次，每批重复内打乱配置顺序。`--launcher` 接收含 `{p}`、`{t}` 占位符的命令，按参数列表执行，不经过 shell。

`--serial-launcher` 为 V0 设置可选的命令前缀，例如 Linux 上的 `taskset --cpu-list 40`。CPU 编号必须来自调度器分配范围，并在计时前检查绑核。两种启动器都会记录到原始结果和 CSV 分组中；缺少串行启动器字段的旧结果仍可读取。

以下为 Open MPI 的绑定示例，需要对应核数的资源分配：

```sh
export OMP_PLACES=cores
export OMP_PROC_BIND=close
python3 scripts/benchmark.py --suite communication --processes 1,2 --threads 2 \
  --launcher 'mpiexec -n {p} --map-by slot:PE={t} --bind-to core --report-bindings' \
  --output results/communication.jsonl
```

检查启动器的绑定报告并记录资源分配；设置环境变量本身不能证明绑定生效。性能测量应避免超额订阅。调度器和模块配置取决于具体集群。

原始 JSONL 和 stderr 日志分别保存。CSV 汇总包含内核时间的中位数、最小值、最大值、重复次数及 SSE 范围。输出文件不会覆盖已有文件，重叠的测量记录会被拒绝。

## 计时与复现

- `kernel_seconds` 测量预热、重置和起始 barrier 之后的 Lloyd 迭代，取各进程耗时的最大值。
- 数据准备、初始化、预热与最终评估分别计时。`total_seconds` 从 MPI 初始化后开始，到最终评估结束；`launch_seconds` 测量外部命令耗时。
- `--trace`、`--profile` 会引入诊断开销，实验汇总会拒绝此类记录。各阶段最大耗时不能相加重建总时间。
- 强扩展加速比为 `t_serial / t_parallel`，效率为 `speedup / (P * T)`。弱扩展效率比较每进程样本数及线程数固定时 `P=1` 与 `P>1` 的耗时。只对工作量和环境匹配的配置计算这些指标。

实验记录包含主机名、可执行文件路径、启动命令和作业 ID。`.gitignore` 排除新的运行结果、外部数据、本地笔记、凭据、缓存和构建产物；明确纳入 `benchmarks/atlas/` 中保留的实验记录。

## 已完成的 Atlas 实验与复现

仓库保留五组 Atlas CPU 正式实验的 **175 条普通测量记录**（另有 50 条独立诊断），以及正确性验证和 pilot 记录。正式实验使用 N=1,000,000、D=32、K=32、seed=42、**20 轮计时**、2 轮预热、每配置 5 次重复，与上面的通用默认参数不同。

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py
python3 hpc/build-atlas-strategy-packages.py
```

前两条命令在本地检查文件完整性、重算统计并复查数值与绑核记录，无需 MPI 或 HPC 登录；结果写入 `artifacts/atlas-audit/`，不覆盖存档。第三条命令从当前代码生成独立作业包，传到 HPC、解压并进入包目录后再提交 PBS，不直接从仓库提交 `hpc/` 下的 PBS 文件。

详见 [HPC 使用说明](hpc/ATLAS_RUN_GUIDE.zh-CN.md)、[实验文件索引](benchmarks/atlas/EXPERIMENT_INDEX.zh-CN.md)及[中文结果总览](analysis/atlas/report_results.zh-CN.md)。历史源码包保持原样，新作业包使用当前代码。实验记录按要求保留原始用户名、主机名和路径，未脱敏。

## 新增固定 P 的线程扩展实验

[固定 P=2 实验说明](hpc/THREAD_SCALING_GUIDE.zh-CN.md)提供一个独立 CPU 作业：T=1、2、3、4、6，对比 V2/V3，分别记录 50 条普通计时与 50 条独立阶段诊断。原来四组实验无需重跑。当前 `--profile` 保留逐 rank 内核与阶段耗时，分析使用内核最慢 rank 的全部阶段。已归档作业 `1028185.venus01`，普通计时 50 条、独立诊断 50 条及小数据预检 20 次均通过复核。新增原始证据见 [统一实验索引](benchmarks/atlas/EXPERIMENT_INDEX.zh-CN.md)，结果与图表见 [补充分析](analysis/atlas/THREAD_SCALING.zh-CN.md)。原四组 125 条与新增 50 条合计 **175 条普通性能测量**；诊断另计。运行 `python3 -B scripts/reproduce_atlas_thread_scaling.py` 可在副本上复核新增实验。

## 报告图表与统计表

已统一保存七张英文报告图：原五张为 PNG/PDF/SVG，新增固定 P 的两张为 PNG/SVG，并保留精确 CSV，以及中、英、韩三语言图注。详见[图表索引](analysis/atlas/Figure/FIGURE_GUIDE.zh-CN.md)、[图表总览](analysis/atlas/overview.png)、[中文结果与图注](analysis/atlas/report_results.zh-CN.md)。安装可选绘图依赖后，可在新目录重新生成：

```sh
python3 -m pip install -r requirements.txt
python3 scripts/plot_atlas.py --output artifacts/atlas-figures-new
```

仅绘图需要 Matplotlib；`--tables-only` 只用标准库生成统计及中、英、韩三语言图注和说明。误差线表示实测最小到最大值，不是置信区间；各项比较保留作业边界，并明确标出参考基线。

## 目录结构

```text
src/          C++ 算法、数据生成、MPI 运行封装与 JSON 输出
scripts/      实验运行与 CSV 汇总
tests/       数值正确性与实验工具测试
examples/     可手算验证的小型输入
hpc/          PBS 脚本、绑核工具与独立作业包生成器
benchmarks/   Atlas 原始结果、源码快照和核查证据
analysis/     报告图表、精确统计表、图注和复现说明
Makefile      串行／并行编译与测试
```
