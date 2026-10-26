# 固定 P=2 实验接收与合并记录

作业 `1028185.venus01`；原始下载位于项目 `HPC/atlas-thread-scaling.1028185.venus01/`。2026-10-27 接收并核查后，现与另外四组实验统一存放。

- `runs/atlas-thread-scaling.1028185.venus01/`：983 个接收文件，逐字节保留，包括远端生成的分析。
- `source-packages/project3-atlas-thread-scaling.tar.gz`：本次确切提交包；29 项源文件清单匹配。原始包元数据见 `thread-scaling-packages.json`。
- `manifest.json` 的 `studies.thread-scaling`：50 条普通计时、50 条独立诊断、20 次小数据预检和证据限制。
- `checksums.sha256`：统一覆盖五组实验；合并前两份清单备份在项目 `Local_Archive/layout-before-merge-20261027/`，历史交付包也保留原目录快照。

完整复核统一使用 `python3 -B scripts/reproduce_atlas.py --output artifacts/atlas-audit-new`。不在 runs 下重跑分析。

退出 0 依据作业内 status.txt；PBS 状态快照及外层 stdout 尚未找到。执行文件未下载，记录的二进制哈希仅用于与测量关联。此限制不因目录合并而变化。

[统一实验索引](EXPERIMENT_INDEX.zh-CN.md) · [新实验结果与图表](../../analysis/atlas/THREAD_SCALING.zh-CN.md)
