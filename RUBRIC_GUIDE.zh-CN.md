# 十一月新评分标准实验指南

[English](RUBRIC_GUIDE.md) · [한국어](RUBRIC_GUIDE.ko.md)

六组实验全部在 Vanda 运行。保留 Lloyd K-means，新增真正的串行规模分析、至 256 个物理 CPU 核的纯 MPI 强/弱扩展、固定资源 MPI+OpenMP 对照、通信诊断和单 GPU CUDA V4。**代码和实验工具已准备，新 HPC 实测尚未完成。**

## 算法和评分对应

每轮 Lloyd 迭代为：计算最近质心、累加各簇坐标和/计数、全局归约充分统计量、更新质心。等距时取最小簇编号，空簇保留旧质心。固定 I 轮的距离计算复杂度为 O(INKD)，每个 rank 的全局统计量大小为 O(KD)。按全局样本编号分区，支持不均匀分区和空 rank；生成器不随进程数改变。

V0 为真正串行版本；V1 为进程内串行计算加 MPI；V2 使用 OpenMP atomic；V3 使用带填充的线程私有统计缓冲，再执行本地合并。新增 V4 将样本常驻显存，第一 CUDA 内核计算距离并累加各 block 独立的统计数组，第二内核归并这些数组。FP64 统计量复制回主机，复用既有 MPI 归约和质心更新，更新后的质心每轮传回 GPU。V4 目前仅接受 **P=1、一个主机线程**；多节点 MPI+OpenMP 是 MPI+X 主线，GPU 为额外单卡实测，未实现多 GPU 扩展。

| 评分项 | 要产出的证据 |
|---|---|
| 算法，5 分 | Lloyd 步骤、复杂度、数据归属、同步依赖 |
| 串行规模，5 分 | V0 分别改变 N/D/K，以及 seconds/(INKD) |
| MPI，10 分 | V1 至 256 个实际核心；强/弱扩展、加速比、效率、通信 |
| MPI+X，10 分 | 总计 256 核的 V2/V3 对照，至少一块 GPU 上的真实 CUDA 执行 |
| 讨论，5 分 | 实测瓶颈、技术选择、主机/设备传输和适用范围 |

合成数据足够，无需下载 Kaggle 数据。生成器固定为 16 个生成簇，与求解器 K 独立；改变 K 会改变计算量和模型容量，不改变生成过程。

## 精确实验矩阵

统一 FP64、seed=42、20 轮计时、2 轮预热、5 次重复；预热后恢复原始质心。正确性预检、阶段诊断与普通计时分别保存。

| 组别 | 普通配置 | 独立诊断配置 | 普通/诊断记录数 |
|---|---|---|---:|
| serial | V0：N={10万,20万,50万,100万,200万,400万}；D={8,16,32,64,128}；K={8,16,32,64,128}；基准 N=100万,D=K=32；基准去重 | 无 | 70 / 0 |
| strong | V0，以及 V1/P={1,2,4,8,16,32,64,128,256}；N=400万,D=K=32 | V1/P={1,C,256} | 50 / 15 |
| weak | 同一 P 序列的 V1；N=10万×P,D=K=32 | P={1,C,256} | 45 / 15 |
| hybrid | V2/V3 的 P×T={256×1,128×2,64×4,32×8}，另加 V1/256×1；N=400万 | V2/V3 的 32×8 | 45 / 10 |
| communication | V1/P={C,256}，Allreduce 对比 Reduce+Bcast；N=400万 | 四个配置全部诊断 | 20 / 20 |
| gpu | N={10万,100万,400万},D=K=32；同一 GPU 作业内 V0/CPU1、V3/CPU8、V4/GPU1 | 三个 V4 规模 | 45 / 15 |
| 合计 | 55 个配置 | 15 个配置 | **275 / 75** |

C 为 {8,16,32,64} 中经过验证的二次幂，选择不超过 64、实际可用物理核数及队列限制的最大值。多节点研究申请 256/C 个独立节点。整个 KVM 拓扑不等于作业获配核心。串行/GPU 作业使用一个节点；GPU 作业申请 8 个 CPU 核和一块 GPU。以下 `--dry-run` 每个配置只显示一次，不展开 5 次重复：

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 scripts/benchmark.py --suite sensitivity --variant v0 --processes 1 --threads 1 --dry-run
```

## 集群准备

先在获配的 CPU/GPU pilot 作业内核查队列时限、节点数限制、`qstat -Qf`、`lscpu`、`mpiexec --version`、`mpicxx --showme`、`nvcc --version` 和 `nvidia-smi -q`。启动器明确面向 **PBS + Open MPI + Linux**，要求各节点共享项目目录和相同 Python 路径。`PBS_NODEFILE` 每节点至少包含 C 个 slot；若集群使用其他 MPI 或 nodefile 约定，需适配后重新预检绑核。

在仓库外编写环境脚本，例如 `/absolute/path/kmeans-env.sh`，加载已确认的编译器/MPI/CUDA 模块。GPU 作业还需设置 `CUDA_HOME` 和 `CUDA_ARCH`（只有设备计算能力为 8.0 时，80 才是适当例子）。V4 要求计算能力 >=6.0，并且 nvcc 与主机编译器兼容；CUDA 13 可能不再编译旧架构，必须核对工具链支持的目标。CPU 作业需要 C++17/OpenMP 编译器和 Open MPI。新完整实验可能需要数小时，应先确认队列限额；应为每个完整 suite 预留足够的时限。

```sh
make all CXX=g++ MPICXX=mpicxx
# 仅 CUDA 环境需要：
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
# 按 pilot 核查结果替换实际队列名：
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue ACTUAL_CPU_QUEUE --gpu-queue ACTUAL_GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
```

生成器只生成六份可审查的 PBS，不提交。检查后从仓库根目录分别提交：

```sh
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/serial.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/strong.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/weak.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/hybrid.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/communication.pbs
qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh artifacts/rubric-jobs/gpu.pbs
```

作业用 `place=scatter:excl` 申请独占且不同的节点。每个作业先保存调度、各节点物理核和工具链信息，再构建、做数值/绑核预检，最后运行打乱顺序的 5 次重复。关闭 Open MPI 自身绑核，由包装器给各 rank 分配互不重叠的物理核子集，并设置单核 `OMP_PLACES`。程序直接记录实际工作线程的 CPU 和 affinity mask；预检及每条样本都拒绝缺失 rank、错误线程数、SMT 重复核、重叠核心或错误节点分布。256 核预检实际启动 256 个单线程 rank 和全部混合布局。GPU 无设备、执行错误、显存不足均报错退出，不回退 CPU。PBS 文件和调度器 `.o*` 输出也应随作业归档。

输出为 `artifacts/rubric-202611/<suite>.<job-id>/probe/` 和 `measurements/`。probe 包含调度/工具链日志、拓扑、分配信息、数值记录、已验证的二进制/源码哈希及 GPU 设备记录。measurements 包含普通 `raw.jsonl`、独立 `profiles.jsonl`、源码清单、分配信息及每条命令 stdout/stderr。已有目录不会覆盖。失败/不完整作业保留用于诊断，不计入正式对照；应在新作业目录重跑整个 suite。源码或二进制变化使原预检失效，最终六个作业必须来自同一份源码快照。

## 验证和计时

```sh
make test
make test-mpi
# 仅在 GPU 作业中执行；笔记本上的 skipped 不代表验收通过：
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH="$CUDA_ARCH"
```

CPU 测试/预检覆盖等距、空簇、不均匀分区、空 rank、两种集合通信及跨节点执行。GPU 小数据与 V0 对比标签、计数和质心，中心容差 rtol=1e-8、atol=1e-10；完整三个规模核查指纹、初始编号、计数和最终 SSE，GPU SSE 相对容差 1e-8，CPU 匹配工作量的 SSE 容差为 1e-10。仅独立诊断使用 CUDA events 测 assignment、tile merge、传输时间；CPU 计时边界同步 GPU。参见 [NVIDIA 计时说明](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#timing)。

`kernel_seconds` 为最慢 rank 的完整计时循环，包含本地计算、传输、通信和主机质心更新。`total_seconds` 包含生成、初始化、GPU 分配/上传、预热、循环及最终评估，不含 MPI 初始化、进程启动和退出。`launch_seconds` 另记录外部进程启动的完整等待时间。首次上传单独记录 CPU 墙钟耗时；每轮 H2D/D2H 诊断为 CUDA event 区间。诊断带来额外开销，不与普通统计混用。CPU 阶段图保留某次真实样本的同一个关键 rank 的完整阶段向量；MPI 阶段包含等待，不等于纯网络延迟。

强扩展分别用同作业 V0、V1/P=1 为基线，E=S/P。弱扩展 E=T1/TP，吞吐加速比 P×T1/TP；小规模 P=1 不能当作最大 N 的串行基线。混合对照固定总计 256 核，参考同作业 V1/256。误差范围为五次实测最小–最大值。

## 归档、复现和交付

每个 PBS 作业构建前会在 `<job>/source/` 保存独立的源码/验收测试快照，避免同时提交时争用同一构建目录。每条测量执行前后都核对源码和二进制哈希。预检与测量完成清单要求保留全部命令/探测日志，离线验收还核对快照和交付源码。归档须一并保留 `source/`、`job.pbs`、`job.stdout`、`probe/` 和 `measurements/`。

把六个**完整作业目录**复制进 `benchmarks/rubric-202611/runs/`，每个保留 `probe/` 和 `measurements/`，并补入 PBS 与调度输出。正式归档每个 suite 只选一份完整作业，失败/替代作业放在归档外。然后：

```sh
python3 scripts/reproduce_rubric.py --status
python3 scripts/reproduce_rubric.py --seal --verify-only
python3 scripts/reproduce_rubric.py --verify-only
python3 scripts/reproduce_rubric.py --tables-only --output artifacts/rubric-tables
python3 -m pip install -r requirements.txt
python3 scripts/reproduce_rubric.py --output artifacts/rubric-figures
python3 scripts/package_rubric.py --output artifacts/kmeans-rubric-source.zip
python3 scripts/package_rubric.py --verify artifacts/kmeans-rubric-source.zip
```

`--seal` 先验收全部 350 条记录，再独占创建校验清单；以后会拒绝缺失、修改、额外加入的证据文件。源码包有独立逐文件哈希；解压后构建，再运行同样的离线验收/重生成命令。仅绘图需要 Matplotlib，数值脚本/验收只需标准库。新图写入指定的新目录；有真实数据后把审阅后的 PNG/PDF/SVG、精确 CSV 和图注保存在 `analysis/rubric-202611/`。参见[图表指南](analysis/rubric-202611/FIGURE_GUIDE.zh-CN.md)。

## 报告结构和保护内容

结果顺序为：串行规模 → MPI 强扩展 → MPI 弱扩展 → 通信 → MPI+OpenMP → GPU。说明数据布局、充分统计量通信（每次归约 KD 个 double 和 K 个 64 位计数，不含协议开销）、atomic 竞争与私有缓冲内存/合并成本、节点边界及主机/设备成本。合成数据支持性能结论，不支持外部真实数据集结论。日志未验收前不写新加速比，也不声称 256 核/GPU 已完成。

新 CPU/GPU 环境另起段落，根据新 probe 填写。保留现有手动分页、三线表、References 独立页；AI 声明原文不改，最后单独一页：

> We used [GPT-6.1 sol] to [help code, create tables and beautify assignment]. We are responsible for the content and quality of the submitted work.

报告采用通过验收的 Vanda 新结果；最终性能表和结论须等正式测量完成后填写。

若原 11 月 13 日截止不变：11 月 2–5 日实现/探测/预检，5–9 日正式实验，9–11 日统计/报告，12 日验收、三语言检查及打包。排队资源和真实 CUDA 验收仍依赖 HPC；本轮不做多 GPU 扩展或额外 GPU 优化版本。
