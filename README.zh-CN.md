# Lloyd K-means：MPI + OpenMP + CUDA

[English](README.md) · [简体中文](README.zh-CN.md) · [한국어](README.ko.md)

使用 C++17 直接实现 Lloyd K-means，包含串行、MPI、MPI+OpenMP 和可选 CUDA 版本，不依赖聚类库。Vanda 实验覆盖 256 个 CPU 核和单块 NVIDIA A40。

## 版本

| 版本 | 实现 |
|---|---|
| V0 | 串行参考 |
| V1 | 各 MPI rank 内串行计算 |
| V2 | OpenMP 共享数组原子累加 |
| V3 | OpenMP 线程私有缓冲与归并 |
| V4 | CUDA 分配与两阶段统计归并；P=1，单 GPU |

## 编译

需要 C++17 编译器和 Make；并行 CPU 版本需要 MPI/OpenMP；V4 需要兼容的 CUDA toolkit 和 nvcc。默认 CPU 构建不依赖 CUDA。在 HPC 上先加载匹配的编译器与 MPI 模块。

```sh
git clone https://github.com/Ru1zh/K-means-MPI-OpenMP.git
cd Code
make all CXX=g++ MPICXX=mpicxx
# Serial only:
make serial
```

可选 GPU 构建：86 对应实测 A40，其他 GPU 应按实际架构设置。

```sh
make cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

macOS 使用 Homebrew Open MPI 与 libomp：

```sh
make all CXX=clang++ MPICXX="$(brew --prefix open-mpi)/bin/mpicxx" \
  OMPFLAGS="-Xpreprocessor -fopenmp -I$(brew --prefix libomp)/include" \
  OMPLIBS="-L$(brew --prefix libomp)/lib -lomp"
```

## 运行

合成数据在内存中生成，无需下载，也不需要 examples 文件夹。

```sh
./build/kmeans_serial --n 10000 --d 8 --k 16 --iterations 20
mpiexec -n 2 ./build/kmeans_mpi --n 10000 --d 8 --k 16 \
  --variant v3 --threads 2 --comm allreduce --iterations 20
./build/kmeans_cuda --variant v4 --n 10000 --d 8 --k 16 --iterations 20
```

纯 MPI 使用 `--variant v1 --threads 1`，原子累加使用 `v2`；`--comm reduce-bcast` 切换通信策略。完整选项见程序的 `--help`。成功运行向 stdout 输出一条 JSON。

## 数据与正确性

生成器等概率选择 16 个高斯分组，中心坐标位于 (-10,10)，加入标准正态噪声（sigma=1，Box-Muller 方法）。随机量由种子、全局样本编号和维度决定，因此在同一构建环境中改变 MPI 分区不改变输入。初始质心为 K 个不同的抽样点；生成分组数与求解器 K 独立。正式实验使用 seed=42，不启用 `--skew`。

坐标与累加使用 FP64，计数使用 64 位整数。等距时选最小簇编号，空簇保留旧质心；最终标签、计数和 SSE 用最终质心重新计算。`--warmup` 结束后恢复初始状态再计时。可选文本输入：首行 `N D`，之后恰好 N×D 个有限坐标。

## 测试

仅需 Python 3.8+ 标准库。11 个 CPU/MPI 测试方法覆盖手算结果、平局、空簇、不均匀及空分区、收敛、预热恢复和阶段计时；3 个可选 GPU 方法验证数值一致性及无设备时明确失败。MPI/GPU 测试应在适当资源分配中执行；跳过 GPU 测试不代表 GPU 验收通过。

```sh
make test
make test-mpi
make test-cuda CUDA_HOME="$CUDA_HOME" CUDA_ARCH=86
```

## HPC 实验

启动器面向 Linux + PBS + Open MPI，要求节点间共享项目目录。先核查队列、模块、时限和物理核分配。将站点模块加载命令放在外部环境脚本中；GPU 作业还需设置 `CUDA_HOME` 与 `CUDA_ARCH`。下列命令生成六份 PBS，检查后再提交。

```sh
python3 scripts/rubric_campaign.py --suite all --cores-per-node 64 --dry-run
python3 hpc/rubric_jobs.py --cores-per-node 64 \
  --cpu-queue CPU_QUEUE --gpu-queue GPU_QUEUE \
  --walltime 08:00:00 --output artifacts/rubric-jobs
for suite in serial strong weak hybrid communication gpu; do
  qsub -v KMEANS_ENV_FILE=/absolute/path/kmeans-env.sh "artifacts/rubric-jobs/$suite.pbs"
done
```

替换队列占位符和环境脚本绝对路径。C 取 {8,16,32,64} 中最大可用值，多节点作业申请 256/C 个独立节点。各作业先保存源码快照、编译并验证数值与实际绑核，再执行五次打乱顺序的重复测量。CPU 重叠、资源不足或 GPU 故障均会终止，不静默回退 CPU。新结果写入独立的 `artifacts/rubric-202611/<suite>.<job-id>/`。

## 正式实验矩阵

统一 FP64、seed=42、20 轮计时、2 轮预热后恢复初始状态、每配置重复 5 次；除规模变化外 D=K=32。共 275 条普通记录与 75 条独立诊断。

| 实验 | 配置 | 普通 / 诊断记录 |
|---|---|---:|
| 串行 | V0：N={100k,200k,500k,1M,2M,4M}；D,K={8,16,32,64,128}，每次只变一项；基准 N=1M,D=K=32 | 70 / 0 |
| 强扩展 | V0 基线与 V1/P={1,2,4,8,16,32,64,128,256}；N=4M | 50 / 15 |
| 弱扩展 | V1，同一组 P；N=100k×P | 45 / 15 |
| 混合并行 | V2/V3，P×T={256×1,128×2,64×4,32×8}，另含 V1/256 | 45 / 10 |
| 通信 | V1/P={C,256}，Allreduce 对比 Reduce+Bcast | 20 / 20 |
| GPU | N={100k,1M,4M}；同作业 V0/CPU1、V3/CPU8、V4/GPU1 | 45 / 15 |

## 计时与解释

`kernel_seconds` 为最慢 rank 的完整迭代循环；`total_seconds` 另含数据准备、初始化、GPU 设置/上传、预热和最终评估，不含 MPI 初始化及外部启动。`--profile` 仅用于独立诊断；CPU 阶段归因采用同一实际 critical rank 的完整向量，GPU 区间使用 CUDA events。MPI 时间包含等待。

强扩展使用同作业 V0 或 V1/P=1 基线，效率为 S/P；弱扩展效率为 T1/TP，吞吐加速比为 P×T1/TP；混合并行固定 P×T=256。只在匹配作业内比较；误差范围为五次实测最小到最大值，不是置信区间。

<!-- LOCAL_ARCHIVE_START -->

## 本地结果与图表

GitHub 仓库保留源码、汇总表和报告图表。原始作业日志与历史源码快照已从当前 Git 追踪中移除，仅在本地保留；原始证据审计命令需要该本地归档。六组 Vanda 实验于 2026 年 11 月 5 日通过验证：Intel Xeon Platinum 8452Y，每节点实际使用 C=64 个物理核，最多四节点，单块 A40；GCC 11.3.0、Open MPI 4.1.8、CUDA 12.4.131。

256 核强扩展相对 V0 加速 130.75 倍、效率 51.07%；弱扩展效率为 57.37%。V3 避免了 V2 的累加开销，但相对纯 MPI 的 1.04% 循环优势仍有范围重叠。GPU 循环相对 CPU1 加速 11.05–13.00 倍，端到端收益较小。

| 图 | 内容 | PNG | PDF | SVG |
|---|---|---|---|---|
| 1 | 串行 N/D/K 扩展 | [PNG](analysis/rubric-202611/paper-figures/figure-1-serial.png) | [PDF](analysis/rubric-202611/paper-figures/figure-1-serial.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-1-serial.svg) |
| 2 | MPI 强扩展 | [PNG](analysis/rubric-202611/paper-figures/figure-2-strong.png) | [PDF](analysis/rubric-202611/paper-figures/figure-2-strong.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-2-strong.svg) |
| 3 | MPI 弱扩展 | [PNG](analysis/rubric-202611/paper-figures/figure-3-weak.png) | [PDF](analysis/rubric-202611/paper-figures/figure-3-weak.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-3-weak.svg) |
| 4 | 通信与阶段占比 | [PNG](analysis/rubric-202611/paper-figures/figure-4-communication.png) | [PDF](analysis/rubric-202611/paper-figures/figure-4-communication.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-4-communication.svg) |
| 5 | 固定 256 核 MPI+OpenMP | [PNG](analysis/rubric-202611/paper-figures/figure-5-hybrid.png) | [PDF](analysis/rubric-202611/paper-figures/figure-5-hybrid.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-5-hybrid.svg) |
| 6 | 同作业 CPU/GPU 对比 | [PNG](analysis/rubric-202611/paper-figures/figure-6-gpu.png) | [PDF](analysis/rubric-202611/paper-figures/figure-6-gpu.pdf) | [SVG](analysis/rubric-202611/paper-figures/figure-6-gpu.svg) |

[精确统计表](analysis/rubric-202611/verified-20261105/statistics.csv) · [独立阶段汇总](analysis/rubric-202611/verified-20261105/profiles.csv)

```sh
python3 scripts/reproduce_rubric.py --verify-only
python3 -m pip install -r requirements.txt
python3 analysis/rubric-202611/render_paper_figures.py \
  --from-tables analysis/rubric-202611/verified-20261105 \
  --output artifacts/report-figures-new
```

`--verify-only` 需要完整封存的本地原始归档；不要重新封存或修改实测快照。从汇总 CSV 重绘需要本地表格，不等同于原始证据审计。时间、问题规模及数值 CPU 数量轴使用对数刻度；阶段占比和效率轴保留线性。完整讨论见报告。OpenAI Codex 协助实现和文档整理。

<!-- LOCAL_ARCHIVE_END -->
