# 已记录的 Atlas 实验

[English](EXPERIMENT_INDEX.md) | [简体中文](EXPERIMENT_INDEX.zh-CN.md) | [한국어](EXPERIMENT_INDEX.ko.md)

这些是于 2026-10-25 从同级 `HPC/` 文件夹复制的原始、**未经脱敏**的记录。主机名、用户名、作业 ID、命令和路径均保留原始记录。最终证据包保留原始运行记录和实测源码快照，省略已被当前指南替代的规划说明。同级原始文件夹保持不变。

## 内容

```text
manifest.json       正式工作负载、记录数量和证据路径
checksums.sha256    此证据包的 SHA-256 清单
runs/               五个作业目录：验证/试验及四项正式研究
source-packages/    六份原始独立源码快照，逐字节保留
```

| 研究 | 作业 ID | 正式记录 | 原始测量 |
| --- | --- | ---: | --- |
| 强扩展 | 1027222.venus01 | 35 | [strong.jsonl](runs/atlas-strong.1027222.venus01/strong.jsonl) |
| 固定 12 核混合并行 | 1027229.venus01 | 30 | [hybrid.jsonl](runs/atlas-hybrid.1027229.venus01/hybrid.jsonl) |
| V2/V3 线程策略 | 1027231.venus01 | 30 | [raw.jsonl](runs/atlas-threads.1027231.venus01/raw.jsonl) |
| 通信策略 | 1027272.venus01 | 30 | [raw.jsonl](runs/atlas-communication.1027272.venus01/raw.jsonl) |

全部 125 条正式测量均使用 N=1,000,000、D=32、K=32、seed=42，固定计时 20 轮、预热 2 轮，每配置重复 5 次。数据指纹为 `7fcf2e8b0cc1a222`。验证作业 `1027219.venus01` 及其较小规模试验工作负载单独保留，不计入该总数。

环境记录标明了实际硬件、CPU 分配、编译器和 MPI 版本。不同作业的分配/NUMA 布局不同；请使用同一作业内匹配的比较。混合并行比较固定总核数为 12，不提供新的串行强扩展基线。策略研究中的全规模 V0 运行是数值参考，并非重复计时基线。

## 复现分析

在仓库根目录使用 Python 3.8+ 运行（仅使用标准库）：

```sh
python3 scripts/reproduce_atlas.py --verify-only
python3 scripts/reproduce_atlas.py --output artifacts/atlas-audit
```

完整性检查覆盖 `checksums.sha256` 中列出的全部文件。第二条命令将四项正式研究复制到新目录，从各项研究的源码快照恢复辅助程序版本，并重新运行原始审计脚本。输出包括重新计算的统计量、布局/数值核查、中文分析报告和 `summary.json`。它不会修改此证据包，也不会重新运行 HPC 计时实验。已存在的输出目录会被拒绝。

验证/试验记录接受完整性检查；其已保存分析仍作为历史证据，而不是重新生成的第五份审计。中文结果解读见[报告结果](../../analysis/atlas/report_results.zh-CN.md)和各作业的 `analysis.zh-CN.md`。

## 重新运行计算

使用 `source-packages/` 中的原始归档重新运行实测源码，或使用[打包工具](../../hpc/ATLAS_RUN_GUIDE.zh-CN.md)运行当前检出版本。两种方式均应从单独解压的包目录提交。数据在内存中生成，无需下载或上传大型输入数据集。

原始记录和历史笔记中保存的路径描述原始运行情况，并不依赖那些账户或本地文件夹。新的打包工具和离线分析命令相对于克隆后的仓库工作。

历史运行说明仍保存在原始源码快照归档内。当前命令统一见上方 HPC 使用指南。`checksums.sha256` 覆盖保留的证据和文档；125 条正式测量保持不变。
